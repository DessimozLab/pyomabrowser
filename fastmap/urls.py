from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^fastmapping/$', views.fastmapping, name='fastmapping'),
    url(r'^fastmapping/(?P<data_id>\w+)/$', views.FastMappingResultDownloader.as_view(), name="fastmapping-download")

]
