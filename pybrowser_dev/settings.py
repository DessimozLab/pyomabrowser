"""
Django settings for pybrowser_dev project.

For more information on this file, see
https://docs.djangoproject.com/en/1.6/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.6/ref/settings/
"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os
BASE_DIR = os.path.dirname(os.path.dirname(__file__))

# deployment, either DEV (default) or PRODUCTION
DEPLOYMENT = os.getenv('DEPLOYMENT_TYPE', default="DEV").upper()

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.6/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = '_^j%sp*a$&+$2esy(k7oarq+kyf@#ubc!lbo@_1r5#rqidc_l_'

# Twitter keys
TWITTER_CONSUMER_KEY = 'Aw21HEok8E6YIhTbthJiFsbXy'
TWITTER_CONSUMER_SECRET = 'HaqiwJm3sbVVN8GLjaMRJBLzSwAGSrG163tlohD2buCtvzIQaz'
TWITTER_ACCESS_TOKEN = '2216530352-HQEG8i87Q3FjngbeYno1HitSpOTa1Ur4HyiLYdl'
TWITTER_ACCESS_TOKEN_SECRET = 'wBQDobkrHXAha8IJEEHFiuB1BGeRDE7PaUZrQ0xqEXfRd'


# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = (DEPLOYMENT != "PRODUCTION")

ALLOWED_HOSTS = ['omabrowser.org', '.ethz.ch', '.cs.ucl.ac.uk']

DEBUG_TOOLBAR_PATCH_SETTINGS = False
SHOW_TOOLBAR_CALLBACK = lambda x: True
INTERNAL_IPS = ('127.0.0.1')
DEBUG_TOOLBAR_PANELS = (
    'debug_toolbar.panels.versions.VersionsPanel',
    'debug_toolbar.panels.timer.TimerPanel',
    'debug_toolbar.panels.settings.SettingsPanel',
    'debug_toolbar.panels.headers.HeadersPanel',
    'debug_toolbar.panels.staticfiles.StaticFilesPanel',
    'debug_toolbar.panels.templates.TemplatesPanel',
    'debug_toolbar.panels.cache.CachePanel',
    'debug_toolbar.panels.signals.SignalsPanel',
    'debug_toolbar.panels.logging.LoggingPanel',
    'debug_toolbar.panels.redirects.RedirectsPanel',
    #'debug_toolbar_line_profiler.panel.ProfilingPanel',
)

# Application definition

INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    #'google_analytics',
    'debug_toolbar',
    'captcha',
    #'debug_toolbar_line_profiler',
    'rest_framework',
    'drf_link_header_pagination',
    'oma',
    'oma_rest',
    'bootstrap3',
)

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    #'google_analytics.middleware.GoogleAnalyticsMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
)

REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'oma_rest.pagination.LinkHeaderPagination',
    'PAGE_SIZE': 100,
    'DEFAULT_VERSIONING_CLASS': 'rest_framework.versioning.AcceptHeaderVersioning',
    'DEFAULT_VERSION': '1.0',
    'ALLOWED_VERSIONS': ('1.0', ),
}


ROOT_URLCONF = 'pybrowser_dev.urls'

WSGI_APPLICATION = 'pybrowser_dev.wsgi.application'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': "[%(asctime)s] %(levelname)s [%(name)s:%(lineno)s] %(message)s",
            'datefmt': "%d/%b/%Y %H:%M:%S"
        },
        'simple': {
            'format': '%(levelname)s %(message)s'
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose'
        }
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'propagate': True,
            'level': 'WARNING',
        },
        'django.request': {
            'handlers': ['console'],
            'propagate': True,
            'level': 'INFO'
        },
        'oma': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': True
        },
        'pyoma': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': True
        },
        'oma_rest': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': True
        },
        'google_analytics': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': True
        }

    }
}

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            # insert your TEMPLATE_DIRS here
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                # Insert your TEMPLATE_CONTEXT_PROCESSORS here or use this
                # list if you haven't customized them:
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.debug',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                'django.template.context_processors.static',
                'django.template.context_processors.tz',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# Database
# https://docs.djangoproject.com/en/1.6/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

os.environ.setdefault('DARWIN_BROWSERDATA_PATH', './')
HDF5DB = {
    'NAME': 'Production',
    'PATH': os.path.join(os.environ['DARWIN_BROWSERDATA_PATH'], 'OmaServer.h5')
}

EMAIL_HOST = "whippee.com"
EMAIL_PORT = 8025
EMAIL_HOST_USER = "labfaq@dessimoz.org"
EMAIL_HOST_PASSWORD = "yZ4J4nsiVwim"
EMAIL_USE_TLS = True

RECAPTCHA_PUBLIC_KEY = "6Lc9PScUAAAAAIi2tZFDxzpBKtNoe3X0GxpgRi_t"
RECAPTCHA_PRIVATE_KEY = "6Lc9PScUAAAAAJzqJ5z5sfJuJJkqxY5EHCB-fmcd"
NOCAPTCHA = True  # using No Captcha reCaptcha

GOOGLE_ANALYTICS = {
    'google_analytics_id': 'UA-1093824-1',
}
GOOGLE_ANALYTICS_IGNORE_PATH = ['/oma/', ]

# Internationalization
# https://docs.djangoproject.com/en/1.6/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.6/howto/static-files/
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(os.path.expanduser("~"), "Browser", "htdocs", "static")
MEDIA_URL = "/media/"
if DEPLOYMENT == "PRODUCTION":
    MEDIA_ROOT = os.path.join(os.path.expanduser("~"), "Browser", "htdocs", "media")
else:
    MEDIA_ROOT = os.path.join(BASE_DIR, 'media')


# some jenkins specific modifications
if DEPLOYMENT == "CI-JENKINS":
    INSTALLED_APPS = INSTALLED_APPS + ('django_jenkins',)
    JENKINS_TASKS = (
        'django_jenkins.tasks.run_pep8',
        'django_jenkins.tasks.run_pyflakes',
    )
