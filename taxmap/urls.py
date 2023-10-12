from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^taxmap/(?P<taxon>[\w _.()-/:-]+)/$', views.TaxonomyMapView.as_view(), name="taxmap"),
]
