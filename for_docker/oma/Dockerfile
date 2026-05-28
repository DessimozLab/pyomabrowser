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
    && chmod 600 /root/.ssh/known_hosts \
    && printf 'Host lab.dessimoz.org\n    Port 2222\n    User gitolite\n    StrictHostKeyChecking yes\n' > /root/.ssh/config \
    && chmod 600 /root/.ssh/config

# --- Install uv ---
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR $SRC_DIR
COPY pyproject.toml uv.lock ./

# --- Install dependencies securely ---
# Supports:
# 1. SSH (default) - uses --mount=type=ssh
# 2. labgit secret with optional TOKEN replacement, allows also to switch URLs from SSH -> HTTPS
#    - labgit contains URL template with ${TOKEN} placeholder
#    - TOKEN secret provides the actual token value
#    - If ${TOKEN} not in URL, TOKEN secret is ignored
RUN --mount=type=ssh \
    --mount=type=secret,id=labgit \
    --mount=type=secret,id=TOKEN \
    bash -c '\
      DEFAULT_SSH="ssh://gitolite@lab.dessimoz.org:2222/"; \
      REPLACEMENT_URL=""; \
      \
      # Check for labgit secret file \
      if [ -f /run/secrets/labgit ]; then \
        LABGIT=$(cat /run/secrets/labgit); \
        \
        # If TOKEN secret exists and URL contains ${TOKEN}, replace it \
        if [ -f /run/secrets/TOKEN ]; then \
          TOKEN_VALUE=$(cat /run/secrets/TOKEN); \
          if [[ "$LABGIT" == *"\${TOKEN}"* ]] || [[ "$LABGIT" == *"\$TOKEN"* ]]; then \
            echo "Replacing \${TOKEN} placeholder in labgit URL"; \
            LABGIT="${LABGIT//\$\{TOKEN\}/$TOKEN_VALUE}"; \
            LABGIT="${LABGIT//\$TOKEN/$TOKEN_VALUE}"; \
          fi; \
        fi; \
        \
        # Ensure trailing slash \
        if [ -n "${LABGIT}" ] && [ "${LABGIT%/}" = "${LABGIT}" ]; then \
          LABGIT="${LABGIT}/"; \
        fi; \
        if [ "${LABGIT}" != "${DEFAULT_SSH}" ]; then \
          echo "Using Git URL from secret file"; \
          REPLACEMENT_URL="${LABGIT}"; \
        fi; \
      fi; \
      \
      # Replace URL if needed \
      if [ -n "$REPLACEMENT_URL" ]; then \
        echo "Replacing $DEFAULT_SSH with configured URL"; \
        git config --global --add url."$REPLACEMENT_URL".insteadOf "ssh://lab.dessimoz.org:2222/"; \
        git config --global --add url."$REPLACEMENT_URL".insteadOf "ssh://gitolite@lab.dessimoz.org:2222/"; \
        git config --global --add url."$REPLACEMENT_URL".insteadOf "git+ssh://lab.dessimoz.org:2222/"; \
        git config --global --add url."$REPLACEMENT_URL".insteadOf "git+ssh://gitolite@lab.dessimoz.org:2222/"; \
      else \
        echo "Using default SSH Git URLs"; \
        git config --global --add url."$DEFAULT_SSH".insteadOf "ssh://lab.dessimoz.org:2222/"; \
        git config --global --add url."$DEFAULT_SSH".insteadOf "git+ssh://lab.dessimoz.org:2222/"; \
      fi; \
      \
      uv venv /app  \
      && VIRTUAL_ENV=/app uv sync --all-groups --frozen --active \
      && python -OO -m compileall /app \
    '



FROM node:24-alpine AS frontend_builder
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
ARG FOLDMASON_VERSION=4-dd3c235
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

# --- Install foldmason ---
# On arm64: single binary. On amd64: install avx2/sse41/sse2 variants and a
# wrapper that selects the best one at runtime by inspecting /proc/cpuinfo.
RUN set -eux; \
    BASE_URL="https://github.com/steineggerlab/foldmason/releases/download/${FOLDMASON_VERSION}"; \
    case "$TARGETPLATFORM" in \
      "linux/arm64") \
        wget -q -O /tmp/foldmason.tar.gz "${BASE_URL}/foldmason-linux-arm64.tar.gz"; \
        tar -xzf /tmp/foldmason.tar.gz -C /tmp; \
        mv /tmp/foldmason/bin/foldmason /usr/local/bin/foldmason; \
        chmod +x /usr/local/bin/foldmason; \
        rm -rf /tmp/foldmason /tmp/foldmason.tar.gz; \
        ;; \
      "linux/amd64") \
        for VARIANT in avx2 sse41 sse2; do \
          wget -q -O /tmp/foldmason-${VARIANT}.tar.gz "${BASE_URL}/foldmason-linux-${VARIANT}.tar.gz"; \
          mkdir -p /tmp/foldmason-${VARIANT}; \
          tar -xzf /tmp/foldmason-${VARIANT}.tar.gz -C /tmp/foldmason-${VARIANT}; \
          mv /tmp/foldmason-${VARIANT}/foldmason/bin/foldmason /usr/local/bin/foldmason.${VARIANT}; \
          chmod +x /usr/local/bin/foldmason.${VARIANT}; \
          rm -rf /tmp/foldmason-${VARIANT} /tmp/foldmason-${VARIANT}.tar.gz; \
        done; \
        printf '#!/bin/sh\nif grep -qw avx2 /proc/cpuinfo 2>/dev/null; then\n    exec /usr/local/bin/foldmason.avx2 "$@"\nelif grep -qw sse4_1 /proc/cpuinfo 2>/dev/null; then\n    exec /usr/local/bin/foldmason.sse41 "$@"\nelse\n    exec /usr/local/bin/foldmason.sse2 "$@"\nfi\n' > /usr/local/bin/foldmason; \
        chmod +x /usr/local/bin/foldmason; \
        ;; \
      *) echo "Unsupported platform: $TARGETPLATFORM" >&2; exit 1 ;; \
    esac

COPY --from=oma_basis --chown=oma /app /app
ENV PATH="/app/bin:$PATH"

# set work directory
COPY . $SRC_DIR
COPY --from=frontend_builder --chown=oma /app/static/ $SRC_DIR/oma/static/
WORKDIR $SRC_DIR

COPY for_docker/oma/entrypoint.sh /
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
