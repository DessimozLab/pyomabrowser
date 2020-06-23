from .base import *

INSTALLED_APPS.extend([
    'bootstrap3',
])

# Maximum upload size for files: 100MB
MAX_UPLOAD_SIZE = 100*2**20