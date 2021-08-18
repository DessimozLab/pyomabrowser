# syntax=docker/dockerfile:experimental
ARG PYOMABROWSER_CODEBASE=from_local
ARG SPECIAL_PYTABLES=no

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

FROM oma_basis as build_from_local
ONBUILD RUN /bin/mkdir $SRC_DIR
ONBUILD COPY ./ $SRC_DIR

FROM oma_basis as build_from_git
ONBUILD RUN --mount=type=ssh \
            git clone ssh://gitolite@lab.dessimoz.org:2222/pyomabrowser \
                               /tmp/pyomabrowser.git && \
            if test -z "$PYOMABROWSER_GITTAG"; then \
              cd /tmp/pyomabrowser.git/ && \
              git checkout $PYOMABROWSER_GITTAG && \
              cd /; \
            fi && \
            /bin/rm -rf /tmp/pyomabrowser.git/.git && \
            /bin/mv /tmp/pyomabrowser.git $SRC_DIR && \
            /bin/rm -rf rm /tmp/pyomabrowser.git

FROM build_${PYOMABROWSER_CODEBASE} as base_web
# install dependencies
RUN pip3 install --no-cache-dir --upgrade pip
RUN pip3 install --no-cache-dir 'psycopg2<2.9'
RUN pip3 install --no-cache-dir uwsgi

FROM base_web as special_pytables_yes
COPY for_docker/oma/tables-3.6.2.dev0-cp38-cp38-manylinux2010_x86_64.whl /
RUN pip3 install --no-cache-dir /tables-3.6.2.dev0-cp38-cp38-manylinux2010_x86_64.whl


FROM base_web as special_pytables_src
RUN apt-get -qq update \
    && apt-get install -y --no-install-recommends \
       cmake \
       liblzo2-dev \
       zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /src/hdf5 \
    && cd /src/hdf5 \
    && wget -O hdf5lib-1.10.4.tar.gz https://support.hdfgroup.org/ftp/HDF5/releases/hdf5-1.10/hdf5-1.10.4/src/hdf5-1.10.4.tar.gz \
    && tar xzf hdf5lib-1.10.4.tar.gz \ 
    && (cd hdf5-1.10.4 \
        && ./configure --prefix /usr --disable-hl --enable-threadsafe \
           --enable-unsupported --with-pthread=yes \
        && make -j4 \
        && make install ) \
    && cd /src \
    && git clone https://github.com/PyTables/PyTables.git \
    && ( cd PyTables \
         && pip3 install --no-cache-dir cython numpy numexpr \
         && python3 setup.py install ) \
    && rm -rf /src

FROM base_web as special_pytables_no

FROM special_pytables_${SPECIAL_PYTABLES}
#COPY requirements.txt $SRC_DIR/requirements.txt
RUN --mount=type=ssh pip3 install --no-cache-dir -r $SRC_DIR/requirements.txt --src /usr/local/src
RUN /bin/date | /usr/bin/md5sum > secret_key.txt

COPY for_docker/oma/entrypoint.sh /


# set work directory
WORKDIR $SRC_DIR

# set environment varibles
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

