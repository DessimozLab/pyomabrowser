#!/bin/bash
set -e

# copy static files to $DARWIN_BROWSERSTATIC_PATH
cp -rnp $DARWIN_BROWSER_REPO_PATH/htdocs/* $DARWIN_BROWSERSTATIC_PATH/

exec "$@"
