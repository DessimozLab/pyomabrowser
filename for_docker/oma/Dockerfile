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
        git config --global url."$REPLACEMENT_URL".insteadOf "ssh://lab.dessimoz.org:2222/" \
      else \
        echo "Using default SSH Git URLs"; \
        git config --global url."$DEFAULT_SSH".insteadOf "ssh://lab.dessimoz.org:2222/"; \
      fi; \
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
ENV PATH="/app/bin:$PATH"

# set work directory
COPY . $SRC_DIR
COPY --from=frontend_builder --chown=oma /app/static/ $SRC_DIR/oma/static/
WORKDIR $SRC_DIR

COPY for_docker/oma/entrypoint.sh /
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
