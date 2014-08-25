from django.conf.urls import patterns, url
from . import views
urlpatterns = patterns('',
          url(r'^pairs/(?P<entry_id>\w+)/$', views.pairs, name='index'),
        url(r'^hogs/(?P<entry_id>\w+)/(?P<level>\w+)/$', views.hogs, name='hogs'),
        url(r'^home/$', views.home, name='home'),
        url(r'^about/$', views.about, name='about'),
        url(r'^groupCV/$', views.groupCV, name='groupCV'),
        url(r'^landHOG/$', views.landHOG, name='landHOG'),
        url(r'^landAnnotation/$', views.landAnnotation, name='landAnnotation'),
        url(r'^landsynteny/$', views.landsynteny, name='landsynteny'),
        url(r'^team/$', views.team, name='team'),
        url(r'^funding/$', views.funding, name='funding'),
        url(r'^license/$', views.license, name='license'),
        url(r'^current/$', views.current, name='current'),
        url(r'^archives/$', views.archives, name='archives'),
        url(r'^APISOAP/$', views.APISOAP, name='APISOAP'),
        url(r'^APIDAS/$', views.APIDAS, name='APIDAS'),
        url(r'^type/$', views.type, name='type'),
        url(r'^uses/$', views.uses, name='uses'),
        url(r'^FAQ/$', views.FAQ, name='FAQ'),
        url(r'^genomePW/$', views.genomePW, name='genomePW'),
        url(r'^nutshell/$', views.nutshell, name='nutshell'),
        url(r'^dataset/$', views.dataset, name='dataset'),
        url(r'^landOMA/$', views.landOMA, name='landOMA'),
        url(r'^genomeCV/$', views.genomeCV, name='genomeCV'),





#        url(r'^synteny/(?P<entry_id>\w+)/(?P<windows>\w+)/$', views.synteny, name='synteny'),
)
