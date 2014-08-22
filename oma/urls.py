from django.conf.urls import patterns, url
from . import views
urlpatterns = patterns('',
          url(r'^pairs/(?P<entry_id>\w+)/$', views.pairs, name='index'),
        url(r'^hogs/(?P<entry_id>\w+)/(?P<level>\w+)/$', views.hogs, name='hogs'),
        url(r'^home/$', views.home, name='home'),
#        url(r'^synteny/(?P<entry_id>\w+)/(?P<windows>\w+)/$', views.synteny, name='synteny'),
)
