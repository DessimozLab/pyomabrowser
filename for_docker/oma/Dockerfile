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
        DEFAULT_SSH="ssh://lab.dessimoz.org:2222/"; \
        LABGIT=$(cat /run/secrets/labgit); \
        echo "LABGIT secret: ${LABGIT}"; \
        if [ "${LABGIT}" != "${DEFAULT_SSH}" ]; then \
          echo "Replacing Git URLs for non-default host: $LABGIT"; \
          sed -i "s|${DEFAULT_SSH}|${LABGIT}|g" pyproject.toml; \
          cat pyproject.toml; \
          uv lock; \
          cat uv.lock; \
        else \
          echo "Using default SSH Git URLs"; \
        fi; \
      fi && \
      uv sync --all-groups \
    '

# Install dependencies into a venv directly at /app
RUN --mount=type=ssh \
    uv venv /app \
    && VIRTUAL_ENV=/app uv sync --frozen --all-groups --active \
    && python -OO -m compileall /app


FROM python:3.12-slim AS runtime

# set environment varibles
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV SRC_DIR="/usr/src/pyomabrowser"
RUN useradd --system --no-create-home oma

RUN apt-get -qq update \
    && apt-get install -y --no-install-recommends \
       libpq-dev \
       mafft \
       wget \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

COPY --from=oma_basis --chown=oma /app /app
ENV PATH="/app/bin:$PATH"
# set work directory
RUN mkdir $SRC_DIR
WORKDIR $SRC_DIR
#COPY . $SRC_DIR
COPY for_docker/oma/entrypoint.sh /
