from .base import *
import os

# Twitter keys
TWITTER_CONSUMER_KEY = os.getenv("TWITTER_CONSUMER_KEY")
TWITTER_CONSUMER_SECRET = os.getenv("TWITTER_CONSUMER_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")

# RECAPTCHA keys
RECAPTCHA_PUBLIC_KEY = os.getenv("RECAPTCHA_PUBLIC_KEY", "not_specified")
RECAPTCHA_PRIVATE_KEY = os.getenv("RECAPTCHA_PRIVATE_KEY", "not_specified")
NOCAPTCHA = True  # using No Captcha reCaptcha


INSTALLED_APPS.extend([
    'google_analytics',
    'matomo_api_tracking',
    'captcha',
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
    'google_analytics.middleware.GoogleAnalyticsMiddleware',
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
    'google_analytics': {
        'handlers': ['console'],
        'level': 'WARNING',
        'propagate': True
    },
    'matomo_api_tracking': {
        'handlers': ['console'],
        'level': 'WARNING',
        'propagate': True
    }
})

FASTMAP = {
    "engine": "cluster",
    "store_files_in_days": 8,
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
    'url': 'https://matomo.sib.swiss/matomo.php',
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
# for backward compability reasons
BEAT_SCHEDULE = CELERY_BEAT_SCHEDULE

GOOGLE_ANALYTICS = {
    'google_analytics_id': os.getenv('GOOGLE_TRACKING_ID', 'UA-1093824-1'),
}
GOOGLE_ANALYTICS_IGNORE_PATH = ['/oma/', ]
