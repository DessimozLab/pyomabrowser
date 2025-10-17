from django.urls import path
from . import views

urlpatterns = [
    path('export/', views.export_omastandalone, name='export'),
    path('export/<slug:data_id>/', views.StandaloneExportResultDownloader.as_view(), name="export-download"),
]
