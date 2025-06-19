from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^export/$', views.export_omastandalone, name='export'),
    url(r'^export/(?P<data_id>\w+)/$', views.StandaloneExportResultDownloader.as_view(), name="export-download"),
    url(r"^fastoma-export/$", views.export_fastoma, name="fastoma-export"),
    url(r"^fastoma-export/(?P<data_id>\w+)/$", views.FastOMAExportResultDownloader.as_view(), name="fastoma-export-download"),
]
