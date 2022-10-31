from .profiling import *

EMAIL_HOST = "whippee.com"
EMAIL_PORT = 8025
EMAIL_HOST_USER = "labfaq@dessimoz.org"
EMAIL_HOST_PASSWORD = "yZ4J4nsiVwim"
EMAIL_USE_TLS = True

# for backward compability reasons
BROKER_URL = CELERY_BROKER_URL
BEAT_SCHEDULE = CELERY_BEAT_SCHEDULE

# Fastmapping adjustments, i.e. run with celery instead of cluster
FASTMAP["engine"] = "celery"
CELERY_TASK_ROUTES.update({
    'fastmap.tasks.compute_mapping_with_celery': {'queue': 'long'},
})

# delete beat scheduler for update-fastmap as not cluster engine used
del CELERY_BEAT_SCHEDULE['task-update-fastmap']