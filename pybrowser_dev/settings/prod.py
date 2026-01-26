import logging
from .base import *
try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None
logger = logging.getLogger(__name__)

# RECAPTCHA keys
RECAPTCHA_PUBLIC_KEY = os.getenv("RECAPTCHA_PUBLIC_KEY", "not_specified")
RECAPTCHA_PRIVATE_KEY = os.getenv("RECAPTCHA_PRIVATE_KEY", "not_specified")
NOCAPTCHA = True  # using No Captcha reCaptcha


INSTALLED_APPS.extend([
    'matomo_api_tracking',
    'django_recaptcha',
    'export',
    'fastmap',
    'omamo',
    'expasysearch',
    'mailman_subscribe',
    'taxmap',
])

MIDDLEWARE.extend([
    'oma.middleware.LongRunningLogger',
    'matomo_api_tracking.middleware.MatomoApiTrackingMiddleware',
])

LOGGING['loggers'].update({
    'export': {
        'handlers': ['console'],
        'level': 'DEBUG' if DEBUG else 'INFO',
        'propagate': True
    },
    'fastmap': {
        'handlers': ['console'],
        'level': 'DEBUG' if DEBUG else 'INFO',
        'propagate': True
    },
    'matomo_api_tracking': {
        'handlers': ['console'],
        'level': 'WARNING',
        'propagate': True
    },
    'mailman_subscribe': {
        'handlers': ['console'],
        'level': 'DEBUG' if DEBUG else 'INFO',
        'propagate': True
    }
})

FASTMAP = {
    "engine": os.getenv("FASTMAP_ENGINE", "cluster"),
    "store_files_in_days": 8,
    "omamer_db": os.getenv('OMAMER_DB', None)
}

EXPORT_OMA = {
    "engine": os.getenv("EXPORT_ENGINE", "cluster"),
    "store_files_in_days": 8,
    "allall_root": os.getenv("DARWIN_ALLALL_PATH", None),
    "build_folder": os.getenv("EXPORT_BUILD_PATH", None),
}

CELERY_TASK_ROUTES = {
    'oma.tasks.assign_go_function_to_user_sequences': {'queue': 'long'},
    'oma.tasks.compute_msa': {'queue': 'async_web'},
    'oma.tasks.export_marker_genes': {'queue': 'long'},
}

OMAMO = {
    'CSV': os.path.join(os.environ['DARWIN_BROWSERDATA_PATH'], "omamo_df.csv"),
    "H5": os.path.join(os.environ['DARWIN_BROWSERDATA_PATH'], "omamo.h5"),
}


MAILMAN_SUBSCRIBE = {
    "sender": "contact@omabrowser.org",
    "mailinglist": "oma-request@lists.dessimoz.org",
}

MATOMO_API_TRACKING = {
    'url': 'https://matomo-app.vital-it.ch/matomo.php',
    'site_id': 6,
    'ignore_paths': ["/oma/",],
}

PROVIDE_SCHEMA_DOT_ORG = True

# beat scheduler for export app
CELERY_BEAT_SCHEDULE = {
    'task-update-omastandalone-exports': {
        'task': 'export.tasks.update_running_jobs',
        'schedule': 30.0,
    },
    'task-purge-old-exports': {
        'task': 'export.tasks.purge_old_exports',
        'schedule': 6 * 3600,
    },
    'task-update-fastmap': {
        'task': 'fastmap.tasks.update_running_jobs',
        'schedule': 30.0,
    },
    'task-purge-old-fastmap': {
        'task': 'fastmap.tasks.purge_old_fastmap',
        'schedule': 6 * 3600,
    }
}
if EXPORT_OMA['engine'] == 'celery':
    CELERY_TASK_ROUTES['export.tasks.run_export_celery'] = {'queue': 'long'}
    del CELERY_BEAT_SCHEDULE['task-update-omastandalone-exports']
if FASTMAP['engine'] == 'celery':
    CELERY_TASK_ROUTES['fastmap.tasks.compute_mapping_with_celery'] = {'queue': 'long'}
    del CELERY_BEAT_SCHEDULE['task-update-fastmap']

# for backward compability reasons
BEAT_SCHEDULE = CELERY_BEAT_SCHEDULE

if os.getenv("SENTRY_DSN") is not None:
    if sentry_sdk is None:
        logger.error("Sentry sdk package not installed")
    else:
        sentry_sdk.init(
            dsn = os.getenv("SENTRY_DSN"),
            environment = os.getenv("SENTRY_ENVIRONMENT", "production"),
            # Set traces_sample_rate to 1.0 to capture 100%
            # of transactions for performance monitoring.
            traces_sample_rate = 1.0,
            # Set profiles_sample_rate to 1.0 to profile 100%
            # of sampled transactions.
            # We recommend adjusting this value in production.
            profiles_sample_rate = 1.0 if DEBUG else 0.1,
        )
