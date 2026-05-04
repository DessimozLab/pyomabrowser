from django.urls import path
from . import views

urlpatterns = [
    path('export/', views.export_omastandalone, name='export'),
    path('export/<slug:data_id>/', views.StandaloneExportResultDownloader.as_view(), name="export-download"),
    path("fastoma-export/", views.export_fastoma, name="fastoma-export"),
    path("fastoma-export/<slug:data_id>/", views.FastOMAExportResultDownloader.as_view(), name="fastoma-export-download"),
]
