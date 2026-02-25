#!/bin/bash
set -euo pipefail

# ---------------------
# Helper functions
# ---------------------

function postgres_ready(){
   python3 << END
import sys
import pybrowser_dev.wsgi
from django.db import connections
from django.db.utils import OperationalError
db_conn = connections['default']
try:
    db_conn.cursor()
except OperationalError:
    sys.exit(1)
except:
  raise
  sys.exit(2)
sys.exit(0)
END
}

function wait_for_db() {
  # wait for the database
  >&2 echo "Wait for database"
  until postgres_ready; do
      >&2 echo "Database is not ready yet - sleep 1s"
      sleep 1
  done
  >&2 echo "Database up and running"
}


function drop_privileges() {
  if [ "$(id -u)" -eq 0 ]; then
    exec gosu oma "$@"
  else
    exec "$@"
  fi
}

# ---------------------
# role handlers
# ---------------------

INIT_MARKER="${DARWIN_BROWSERMEDIA_PATH:-/data}/.initialized"
function run_init_if_needed() {
    if [ -f "${INIT_MARKER}" ]; then
      >&2 echo "Initialization already completed - skipping"
      return
    fi

    >&2 echo "Running one-time initialization tasks:"

    # Fix permissions for mounted volumes
    >&2 echo " -> Fixing permissions for mounted volumes"
    chown -R oma:oma "$DARWIN_BROWSERSTATIC_PATH" "$DARWIN_BROWSERMEDIA_PATH"

    # create root account for Django admin page
    >&2 echo " -> Create superuser for the database"
    python3 manage.py shell << EOF
import os
from django.contrib.auth.models import User
try:
    User.objects.get(username=os.environ['SQL_USER'])
except User.DoesNotExist:
    User.objects.create_superuser(os.environ['SQL_USER'],
                                  os.environ['SQL_USERMAIL'],
                                  os.environ['SQL_PASSWORD'])
except Exception as dexc:
    if str(dexc) == 'UNIQUE constraint failed: auth_user.username':
        pass
except:
    raise
EOF
    # mark initialization as done
    >&2 echo "Initialization completed"
    touch "${INIT_MARKER}"
}

function run_web() {
  wait_for_db
  if [ "${AUTO_INIT:-true}" = "true" ]; then
    run_init_if_needed
  fi

  # Make sure the database is set up
  >&2 echo " -> Assure database is set up with tables"
  python3 manage.py migrate --noinput

  # Install static files
  >&2 echo " -> Collect static files"
  python3 manage.py collectstatic --noinput --clear

  drop_privileges "$@"
}

function run_worker() {
  wait_for_db
  drop_privileges "$@"
}

function run_shell() {
  wait_for_db
  drop_privileges "$@"
}

ROLE="${CONTAINER_ROLE:-web}"

case "$ROLE" in
  init)
    run_init_if_needed
    ;;
  web)
    run_web "$@"
    ;;
  worker)
    run_worker "$@"
    ;;
  shell)
    run_shell "$@"
    ;;
  *)
    echo "Unknown CONTAINER_ROLE: $ROLE"
    exit 1
    ;;
esac
