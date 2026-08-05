"""
Integration tests for the /api/ tiering + rate limiting in nginx.conf.template.

Covers behavior that's invisible to any Django-level test because it's decided
entirely by nginx before a request ever reaches the app:
  - website AJAX (sec-fetch-site: same-origin + a fetch/XHR sec-fetch-mode) is
    never rate-limited, even if the visitor also happens to be logged in.
  - the crawler pattern found in production traffic (sec-fetch-site: same-origin
    but sec-fetch-mode: navigate, i.e. a direct page load, not real AJAX) is NOT
    exempted and is subject to the anonymous rate limit.
  - anonymous callers are served (not blocked with a 401/redirect) but capped
    hard, with a JSON 429 body once the limit trips.
  - authenticated callers (valid Bearer token, per the oauth2-proxy stub) get
    their own, independent per-credential limit.

This spins up the real nginx image (built from ../Dockerfile, same as
production) plus stub "web" and "oauth2-proxy" backends. Run with:
    pytest for_docker/nginx/tests/test_nginx_rate_limiting.py
"""
import json
import subprocess
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
COMPOSE_FILE = TEST_DIR / "docker-compose.test.yml"
COMPOSE_CMD = ["docker", "compose", "-f", str(COMPOSE_FILE)]

VALID_BEARER = "Bearer good-token"


def _fetch(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read(), dict(resp.headers.items())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers.items())


class NginxRateLimitingTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        subprocess.run(COMPOSE_CMD + ["up", "-d", "--build"], check=True, cwd=TEST_DIR)
        cls.base_url = f"http://127.0.0.1:{cls._published_port()}"
        cls._wait_until_ready()

    @classmethod
    def tearDownClass(cls):
        subprocess.run(COMPOSE_CMD + ["down", "-v", "--remove-orphans"], check=True, cwd=TEST_DIR)

    @classmethod
    def _published_port(cls):
        out = subprocess.run(
            COMPOSE_CMD + ["port", "nginx", "80"],
            check=True, cwd=TEST_DIR, capture_output=True, text=True,
        ).stdout.strip()
        return out.rsplit(":", 1)[-1]

    @classmethod
    def _wait_until_ready(cls, timeout=30):
        deadline = time.time() + timeout
        last_error = None
        while time.time() < deadline:
            try:
                status, _, headers = _fetch(cls.base_url + "/All/__readiness_probe__")
                if status == 200 and headers.get("X-From-Stub") == "1":
                    return
                last_error = f"status={status} headers={headers}"
            except (urllib.error.URLError, ConnectionError) as exc:
                last_error = exc
            time.sleep(0.5)
        raise RuntimeError(f"nginx/stubs never became reachable: {last_error}")

    def _hammer(self, path, headers, n):
        """Fire n requests, return the list of (status, body) tuples."""
        results = []
        for _ in range(n):
            status, body, _ = _fetch(self.base_url + path, headers=headers)
            results.append((status, body))
        return results

    # NOTE on ordering: api_anon_limit and api_anon_global_limit are shared,
    # persistent nginx state across every request the container sees for the
    # lifetime of this test class (all test_ methods run against the same
    # nginx instance). Tests that rely on "the very first anonymous request
    # is served" must run before anything else has spent that shared quota —
    # hence the explicit numeric prefixes below to pin execution order.
    # Tests that only assert "eventually a 429 shows up" are order-independent
    # (that holds whether the quota was fresh or already partly spent).

    def test_01_website_ajax_same_origin_cors_is_never_rate_limited(self):
        # Uses its own zone (none at all — website AJAX is unlimited), so this
        # is safe regardless of ordering relative to the anon-tier tests below.
        headers = {"sec-fetch-site": "same-origin", "sec-fetch-mode": "cors"}
        results = self._hammer("/api/rl-test-ajax", headers, 10)
        statuses = [s for s, _ in results]
        self.assertEqual(statuses, [200] * 10, statuses)

    def test_02_website_ajax_is_unaffected_even_with_a_valid_credential(self):
        # A logged-in visitor's own AJAX must not be penalized just because
        # their browser also sends the oauth2-proxy session (simulated here
        # via Authorization, which the /api/ location also inspects).
        headers = {
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "Authorization": VALID_BEARER,
        }
        results = self._hammer("/api/rl-test-ajax-auth", headers, 10)
        statuses = [s for s, _ in results]
        self.assertEqual(statuses, [200] * 10, statuses)

    def test_03_anonymous_first_request_is_served_not_blocked(self):
        # Must run before any other anon-tier test spends the shared quota.
        status, body, _ = _fetch(self.base_url + "/api/rl-test-anon-first")
        self.assertEqual(status, 200, body)

    def test_04_anonymous_and_crawler_pattern_eventually_rate_limited(self):
        # Same-origin + navigate (the crawler pattern found in production)
        # and plain anonymous both land in the same anon tier and are NOT
        # exempted — confirmed by getting a 429 eventually, not a free pass.
        crawler_headers = {"sec-fetch-site": "same-origin", "sec-fetch-mode": "navigate"}
        results = self._hammer("/api/rl-test-crawler", crawler_headers, 4)
        results += self._hammer("/api/rl-test-anon-more", {}, 4)
        statuses = [s for s, _ in results]
        self.assertIn(429, statuses, statuses)
        # The 429 body is the friendly JSON, not nginx's built-in error page —
        # this also exercises recursive_error_pages, since @api_anon is itself
        # reached via an error_page redirect (401 -> @api_anon) before its own
        # limit_req can trigger a second one (429 -> @api_rate_limited).
        bodies = [b for s, b in results if s == 429]
        self.assertTrue(bodies, "expected at least one 429")
        payload = json.loads(bodies[0])
        self.assertEqual(payload, {"detail": "Rate limit exceeded. Log in for a higher limit."})

    def test_05_authenticated_credential_gets_its_own_rate_limit(self):
        # api_auth_limit is keyed per-credential, independent of the anon
        # zones above, so this is safe regardless of their state.
        headers = {"Authorization": VALID_BEARER}
        results = self._hammer("/api/rl-test-authtier", headers, 8)
        statuses = [s for s, _ in results]
        self.assertIn(200, statuses, statuses)
        self.assertIn(429, statuses, statuses)

    def test_06_invalid_credential_falls_back_to_anonymous_tier_not_401(self):
        headers = {"Authorization": "Bearer wrong-token"}
        status, body, _ = _fetch(self.base_url + "/api/rl-test-badtoken", headers=headers)
        # Not authenticated, and not website AJAX -> served at the anon rate
        # (200) or, if the shared anon quota is already spent by an earlier
        # test, rate-limited (429) — either way, never the old hard 401.
        self.assertIn(status, (200, 429), body)

    def test_device_flow_endpoint_stays_public(self):
        status, _, _ = _fetch(self.base_url + "/api/auth/device", headers={})
        self.assertNotEqual(status, 401)

    def test_oma_pages_stay_public_and_unaffected(self):
        status, _, _ = _fetch(self.base_url + "/oma/home/")
        self.assertNotIn(status, (401, 403))


if __name__ == "__main__":
    unittest.main()
