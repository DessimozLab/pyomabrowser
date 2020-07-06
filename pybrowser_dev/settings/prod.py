from .base import *

# Twitter keys
TWITTER_CONSUMER_KEY = 'Aw21HEok8E6YIhTbthJiFsbXy'
TWITTER_CONSUMER_SECRET = 'HaqiwJm3sbVVN8GLjaMRJBLzSwAGSrG163tlohD2buCtvzIQaz'
TWITTER_ACCESS_TOKEN = '2216530352-HQEG8i87Q3FjngbeYno1HitSpOTa1Ur4HyiLYdl'
TWITTER_ACCESS_TOKEN_SECRET = 'wBQDobkrHXAha8IJEEHFiuB1BGeRDE7PaUZrQ0xqEXfRd'

# RECAPTCHA keys
RECAPTCHA_PUBLIC_KEY = "6Lc9PScUAAAAAIi2tZFDxzpBKtNoe3X0GxpgRi_t"
RECAPTCHA_PRIVATE_KEY = "6Lc9PScUAAAAAJzqJ5z5sfJuJJkqxY5EHCB-fmcd"
NOCAPTCHA = True  # using No Captcha reCaptcha


INSTALLED_APPS.extend([
    'google_analytics',
    'captcha',
    'export',
])

MIDDLEWARE.extend([
    'google_analytics.middleware.GoogleAnalyticsMiddleware',
    #'debug_toolbar.middleware.DebugToolbarMiddleware',
])

LOGGING['loggers'].update({
    'export': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': True
    },
    'google_analytics': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': True
    }
})

# beat scheduler for export app
CELERY_BEAT_SCHEDULE = {
    'task-update-omastandalone-exports': {
        'task': 'export.tasks.update_running_jobs',
        'schedule': 30.0,
    },
    'task-purge-old-exports': {
        'task': 'export.tasks.purge_old_exports',
        'schedule': 6 * 3600,
    }
}
# for backward compability reasons
BEAT_SCHEDULE = CELERY_BEAT_SCHEDULE

GOOGLE_ANALYTICS = {
    'google_analytics_id': os.getenv('GOOGLE_TRACKING_ID', 'UA-1093824-1'),
}
GOOGLE_ANALYTICS_IGNORE_PATH = ['/oma/', ]