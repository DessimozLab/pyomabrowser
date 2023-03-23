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


# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = (DEPLOYMENT != "PRODUCTION")

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')

INTERNAL_IPS = ("127.0.0.1")
if DEBUG:
    import socket  # only if you haven't already imported this
    hostname, _, ips = socket.gethostbyname_ex(socket.gethostname())
    INTERNAL_IPS = [ip[: ip.rfind(".")] + ".1" for ip in ips] + ["127.0.0.1", "10.0.2.2"]
print(INTERNAL_IPS)

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'drf_link_header_pagination',
    'oma',
    'oma_rest',
    'bootstrap4',
    'django.contrib.humanize',
    'academy'
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'oma.middleware.OutdatedHogIdRedirector',
]

REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'oma_rest.pagination.LinkHeaderPagination',
    'PAGE_SIZE': 100,
    'DEFAULT_VERSIONING_CLASS': 'rest_framework.versioning.AcceptHeaderVersioning',
    'DEFAULT_VERSION': '1.8',
    'ALLOWED_VERSIONS': ('1.0', '1.1', '1.2', '1.3', '1.4', '1.5', '1.6', '1.7', '1.8'),
    'DEFAULT_SCHEMA_CLASS': 'rest_framework.schemas.coreapi.AutoSchema',
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
            'level': 'INFO',
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
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'oma.context_processors.xref_order',
                'oma.context_processors.oma_instance',
                'oma.context_processors.release_info',
            ],
        },
    },
]

CELERY_BROKER_URL = os.getenv('CELERY_BROKER', None)
# for backward compability reasons
BROKER_URL = CELERY_BROKER_URL
# CORS stuff to allow iHAM integration on other sites
CORS_ORIGIN_ALLOW_ALL = True
# allow all /api/ views, hogdata and orthoxml
CORS_URLS_REGEX = r'^/(api/|oma/hog(s|data)?/\w*/(orthoxml|json)/$)'
CORS_ALLOW_METHODS = ('GET',)

# Database
DATABASES = {
    'default': {
        'ENGINE': os.getenv('SQL_ENGINE', 'django.db.backends.sqlite3'),
        'NAME': os.getenv('SQL_DATABASE', os.path.join(BASE_DIR, '../../db.sqlite3')),
        'USER': os.getenv('SQL_USER', 'user'),
        'PASSWORD': os.getenv('SQL_PASSWORD', 'password'),
        'HOST': os.getenv('SQL_HOST', 'localhost'),
        'PORT': os.getenv('SQL_PORT', '5432'),
    }
}

os.environ.setdefault('DARWIN_BROWSERDATA_PATH', './')
HDF5DB = {
    'NAME': 'Production',
    'PATH': os.path.join(os.environ['DARWIN_BROWSERDATA_PATH'], 'OmaServer.h5')
}
OMA_INSTANCE_NAME = os.getenv('OMA_INSTANCE', 'full').lower()
if OMA_INSTANCE_NAME == "":
    OMA_INSTANCE_NAME = "full"


# Maximum upload size for files: 50MB
MAX_UPLOAD_SIZE = 50*2**20


# Internationalization
# https://docs.djangoproject.com/en/1.6/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True

CONTACT_EMAIL = "contact@omabrowser.org"


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.6/howto/static-files/
STATIC_URL = '/static/'
if 'DARWIN_BROWSERSTATIC_PATH' in os.environ:
    STATIC_ROOT = os.environ['DARWIN_BROWSERSTATIC_PATH']
else:
    STATIC_ROOT = os.path.join(
        os.getenv('DARWIN_BROWSER_REPO_PATH',
                  os.path.join(os.path.expanduser("~"), "Browser")),
        "htdocs",
        "static")
MEDIA_URL = "/media/"
MEDIA_ROOT = os.getenv('DARWIN_BROWSERMEDIA_PATH', os.path.join(BASE_DIR, '../../media'))


# some jenkins specific modifications
if DEPLOYMENT == "CI-JENKINS":
    INSTALLED_APPS = INSTALLED_APPS + ['django_jenkins',]
    JENKINS_TASKS = (
        'django_jenkins.tasks.run_pep8',
        'django_jenkins.tasks.run_pyflakes',
    )
