from .profiling import *

EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = os.getenv("EMAIL_PORT")
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = os.getenv("EMAIL_TLS", True)

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