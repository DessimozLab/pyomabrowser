#!/bin/sh
# Entrypoint for the cloudflare_guard sidecar (see docker-compose.yml and
# Readme.md, "Cloudflare load-based challenge"). Idles instead of crash-
# looping when CF_API_TOKEN isn't set, so the "cloudflare-guard" compose
# profile can be left enabled in an env file without every deployment
# needing Cloudflare credentials configured.
set -u

if [ -z "${CF_API_TOKEN:-}" ]; then
    echo "cloudflare_load_guard: CF_API_TOKEN not set, idling."
    exec sleep infinity
fi

interval="${CF_GUARD_INTERVAL_SECONDS:-60}"
while true; do
    python3 /app/cloudflare_load_guard.py || echo "cloudflare_load_guard: run failed, retrying in ${interval}s" >&2
    sleep "$interval"
done
