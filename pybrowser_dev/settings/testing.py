from .prod import *

EMAIL_HOST = "whippee.com"
EMAIL_PORT = 8025
EMAIL_HOST_USER = "labfaq@dessimoz.org"
EMAIL_HOST_PASSWORD = "yZ4J4nsiVwim"
EMAIL_USE_TLS = True

# for backward compability reasons
BROKER_URL = CELERY_BROKER_URL
BEAT_SCHEDULE = CELERY_BEAT_SCHEDULE
