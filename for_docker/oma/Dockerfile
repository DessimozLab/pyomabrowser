# syntax=docker/dockerfile:experimental

# pull official base image
FROM python:3.10-slim as oma_basis

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

# install dependencies
RUN pip3 install --no-cache-dir --upgrade pip
RUN pip3 install --no-cache-dir 'psycopg2<2.9'
RUN pip3 install --no-cache-dir uwsgi \
    'numexpr==2.8.4' \
    'numpy==1.23.5' \
    'blosc2' \
    'cython==0.29.33' \
    'pipenv'

WORKDIR $SRC_DIR
COPY Pipfile Pipfile.lock $SRC_DIR
RUN pipenv requirements > requirements.pipenv.txt
RUN echo "psycopg2<2.9\nuwsgi" >> requirements.pipenv.txt
RUN python -m venv /app
ENV PATH="/app/bin:$PATH"
RUN --mount=type=ssh \
    pip install -r requirements.pipenv.txt

FROM python:3.10-slim as runtime

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
COPY . $SRC_DIR
COPY for_docker/oma/entrypoint.sh /
