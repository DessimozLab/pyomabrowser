FROM python:3-alpine

COPY cloudflare_load_guard.py entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh

WORKDIR /app
ENTRYPOINT ["/app/entrypoint.sh"]
