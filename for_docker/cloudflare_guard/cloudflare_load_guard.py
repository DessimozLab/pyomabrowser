#!/usr/bin/env python3
"""
Watches the local nginx access log for signs of heavy load (high request
rate, a high 5xx/429 error rate, and/or high median response time) and
toggles a pre-created Cloudflare WAF custom rule (Managed Challenge on a set
of URI paths) on or off accordingly.

The response-time trigger needs the log format to include `rt=$request_time`
(not part of nginx's default combined format — see Readme.md,
"Cloudflare load-based challenge", for the log_format line to add). Without
it, that trigger is silently inactive and only request rate / error rate are
used.

It only needs Python 3's standard library and read access to the nginx access
log, so it can run either way (see Readme.md, "Cloudflare load-based
challenge"):
  - as the "cloudflare_guard" sidecar in docker-compose.yml, gated behind the
    "cloudflare-guard" compose profile; or
  - standalone via cron on a bare-metal nginx host, independent of Docker,
    using cloudflare_load_guard.env.template as the source of its environment.

One-time setup (see Readme.md, "Cloudflare load-based challenge"):
  1. Create a Custom Rule in Cloudflare (Security -> WAF -> Custom rules)
     matching the URI paths to protect, action "Managed Challenge", saved
     but left DISABLED.
  2. Note the zone ID, the ruleset ID, and that rule's ID.
  3. Create a scoped API token (Zone / Zone WAF / Edit, restricted to that
     zone) and put it, together with the IDs above, into the env file used by
     whichever deployment mode above applies.

Each run reads only the bytes appended to the log since the previous run
(tracked in a small state file), classifies the window as calm or elevated,
and requires several consecutive elevated/calm windows in a row (hysteresis)
before actually flipping the rule, to avoid flapping it on noisy traffic.
The live rule state is always re-read from Cloudflare before deciding to
call PATCH, so manual dashboard changes are respected rather than clobbered.

To calibrate thresholds against an existing log instead of live traffic, use
--replay (see its --help text below): it re-derives elapsed time from the
log's own timestamps rather than wall-clock time between runs, and never
touches Cloudflare or the state file.
"""
import argparse
import datetime
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

CF_API_BASE = "https://api.cloudflare.com/client/v4"

# Default nginx combined log format:
# $remote_addr - $remote_user [$time_local] "$request" $status $body_bytes_sent "$referer" "$ua"
LOG_LINE_RE = re.compile(r'^\S+ \S+ \S+ \[([^\]]+)\] "([^"]*)" (\d{3}) ')

# Optional trailing field, present only if the log_format was extended with
# rt=$request_time (see module docstring). Matched independently of position
# so it works whether it was appended at the end of combined or elsewhere.
REQUEST_TIME_RE = re.compile(r'\brt=([\d.]+)')

MONTHS = {name: i for i, name in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), start=1)}
TIME_LOCAL_RE = re.compile(r'(\d{2})/(\w{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) ([+-]\d{4})')


@dataclass
class Thresholds:
    rps_high: float
    rps_low: float
    error_rate_high: float
    latency_high: float  # or None, if unconfigured
    min_sample: int
    consecutive_on: int
    consecutive_off: int


def env(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and not value:
        sys.exit(f"missing required environment variable: {name}")
    return value


def thresholds_from_env():
    latency_high_raw = env("CF_GUARD_LATENCY_HIGH", "")
    return Thresholds(
        rps_high=float(env("CF_GUARD_RPS_HIGH", "50")),
        rps_low=float(env("CF_GUARD_RPS_LOW", "20")),
        error_rate_high=float(env("CF_GUARD_ERROR_RATE_HIGH", "0.2")),
        latency_high=float(latency_high_raw) if latency_high_raw else None,
        min_sample=int(env("CF_GUARD_MIN_SAMPLE", "20")),
        consecutive_on=int(env("CF_GUARD_CONSECUTIVE_ON", "3")),
        consecutive_off=int(env("CF_GUARD_CONSECUTIVE_OFF", "5")),
    )


def load_state(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(path, state):
    tmp = f"{path}.tmp"
    with open(tmp, "w") as fh:
        json.dump(state, fh)
    os.replace(tmp, path)


def read_new_lines(log_path, state):
    """Return (lines, new_offset, new_inode) for bytes appended since last run."""
    st = os.stat(log_path)
    inode = st.st_ino
    size = st.st_size
    offset = state.get("offset", 0)

    if state.get("inode") != inode or offset > size:
        # Rotated (or truncated) since last run — start fresh from here on,
        # no way to recover the window that was lost during rotation.
        offset = 0

    with open(log_path, "r", errors="replace") as fh:
        fh.seek(offset)
        data = fh.read()
        new_offset = fh.tell()

    lines = data.splitlines()
    return lines, new_offset, inode


def classify(lines, path_filter):
    total = 0
    errors = 0
    request_times = []
    for line in lines:
        m = LOG_LINE_RE.match(line)
        if not m:
            continue
        request, status = m.group(2), m.group(3)
        if path_filter and not path_filter.search(request):
            continue
        total += 1
        if status == "429" or status.startswith("5"):
            errors += 1
        rt_match = REQUEST_TIME_RE.search(line)
        if rt_match:
            request_times.append(float(rt_match.group(1)))
    return total, errors, request_times


def evaluate_window(total, errors, request_times, elapsed, thresholds):
    """Shared by live mode and --replay so their decisions can't drift apart."""
    rps = total / elapsed if elapsed else 0.0
    error_rate = errors / total if total else 0.0
    median_rt = statistics.median(request_times) if request_times else None

    latency_elevated = (
        thresholds.latency_high is not None
        and median_rt is not None
        and total >= thresholds.min_sample
        and median_rt >= thresholds.latency_high
    )
    latency_calm = (
        thresholds.latency_high is None
        or median_rt is None
        or median_rt < thresholds.latency_high
    )
    is_heavy = (
        rps >= thresholds.rps_high
        or (total >= thresholds.min_sample and error_rate >= thresholds.error_rate_high)
        or latency_elevated
    )
    is_calm = rps <= thresholds.rps_low and error_rate < thresholds.error_rate_high and latency_calm
    return rps, error_rate, median_rt, is_heavy, is_calm


def parse_time_local(raw):
    m = TIME_LOCAL_RE.match(raw)
    if not m:
        return None
    day, mon, year, hh, mm, ss, tz = m.groups()
    month = MONTHS.get(mon)
    if month is None:
        return None
    sign = 1 if tz[0] == "+" else -1
    offset_minutes = sign * (int(tz[1:3]) * 60 + int(tz[3:5]))
    dt = datetime.datetime(
        int(year), month, int(day), int(hh), int(mm), int(ss),
        tzinfo=datetime.timezone(datetime.timedelta(minutes=offset_minutes)),
    )
    return dt.timestamp()


def cf_request(method, path, token, body=None):
    url = f"{CF_API_BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Cloudflare API {method} {path} failed: {exc.code} {exc.read()}")


def get_rule(zone_id, ruleset_id, rule_id, token):
    result = cf_request("GET", f"/zones/{zone_id}/rulesets/{ruleset_id}", token)
    for rule in result["result"]["rules"]:
        if rule["id"] == rule_id:
            return rule
    raise SystemExit(f"rule {rule_id} not found in ruleset {ruleset_id}")


def set_rule_enabled(zone_id, ruleset_id, rule_id, token, enabled):
    rule = get_rule(zone_id, ruleset_id, rule_id, token)
    if rule["enabled"] == enabled:
        return False, rule["enabled"]

    body = {
        "action": rule["action"],
        "expression": rule["expression"],
        "description": rule.get("description", ""),
        "enabled": enabled,
    }
    if rule.get("action_parameters"):
        body["action_parameters"] = rule["action_parameters"]

    cf_request("PATCH", f"/zones/{zone_id}/rulesets/{ruleset_id}/rules/{rule_id}", token, body)
    return True, rule["enabled"]


def format_window_line(ts_label, total, errors, rps, error_rate, median_rt,
                        consecutive_high, consecutive_low, outcome_suffix):
    median_rt_str = f"{median_rt:.3f}s" if median_rt is not None else "n/a"
    return (
        f"[{ts_label}] requests={total} errors={errors} "
        f"rps={rps:.2f} error_rate={error_rate:.2%} median_rt={median_rt_str} "
        f"consecutive_high={consecutive_high} consecutive_low={consecutive_low}"
        + outcome_suffix
    )


def replay(log_path, window_seconds, path_filter, thresholds, verbose):
    """
    Offline calibration: buckets a historical log into fixed windows using
    the log's OWN timestamps (never wall-clock), runs each window through
    the exact same decision logic as live mode, and reports what would have
    happened. Never calls Cloudflare and never touches the live state file.
    """
    consecutive_high = 0
    consecutive_low = 0
    enabled = False
    window_count = 0
    transition_count = 0
    rps_values, error_rate_values, median_rt_values = [], [], []

    # After this many consecutive empty windows, both hysteresis counters
    # have already saturated (and any pending transition has already fired)
    # — further identical empty windows change nothing, so a long quiet
    # stretch in the log can be fast-forwarded instead of walked one window
    # at a time (which would be O(gap length / window) otherwise).
    settle_after = max(thresholds.consecutive_on, thresholds.consecutive_off) + 1

    def process(bucket_start, total, errors, request_times):
        nonlocal consecutive_high, consecutive_low, enabled, window_count, transition_count
        rps, error_rate, median_rt, is_heavy, is_calm = evaluate_window(
            total, errors, request_times, window_seconds, thresholds
        )
        consecutive_high = consecutive_high + 1 if is_heavy else 0
        consecutive_low = consecutive_low + 1 if is_calm else 0
        window_count += 1
        rps_values.append(rps)
        error_rate_values.append(error_rate)
        if median_rt is not None:
            median_rt_values.append(median_rt)

        transition = None
        if consecutive_high >= thresholds.consecutive_on and not enabled:
            enabled = True
            transition = "ENABLE"
            transition_count += 1
        elif consecutive_low >= thresholds.consecutive_off and enabled:
            enabled = False
            transition = "DISABLE"
            transition_count += 1

        if verbose or transition:
            ts_label = datetime.datetime.fromtimestamp(
                bucket_start, tz=datetime.timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            suffix = f" -> would {transition} managed challenge" if transition else ""
            print(format_window_line(ts_label, total, errors, rps, error_rate, median_rt,
                                      consecutive_high, consecutive_low, suffix))

    bucket_start = None
    bucket_lines = []  # list of (status, request_time_or_None) for the currently open bucket

    def flush_and_advance():
        nonlocal bucket_lines, bucket_start
        total = len(bucket_lines)
        errors = sum(1 for status, _ in bucket_lines if status == "429" or status.startswith("5"))
        times = [rt for _, rt in bucket_lines if rt is not None]
        process(bucket_start, total, errors, times)
        bucket_lines = []
        bucket_start += window_seconds

    with open(log_path, errors="replace") as fh:
        for raw_line in fh:
            m = LOG_LINE_RE.match(raw_line)
            if not m:
                continue
            ts = parse_time_local(m.group(1))
            if ts is None:
                continue
            request, status = m.group(2), m.group(3)
            if path_filter and not path_filter.search(request):
                continue

            if bucket_start is None:
                bucket_start = ts

            while ts >= bucket_start + window_seconds:
                flush_and_advance()  # flushes whatever was pending (possibly empty)
                remaining = int((ts - bucket_start) // window_seconds)
                if remaining > settle_after:
                    for _ in range(settle_after):
                        process(bucket_start, 0, 0, [])
                        bucket_start += window_seconds
                    skipped = int((ts - bucket_start) // window_seconds)
                    print(f"  ... {skipped} quiet window(s) skipped (state already settled) ...")
                    bucket_start += skipped * window_seconds
                    window_count += skipped
                    break  # ts now fits within [bucket_start, bucket_start + window_seconds)

            rt_match = REQUEST_TIME_RE.search(raw_line)
            rt = float(rt_match.group(1)) if rt_match else None
            bucket_lines.append((status, rt))

        if bucket_start is not None:
            # Final bucket may be shorter than window_seconds if the log ends
            # mid-window — its rps is a slight underestimate as a result.
            flush_and_advance()

    if window_count == 0:
        print("no parseable log lines found (check the file matches nginx's combined log format)")
        return

    def summarize(label, values, fmt):
        if not values:
            return f"{label}: n/a"
        return f"{label}: min={fmt(min(values))} median={fmt(statistics.median(values))} max={fmt(max(values))}"

    print()
    print(f"{window_count} window(s) analyzed ({window_seconds:.0f}s each), "
          f"{transition_count} would-be transition(s), ended {'ENABLED' if enabled else 'DISABLED'}")
    print(summarize("rps", rps_values, lambda v: f"{v:.2f}"))
    print(summarize("error_rate", error_rate_values, lambda v: f"{v:.2%}"))
    print(summarize("median_rt", median_rt_values, lambda v: f"{v:.3f}s"))


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                         help="compute and log the decision but never call the Cloudflare API")
    parser.add_argument("--replay", metavar="LOG_FILE",
                         help="calibrate offline against a historical access log instead of "
                              "monitoring live: buckets it by its own timestamps, runs the same "
                              "decision logic, and reports what would have happened. Never calls "
                              "Cloudflare or touches the live state file; CF_ZONE_ID etc. are not "
                              "required. Still reads the CF_GUARD_* threshold env vars.")
    parser.add_argument("--replay-window", type=float, default=60.0,
                         help="bucket size in seconds for --replay, matching your intended cron "
                              "interval (default: 60)")
    parser.add_argument("--replay-verbose", action="store_true",
                         help="with --replay, print every bucket instead of just transitions and "
                              "the final summary")
    args = parser.parse_args()

    path_filter_pattern = env("CF_GUARD_PATH_FILTER", "")
    path_filter = re.compile(path_filter_pattern) if path_filter_pattern else None
    thresholds = thresholds_from_env()

    if args.replay:
        if args.replay_window <= 0:
            sys.exit("--replay-window must be positive")
        replay(args.replay, args.replay_window, path_filter, thresholds, args.replay_verbose)
        return

    log_path = env("CF_GUARD_ACCESS_LOG", required=True)
    state_path = env("CF_GUARD_STATE_FILE", "/var/tmp/cloudflare_load_guard.state.json")
    dry_run = args.dry_run or env("CF_GUARD_DRY_RUN", "false").lower() == "true"

    zone_id = env("CF_ZONE_ID", required=True)
    ruleset_id = env("CF_RULESET_ID", required=True)
    rule_id = env("CF_RULE_ID", required=True)
    token = env("CF_API_TOKEN", required=True)

    state = load_state(state_path)
    now = time.time()
    last_run_ts = state.get("last_run_ts", now - 60)
    elapsed = max(now - last_run_ts, 1.0)

    lines, new_offset, inode = read_new_lines(log_path, state)
    total, errors, request_times = classify(lines, path_filter)
    rps, error_rate, median_rt, is_heavy, is_calm = evaluate_window(
        total, errors, request_times, elapsed, thresholds
    )

    consecutive_high = state.get("consecutive_high", 0) + 1 if is_heavy else 0
    consecutive_low = state.get("consecutive_low", 0) + 1 if is_calm else 0

    want_enabled = None
    if consecutive_high >= thresholds.consecutive_on:
        want_enabled = True
    elif consecutive_low >= thresholds.consecutive_off:
        want_enabled = False

    if want_enabled is None:
        outcome = " (no state change triggered this window)"
    elif dry_run:
        outcome = f" -> would {'ENABLE' if want_enabled else 'DISABLE'} managed challenge (dry-run, API not called)"
    else:
        changed, was_enabled = set_rule_enabled(zone_id, ruleset_id, rule_id, token, want_enabled)
        outcome = (
            f" -> {'ENABLED' if want_enabled else 'DISABLED'} managed challenge"
            if changed
            else f" (no change, already {'enabled' if was_enabled else 'disabled'})"
        )

    ts_label = time.strftime('%Y-%m-%dT%H:%M:%S')
    print(f"window={elapsed:.0f}s " +
          format_window_line(ts_label, total, errors, rps, error_rate, median_rt,
                              consecutive_high, consecutive_low, outcome))

    state.update({
        "offset": new_offset,
        "inode": inode,
        "last_run_ts": now,
        "consecutive_high": consecutive_high,
        "consecutive_low": consecutive_low,
    })
    save_state(state_path, state)


if __name__ == "__main__":
    main()
