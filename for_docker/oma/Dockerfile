# syntax=docker/dockerfile:experimental
ARG PYOMABROWSER_CODEBASE=from_local
ARG SPECIAL_PYTABLES=no
ARG PYOMABROWSER_GITTAG

# pull official base image
FROM python:3.8-slim as oma_basis

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
    'numexpr==2.7.3' \
    'numpy==1.20.2' \
    'pipenv'

WORKDIR $SRC_DIR
COPY Pipfile Pipfile.lock $SRC_DIR
RUN pipenv requirements > requirements.pipenv.txt
RUN echo "psycopg2<2.9\nuwsgi" >> requirements.pipenv.txt
RUN --mount=type=cache,id=wheels-oma,target=/usr/src/app/wheels \
    --mount=type=ssh \
    pip wheel --no-cache-dir --no-deps --wheel-dir /usr/src/app/wheels -r requirements.pipenv.txt

FROM python:3.8-slim as runtime

# set environment varibles
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV SRC_DIR="/usr/src/pyomabrowser"

RUN apt-get -qq update \
    && apt-get install -y --no-install-recommends \
       libpq-dev \
       mafft \
       wget \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

# set work directory
RUN mkdir $SRC_DIR
WORKDIR $SRC_DIR
COPY --from=oma_basis $SRC_DIR/requirements.pipenv.txt $SRC_DIR
RUN --mount=type=cache,id=wheels-oma,target=/wheels \
    ls /wheels \
    && pip install  --no-cache  /wheels/*

COPY . $SRC_DIR
COPY for_docker/oma/entrypoint.sh /

RUN /bin/date | /usr/bin/md5sum > secret_key.txt

