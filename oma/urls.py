from django.conf import settings
from django.conf.urls import include, patterns, url
from django.views.generic.base import TemplateView
from . import views

urlpatterns = patterns('',
        #  url(r'^pairs/(?P<entry_id>\w+)/$', views.pairs, name='index'),
        url(r'^hogs/(?P<entry_id>\w+)/$', views.HOGsView.as_view(), name='hogs'),
        url(r'^hogs/(?P<entry_id>\w+)/(?P<level>[A-Za-z0-9 -]+)/$', views.HOGsView.as_view(), name='hogs'),
        url(r'^hogs/(?P<entry_id>\w+)/(?P<level>[A-Za-z0-9 -]+)/fasta/$', 
            views.HOGsFastaView.as_view(), name='hogs_fasta'),
        url(r'^synteny/(?P<entry_id>\w+)/$', views.synteny, name='synteny'),
        url(r'^synteny/(?P<entry_id>\w+)/(?P<windows>\d)/$', views.synteny, name='synteny'),
        url(r'^synteny/(?P<entry_id>\w+)/(?P<mod>\d)/(?P<windows>\d)/$', 
            views.synteny, name='synteny'),
        url(r'^$', views.home),
        url(r'^home/$', views.home, name='home'),

        # static pages that can be rendered directly to a template.
        url(r'^hogs/$', TemplateView.as_view(template_name='landHOG.html'), name='hogs'),
        url(r'^synteny/$', TemplateView.as_view(template_name='landsynteny.html'), name='synteny'),
        url(r'^about/$', TemplateView.as_view(template_name='about.html'), name='about'),
        url(r'^export/$', TemplateView.as_view(template_name='export.html'), name='export'),
        url(r'^landAnnotation/$', TemplateView.as_view(template_name='landAnnotation.html'), name='landAnnotation'),
        url(r'^team/$', TemplateView.as_view(template_name='team.html'), name='team'),
        url(r'^funding/$', TemplateView.as_view(template_name='funding.html'), name='funding'),
        url(r'^license/$', TemplateView.as_view(template_name='license.html'), name='license'),
        url(r'^current/$', TemplateView.as_view(template_name='current.html'), name='current'),
        url(r'^APISOAP/$', TemplateView.as_view(template_name='APISOAP.html'), name='APISOAP'),
        url(r'^APIDAS/$', TemplateView.as_view(template_name='APIDAS.html'), name='APIDAS'),
        url(r'^type/$', TemplateView.as_view(template_name='type.html'), name='type'),
        url(r'^uses/$', TemplateView.as_view(template_name='uses.html'), name='uses'),
        url(r'^FAQ/$', TemplateView.as_view(template_name='FAQ.html'), name='FAQ'),
        url(r'^genomePW/$', TemplateView.as_view(template_name='genomePW.html'), name='genomePW'),
        url(r'^landOMA/$', TemplateView.as_view(template_name='landOMA.html'), name='landOMA'),
        
        url(r'^archives/$', TemplateView.as_view(template_name='archives.html'), name='archives'),
        url(r'^ArchivesJul2013/$', views.ArchivesJul2013, name='ArchivesJul2013'),
        url(r'^ArchivesDec2012/$', views.ArchivesDec2012, name='ArchivesDec2012'),
        url(r'^ArchivesMar2012/$', views.ArchivesMar2012, name='ArchivesMar2012'),
        url(r'^ArchivesMay2011/$', views.ArchivesMay2011, name='ArchivesMay2011'),
        url(r'^ArchivesNov2010/$', views.ArchivesNov2010, name='ArchivesNov2010'),
        url(r'^ArchivesMay2010/$', views.ArchivesMay2010, name='ArchivesMay2010'),
        url(r'^ArchivesOct2009/$', views.ArchivesOct2009, name='ArchivesOct2009'),
        url(r'^ArchivesApr2009/$', views.ArchivesApr2009, name='ArchivesApr2009'),

)

if settings.DEBUG:
    import debug_toolbar
    urlpatterns += patterns('',
        url(r'^__debug__/', include(debug_toolbar.urls)),
    )

