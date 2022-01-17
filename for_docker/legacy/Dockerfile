# syntax=docker/dockerfile:experimental

# pull latest darwin image 
FROM cbrg/darwin:latest

EXPOSE 8000

ENV DARWIN_BROWSER_REPO_PATH "/browser"
ENV DARWIN_OMA_REPO_PATH "/OMA"
ENV DARWIN_RUN_PATH "/run"
ENV DARWIN_LOG_PATH "/var/log"
WORKDIR /

RUN apt-get -qq update \
    && DEBIAN_FRONTEND="noninteractive" TZ="Europe/Zurich" apt-get install -y --no-install-recommends \
        git \
        libcgi-session-perl \
        openssh-client \
        uwsgi \
        uwsgi-core \
        uwsgi-plugin-python3 \
    && apt-get install -y  --reinstall ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -m 700 /root/.ssh/ \
    && touch /root/.ssh/known_hosts \
    && ssh-keyscan -p 2222 lab.dessimoz.org >> /root/.ssh/known_hosts \
    && chmod 600 /root/.ssh/known_hosts

COPY uwsgi.conf /etc/oma-uwsgi.conf
COPY start.omabrowser /bin/start.omabrowser
COPY entrypoint.sh /bin/entrypoint.sh
RUN chmod 755 /bin/start.omabrowser /bin/entrypoint.sh

RUN --mount=type=ssh git clone ssh://gitolite@lab.dessimoz.org:2222/browser
RUN --mount=type=ssh git clone ssh://gitolite@lab.dessimoz.org:2222/OMA
RUN --mount=type=ssh cd /browser && git pull \
      && cd /OMA && git pull

ENTRYPOINT ["entrypoint.sh", "uwsgi", "--ini", "/etc/oma-uwsgi.conf"]
