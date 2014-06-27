from django.conf.urls import patterns, url
from . import views
urlpatterns = patterns('',
        url(r'^pairs/(?P<entry_id>\w+)/$', views.pairs, name='index'),
)
