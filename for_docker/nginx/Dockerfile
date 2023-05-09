FROM nginx:latest

RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf.template /etc/nginx/templates/

COPY 15-nginx_template_error_configuration.sh /docker-entrypoint.d/
RUN chmod +x /docker-entrypoint.d/15-nginx_template_error_configuration.sh
