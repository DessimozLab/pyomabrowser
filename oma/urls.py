from django.conf import settings
from django.conf.urls import include, patterns, url
from . import views
urlpatterns = patterns('',
          url(r'^pairs/(?P<entry_id>\w+)/$', views.pairs, name='index'),
        url(r'^hogs/(?P<entry_id>\w+)/$', views.hogs, name='hogs'),
        url(r'^hogs/(?P<entry_id>\w+)/(?P<level>[A-Za-z0-9 -]+)/$', views.hogs, name='hogs'),
        url(r'^synteny/(?P<entry_id>\w+)/$', views.synteny, name='synteny'),
        url(r'^synteny/(?P<entry_id>\w+)/(?P<windows>\d)/$', views.synteny, name='synteny'),
        url(r'^synteny/(?P<entry_id>\w+)/(?P<mod>\d)/(?P<windows>\d)/$', 
            views.synteny, name='synteny'),
        url(r'^$', views.home),
        url(r'^home/$', views.home, name='home'),
        url(r'^about/$', views.about, name='about'),
        url(r'^export/$', views.export, name='export'),
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
        url(r'^seqCV/$', views.seqCV, name='seqCV'),
        url(r'^informationSeqCV/$', views.informationSeqCV, name='informationSeqCV'),
        url(r'^orthologsSeqCV/$', views.orthologsSeqCV, name='orthologsSeqCV'),
        url(r'^syntenySeqCV/$', views.syntenySeqCV, name='syntenySeqCV'),
        url(r'^HOGsSeqCV/$', views.HOGsSeqCV, name='HOGsSeqCV'),
        url(r'^OMAGSeqCV/$', views.OMAGSeqCV, name='OMAGSeqCV'),
        url(r'^alignGroupCV/$', views.alignGroupCV, name='alignGroupCV'),
        url(r'^closeGroupCV/$', views.closeGroupCV, name='closeGroupCV'),
        url(r'^ontologyGroupCV/$', views.ontologyGroupCV, name='ontologyGroupCV'),
        url(r'^proteinGroupCV/$', views.proteinGroupCV, name='proteinGroupCV'),
        url(r'^seqCVprotein/$', views.seqCVprotein, name='seqCVprotein'),
        url(r'^seqCValign/$', views.seqCValign, name='seqCValign'),
        url(r'^seqCVclose/$', views.seqCVclose, name='seqCVclose'),
        url(r'^seqCVontology/$', views.seqCVontology, name='seqCVontology'),
        url(r'^HOGCV/$', views.HOGCV, name='HOGCV'),
        url(r'^alignHOGCV/$', views.alignHOGCV, name='alignHOGCV'),
        url(r'^ontologyHOGCV/$', views.ontologyHOGCV, name='ontologyHOGCV'),
        url(r'^proteinHOGCV/$', views.proteinHOGCV, name='proteinHOGCV'),
        url(r'^seqCVproteinHOG/$', views.seqCVproteinHOG, name='seqCVproteinHOG'),
        url(r'^seqCValignHOG/$', views.seqCValignHOG, name='seqCValignHOG'),
        url(r'^seqCVontologyHOG/$', views.seqCVontologyHOG, name='seqCVontologyHOG'),
        url(r'^ArchivesJul2013/$', views.ArchivesJul2013, name='ArchivesJul2013'),
        url(r'^ArchivesDec2012/$', views.ArchivesDec2012, name='ArchivesDec2012'),
        url(r'^ArchivesMar2012/$', views.ArchivesMar2012, name='ArchivesMar2012'),
        url(r'^ArchivesMay2011/$', views.ArchivesMay2011, name='ArchivesMay2011'),
        url(r'^ArchivesNov2010/$', views.ArchivesNov2010, name='ArchivesNov2010'),
        url(r'^ArchivesMay2010/$', views.ArchivesMay2010, name='ArchivesMay2010'),
        url(r'^ArchivesOct2009/$', views.ArchivesOct2009, name='ArchivesOct2009'),
        url(r'^ArchivesApr2009/$', views.ArchivesApr2009, name='ArchivesApr2009'),






#        url(r'^synteny/(?P<entry_id>\w+)/(?P<windows>\w+)/$', views.synteny, name='synteny'),
)

if settings.DEBUG:
    import debug_toolbar
    urlpatterns += patterns('',
        url(r'^__debug__/', include(debug_toolbar.urls)),
    )

