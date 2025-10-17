from django.urls import re_path
from . import views

urlpatterns = [
    re_path(r'^taxmap/(?P<taxon>[\w _.()-/:-]+)/$', views.TaxonomyMapView.as_view(), name="taxmap"),
]
