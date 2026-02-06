FROM nginx:latest

# add gomplate for templating
COPY --from=hairyhenderson/gomplate:stable /gomplate /bin/gomplate

RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf.template /etc/nginx/templates/

COPY 15-gomplate-render.sh /docker-entrypoint.d/
RUN chmod +x /docker-entrypoint.d/15-gomplate-render.sh
