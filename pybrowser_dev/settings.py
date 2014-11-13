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
DEBUG = False

TEMPLATE_DEBUG = DEBUG

ALLOWED_HOSTS = ['omabrowser.org','.ethz.ch','.cs.ucl.ac.uk']

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
    'debug_toolbar_line_profiler.panel.ProfilingPanel',
)

# Application definition

INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'debug_toolbar',
    'debug_toolbar_line_profiler',
    'oma',
    'bootstrap3',
)

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
)


ROOT_URLCONF = 'pybrowser_dev.urls'

WSGI_APPLICATION = 'pybrowser_dev.wsgi.application'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format' : "[%(asctime)s] %(levelname)s [%(name)s:%(lineno)s] %(message)s",
            'datefmt' : "%d/%b/%Y %H:%M:%S"
        },
        'simple': {
            'format': '%(levelname)s %(message)s'
        },
    },
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': os.path.join(os.getenv('DARWIN_LOG_PATH',default=''),'pyoma.log'),
            'formatter': 'verbose'
        },
    },
    'loggers': {
        'django': {
            'handlers':['file'],
            'propagate': True,
            'level':'WARNING',
        },
        'oma': {
            'handlers': ['file'],
            'level': 'DEBUG',
        },
    }
}


# Database
# https://docs.djangoproject.com/en/1.6/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

HDF5DB = {
    'NAME': 'Production',
    'PATH': os.path.join(os.environ['DARWIN_BROWSERDATA_PATH'],
                         'OmaServer.h5')
}

# Internationalization
# https://docs.djangoproject.com/en/1.6/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.6/howto/static-files/
STATIC_ROOT = os.path.join(os.path.expanduser("~"),"Browser","htdocs","static")
STATIC_URL = '/static/'
