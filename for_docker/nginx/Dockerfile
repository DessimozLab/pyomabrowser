FROM nginx:latest

RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf.template /etc/nginx/templates/
COPY 50x.html /usr/share/nginx/html/50x.html
