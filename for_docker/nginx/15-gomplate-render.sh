#!/bin/sh
set -e

FILE="/etc/nginx/templates/nginx.conf.template"
gomplate  -f $FILE -o $FILE.tmp
mv $FILE.tmp $FILE