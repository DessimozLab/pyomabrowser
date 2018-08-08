from django.conf import settings
from django.conf.urls import include, url
from django.conf.urls.static import static
from django.contrib import admin
import os

admin.autodiscover()

urlpatterns = [
    url(r'^api/', include('oma_rest.urls')),
    url(r'^oma/', include('oma.urls')),
    url(r'^oma/', include('export.urls'))
]

if settings.DEPLOYMENT != "PRODUCTION":
    from django.views.generic.base import RedirectView
    urlpatterns += [
        url(r'^$', RedirectView.as_view(url="/oma/home/", permanent=True))
    ]

    dwnld_folder = os.path.normpath(os.path.join(os.getenv('DARWIN_BROWSERDATA_PATH', default="./"), '..', 'downloads'))
    if not os.path.isdir(dwnld_folder):
        dwnld_folder = os.path.normpath(os.getenv('DARWIN_BROWSERDATA_PATH', default="./"))
    urlpatterns += static(r'All/', document_root=dwnld_folder)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

