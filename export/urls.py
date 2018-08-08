from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^export/$', views.export_omastandalone, name='export'),
    url(r'^export/(?P<data_id>\w+)/$', views.StandaloneExportResultDownloader.as_view(), name="export-download")
]
