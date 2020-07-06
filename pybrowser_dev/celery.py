from __future__ import absolute_import
import os
from celery import Celery

# set the default Django settings module for the 'celery' program.
if "OMA_INSTANCE" in os.environ:
    if os.environ['OMA_INSTANCE'].upper() == "BASF":
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pybrowser_dev.settings.basf')
    elif os.environ['OMA_INSTANCE'].upper() in ("", "FULL"):
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pybrowser_dev.settings.prod')
    elif os.environ['OMA_INSTANCE'].upper() in ("TEST", "TESTING"):
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pybrowser_dev.settings.testing')
else:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pybrowser_dev.settings.testing')

from django.conf import settings  # noqa

app = Celery('browser')

# Using a string here means the worker will not have to
# pickle the object when using Windows.
try:
    app.config_from_object('django.conf:settings', namespace='CELERY')
except TypeError:
    app.config_from_object('django.conf:settings')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))
