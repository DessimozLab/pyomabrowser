from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
import os

admin.autodiscover()

urlpatterns = [
    path('api/', include('oma_rest.urls')),
    path('oma/', include('oma.urls')),
]

if 'export' in settings.INSTALLED_APPS:
    urlpatterns.append(
        path('oma/', include('export.urls'))
    )
if 'fastmap' in settings.INSTALLED_APPS:
    urlpatterns.append(
        path('oma/', include('fastmap.urls'))
    )
if 'academy' in settings.INSTALLED_APPS:
    urlpatterns.append(
        path('oma/academy/', include('academy.urls'))
    )
if "omamo" in settings.INSTALLED_APPS:
    urlpatterns.append(
        path("oma/omamo/", include('omamo.urls'))
    )

if "expasysearch" in settings.INSTALLED_APPS:
    urlpatterns.append(
        path("oma/expasy/", include('expasysearch.urls'))
    )

if "mailman_subscribe" in settings.INSTALLED_APPS:
    urlpatterns.append(
        path("oma/", include('mailman_subscribe.urls'))
    )

if "taxmap" in settings.INSTALLED_APPS:
    urlpatterns.append(
        path("oma/", include("taxmap.urls"))
    )

if settings.DEPLOYMENT != "PRODUCTION":
    from django.views.generic.base import RedirectView
    from django.urls import re_path
    urlpatterns += [
        re_path(r'^$', RedirectView.as_view(url="/oma/home/", permanent=True)),
    ]
    try:
        import debug_toolbar
        if "debug_toolbar" in settings.INSTALLED_APPS:
            urlpatterns += [path('oma/__debug__/', include(debug_toolbar.urls))]
            print("found debug_toolbar")
    except ImportError:
        pass

    dwnld_folder = os.path.normpath(os.path.join(os.getenv('DARWIN_BROWSERDATA_PATH', default="./"), '..', 'downloads'))
    if not os.path.isdir(dwnld_folder):
        dwnld_folder = os.path.normpath(os.getenv('DARWIN_BROWSERDATA_PATH', default="./"))
    urlpatterns += static(r'All/', document_root=dwnld_folder)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

