# syntax=docker/dockerfile:1

# pull official base image
FROM python:3.12-slim AS oma_basis

ENV SRC_DIR="/usr/src/pyomabrowser"

RUN apt-get -qq update \
    && apt-get install -y --no-install-recommends \
       wget openssh-client git-core gcc build-essential \
       libpq-dev mafft \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -m 700 /root/.ssh/ \
    && touch /root/.ssh/known_hosts \
    && ssh-keyscan -p 2222 lab.dessimoz.org >> /root/.ssh/known_hosts \
    && chmod 600 /root/.ssh/known_hosts

# --- Install uv ---
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR $SRC_DIR
COPY pyproject.toml uv.lock ./

# --- Install dependencies securely ---
# If LABGIT_TOKEN is passed as a secret, switch URLs from SSH → HTTPS dynamically.
RUN --mount=type=ssh \
    --mount=type=secret,id=labgit \
    bash -c '\
      if [ -f /run/secrets/labgit ]; then \
        DEFAULT_SSH="ssh://gitolite@lab.dessimoz.org:2222/"; \
        LABGIT=$(cat /run/secrets/labgit); \
        if [ -n "${LABGIT}" ] && [ "${LABGIT%/}" = "${LABGIT}" ]; then \
          LABGIT="${LABGIT}/"; \
        fi; \
        if [ "${LABGIT}" != "${DEFAULT_SSH}" ]; then \
          echo "Replacing Git URLs for non-default host: $LABGIT"; \
          ESCAPED_LABGIT=$(printf "%s\n" "$LABGIT" | sed "s/[&/]/\\\\&/g"); \
          sed -i "s|$DEFAULT_SSH|$ESCAPED_LABGIT|g" pyproject.toml; \
        else \
          echo "Using default SSH Git URLs"; \
        fi; \
      fi; \
      git config --global url."ssh://gitolite@lab.dessimoz.org:2222/".insteadOf \
                        "ssh://lab.dessimoz.org:2222/"; \
      uv sync --all-groups \
    '

# Install dependencies into a venv directly at /app
RUN --mount=type=ssh \
    uv venv /app \
    && VIRTUAL_ENV=/app uv sync --frozen --all-groups --active \
    && python -OO -m compileall /app


FROM node:24-alpine as frontend_builder
WORKDIR /app
COPY frontend/package*json ./
RUN npm install
COPY frontend .
RUN npm run build


FROM python:3.12-slim AS runtime

# set environment varibles
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# hide warnings about invalid escape sequences in Python files (e.g. in ete3)
ENV PYTHONWARNINGS="ignore:invalid escape sequence:SyntaxWarning"
ENV SRC_DIR="/usr/src/pyomabrowser"

# create oma user
RUN useradd --system --no-create-home oma

# add gosu for easy step-down from root
ARG TARGETPLATFORM
RUN set -eux; \
    apt-get -qq update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       libpq5 \
       mafft \
       wget; \
    case "$TARGETPLATFORM" in \
      "linux/amd64") ARCH="amd64" ;;\
      "linux/arm64") ARCH="arm64" ;; \
      *) echo "Unsupported platform: $TARGETPLATFORM" >&2; exit 1 ;; \
    esac; \
    wget -O /usr/local/bin/gosu "https://github.com/tianon/gosu/releases/download/1.19/gosu-$ARCH"; \
    chmod +x /usr/local/bin/gosu; \
    gosu nobody true; \
    rm -rf /var/lib/apt/lists/*

COPY --from=oma_basis --chown=oma /app /app
COPY --from=frontend_builder --chown=oma /app/static/ /app/oma/static/
ENV PATH="/app/bin:$PATH"

# set work directory
COPY . $SRC_DIR
WORKDIR $SRC_DIR

COPY for_docker/oma/entrypoint.sh /
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
