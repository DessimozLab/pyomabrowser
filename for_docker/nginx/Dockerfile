FROM nginx:latest

RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf.template /etc/nginx/templates/
COPY 50x.html /usr/share/nginx/html/50x.html
COPY 502.html /usr/share/nginx/html/502.html

COPY 15-nginx_template_error_configuration.sh /docker-entrypoint.d/
RUN chmod +x /docker-entrypoint.d/15-nginx_template_error_configuration.sh
