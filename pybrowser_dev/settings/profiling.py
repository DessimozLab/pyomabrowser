from prod import *

INSTALLED_APPS.extend([
    "debug_toolbar",
])

MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")