from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^fastmapping/$', views.fastmapping, name='fastmapping'),
]
