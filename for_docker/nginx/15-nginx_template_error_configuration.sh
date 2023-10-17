#!/bin/sh

set -e

ME=$(basename $0)

entrypoint_log() {
    if [ -z "${NGINX_ENTRYPOINT_QUIET_LOGS:-}" ]; then
        echo "$@"
    fi
}

remove_error_page() {

  echo "${DEPLOYMENT_TYPE:-}";

  if [ "$DEPLOYMENT_TYPE" = "DEV" ]; then

  start_string="#START_ERROR";
  end_string="#END_ERROR";

  sed  "/$start_string/,/$end_string/d" /etc/nginx/templates/nginx.conf.template > /etc/nginx/templates/nginx.conf.template.tmp;
  mv /etc/nginx/templates/nginx.conf.template.tmp /etc/nginx/templates/nginx.conf.template

  fi

}

remove_error_page

exit 0
