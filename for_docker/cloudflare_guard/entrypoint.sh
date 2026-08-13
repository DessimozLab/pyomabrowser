#!/bin/sh
# Entrypoint for the cloudflare_guard sidecar (see docker-compose.yml and
# Readme.md, "Cloudflare load-based challenge"). Idles instead of crash-
# looping when CF_API_TOKEN isn't set, so the "cloudflare-guard" compose
# profile can be left enabled in an env file without every deployment
# needing Cloudflare credentials configured.
set -u

# This script runs as the container's PID 1. Without an explicit handler, the
# kernel silently discards default-disposition signals (including SIGTERM)
# sent to PID 1, so `docker/podman stop` or a Kubernetes pod termination would
# otherwise just sit until the runtime's grace period expires and SIGKILLs it.
# Trapping TERM/INT here fixes that everywhere, unlike Docker Compose's
# `init: true` (inserts tini as PID 1 to forward signals) which isn't
# consistently available under podman-compose or Kubernetes.
trap 'exit 0' TERM INT

if [ -z "${CF_API_TOKEN:-}" ]; then
    echo "cloudflare_load_guard: CF_API_TOKEN not set, idling."
    # No `exec` here: exec() resets trapped signals to their default
    # disposition, which would silently undo the trap above.
    while true; do
        sleep 3600 & wait $!
    done
fi

interval="${CF_GUARD_INTERVAL_SECONDS:-60}"
while true; do
    # Run as a backgrounded job and `wait` on it (rather than a plain
    # foreground command) so the trap fires immediately if a signal arrives
    # while python3 (or sleep) is running, instead of only after it exits.
    python3 /app/cloudflare_load_guard.py &
    if ! wait $!; then
        echo "cloudflare_load_guard: run failed, retrying in ${interval}s" >&2
    fi
    sleep "$interval" & wait $!
done
