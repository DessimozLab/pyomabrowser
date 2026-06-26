from django.urls import re_path

from . import views

urlpatterns = [
    # /All/<filename> — redirects to the "latest" release on Zenodo
    re_path(r'^All/(?P<filename>.+)$', views.download_latest, name='download_latest'),
    # /All.Mar2026/<filename> or /Plants.Mar2026/<filename> — specific release
    # Matches any <Type>.<Release>/<filename> where the directory name contains a dot.
    re_path(r'^(?P<release_name>[^/]+\.[^/]+)/(?P<filename>.+)$', views.download_release, name='download_release'),
]
