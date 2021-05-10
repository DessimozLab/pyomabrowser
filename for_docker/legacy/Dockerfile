# syntax=docker/dockerfile:experimental

# pull latest darwin image 
FROM cbrg/darwin:latest

EXPOSE 8000

ENV DARWIN_BROWSER_REPO_PATH "/browser"
ENV DARWIN_OMA_REPO_PATH "/OMA"
ENV DARWIN_RUN_PATH "/run"
ENV DARWIN_LOG_PATH "/var/log"

RUN apt-get -qq update \
    && apt-get install -y --no-install-recommends \
       uwsgi \
       uwsgi-core \
       uwsgi-plugin-python3 \
       libcgi-session-perl \
    && rm -rf /var/lib/apt/lists/*

COPY uwsgi.conf /etc/oma-uwsgi.conf
COPY start.omabrowser /bin/start.omabrowser
COPY entrypoint.sh /bin/entrypoint.sh
RUN chmod 755 /bin/start.omabrowser /bin/entrypoint.sh

RUN --mount=type=ssh git clone ssh://gitolite@lab.dessimoz.org:2222/browser
RUN --mount=type=ssh git clone ssh://gitolite@lab.dessimoz.org:2222/OMA
RUN --mount=type=ssh cd /browser && git pull \
      && cd /OMA && git pull

ENTRYPOINT ["entrypoint.sh", "uwsgi", "--ini", "/etc/oma-uwsgi.conf"]
