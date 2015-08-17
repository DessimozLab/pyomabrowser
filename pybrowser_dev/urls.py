from django.conf import settings
from django.conf.urls import patterns, include, url
from django.conf.urls.static import static

from django.contrib import admin
import os

admin.autodiscover()

urlpatterns = patterns('',
    # Examples:
    # url(r'^$', 'pybrowser_dev.views.home', name='home'),
    # url(r'^blog/', include('blog.urls')),
    url(r'^oma/', include('oma.urls')),
)

if settings.DEPLOYMENT != "PRODUCTION":
    dwnld_folder = os.path.normpath(os.path.join(os.getenv('DARWIN_BROWSERDATA_PATH', default="./"), '..', 'downloads'))
    urlpatterns += static(r'All/', document_root=dwnld_folder)

