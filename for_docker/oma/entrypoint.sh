#!/bin/bash

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

# exit immediately on commands with a non-zero exit status.
set -e

# wait for the database
>&2 echo "Wait for database"
until postgres_ready; do
    >&2 echo "Database is not ready yet - sleep 1s"
    sleep 1
done
>&2 echo "Database up and running"

# Make sure the database is set up
>&2 echo "Assure database is set up with tables"
python3 manage.py makemigrations
python3 manage.py migrate

# Install static files
python3 manage.py collectstatic --noinput

# create root account for Django admin page
>&2 echo "Create superuser for the database"
python3 manage.py shell << END
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
END

exec "$@"
