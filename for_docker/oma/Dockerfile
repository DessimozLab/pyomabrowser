# syntax=docker/dockerfile:experimental
ARG PYOMABROWSER_CODEBASE=from_local

# pull official base image
FROM python:3.7-slim as oma_basis

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

FROM oma_basis as build_from_local
ONBUILD RUN /bin/mkdir $SRC_DIR
ONBUILD COPY ./ $SRC_DIR

FROM oma_basis as build_from_git
ONBUILD RUN git clone ssh://gitolite@lab.dessimoz.org:2222/pyomabrowser \
                               /tmp/pyomabrowser.git && \
            if test -z "$PYOMABROWSER_GITTAG"; then \
              cd /tmp/pyomabrowser.git/ && \
              git checkout $PYOMABROWSER_GITTAG && \
              cd /; \
            fi && \
            /bin/rm -rf /tmp/pyomabrowser.git/.git && \
            /bin/mv /tmp/pyomabrowser.git $SRC_DIR && \
            /bin/rm -rf rm /tmp/pyomabrowser.git &&

FROM build_${PYOMABROWSER_CODEBASE}
# install dependencies
RUN pip3 install --no-cache-dir --upgrade pip
RUN pip3 install --no-cache-dir psycopg2
RUN pip3 install --no-cache-dir uwsgi
RUN --mount=type=ssh pip3 install --no-cache-dir -r $SRC_DIR/requirements.txt --src /usr/local/src
RUN /bin/date | /usr/bin/md5sum > secret_key.txt

COPY for_docker/oma/entrypoint.sh /


# set work directory
WORKDIR $SRC_DIR

# set environment varibles
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

