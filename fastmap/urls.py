from django.urls import path
from . import views

urlpatterns = [
    path('fastmapping/', views.fastmapping, name='fastmapping'),
    path('fastmapping/<slug:data_id>/', views.FastMappingResultDownloader.as_view(), name="fastmapping-download"),
]
