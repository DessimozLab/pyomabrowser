from django.conf import settings
from django.conf.urls import include, patterns, url
from django.views.generic.base import TemplateView
from . import views

urlpatterns = [
    url(r'^domains/(?P<entry_id>\w+)/json/$', views.domains_json, name='domains_json'),
    url(r'^hogs/(?P<entry_id>\w+)/$', views.HOGsView.as_view(), name='hogs'),
    url(r'^hogs/(?P<entry_id>\w+)/orthoxml/$', views.HOGsOrthoXMLView.as_view(),
        name='hogs_orthoxml'),
    url(r'^hogs/(?P<entry_id>\w+)/vis/$', views.HOGsVis.as_view(), name='hog_vis'),
    url(r'^hogs/(?P<entry_id>\w+)/vis0/$', views.HogVisWithoutInternalLabels.as_view(),
        name='hog_vis_no_internal_labels'),
    url(r'^hogs/(?P<entry_id>\w+)/(?P<level>[A-Za-z0-9 -]+)/$', views.HOGsView.as_view(),
        name='hogs'),
    url(r'^hogs/(?P<entry_id>\w+)/(?P<level>[A-Za-z0-9 -]+)/fasta/$',
        views.HOGsFastaView.as_view(), name='hogs_fasta'),
    url(r'^hogs/(?P<entry_id>\w+)/(?P<level>[A-Za-z0-9 -]+)/json/$',
        views.HOGsJson.as_view(), name='hog_json'),
    url(r'^hogs/(?P<entry_id>\w+)/(?P<level>[A-Za-z0-9 -]+)/msa/$',
        views.HOGsMSA.as_view(), name='hogs_msa'),
    url(r'^synteny/(?P<entry_id>\w+)/$', views.synteny, name='synteny'),
    url(r'^synteny/(?P<entry_id>\w+)/(?P<windows>\d)/$', views.synteny, name='synteny'),
    url(r'^synteny/(?P<entry_id>\w+)/(?P<mod>\d)/(?P<windows>\d)/$',
        views.synteny, name='synteny'),
    url(r'^info/(?P<entry_id>\w+)/fasta/$', views.InfoViewFasta.as_view(), name='entry_fasta'),
    url(r'^$', views.home),
    url(r'^home/$', views.home, name='home'),
    url(r'^vps/(?P<entry_id>\w+)/$', views.PairsView.as_view(), name="pairs"),
    url(r'^vps/(?P<entry_id>\w+)/fasta/$', views.PairsViewFasta.as_view(), name="pairs_fasta"),
    url(r'^vps/(?P<entry_id>\w+)/json/$', views.PairsJson.as_view(), name="pairs_json"),
    url(r'^export_markers', views.export_marker_genes, name='export_markers'),
    url(r'^markers/(?P<data_id>\w+)/$', views.marker_genes_retrieve_results, name='marker_genes'),
    # hogdata
    url(r'^hogdata/(?P<entry_id>\w+)/json', views.FamGeneDataJson.as_view(), name="fam_genedata"),
    # static pages that can be rendered directly to a template.
    url(r'^hogs/$', TemplateView.as_view(template_name='landHOG.html'), name='hogs'),
    url(r'^synteny/$', TemplateView.as_view(template_name='landsynteny.html'), name='synteny'),
    url(r'^about/$', TemplateView.as_view(template_name='about.html'), name='about'),
    url(r'^export/$', TemplateView.as_view(template_name='export.html'), name='export'),
    url(r'^landAnnotation/$', TemplateView.as_view(template_name='landAnnotation.html'),
        name='landAnnotation'),
    url(r'^team/$', TemplateView.as_view(template_name='team.html'), name='team'),
    url(r'^funding/$', TemplateView.as_view(template_name='funding.html'), name='funding'),
    url(r'^license/$', TemplateView.as_view(template_name='license.html'), name='license'),
    url(r'^APISOAP/$', TemplateView.as_view(template_name='APISOAP.html'), name='APISOAP'),
    url(r'^APIDAS/$', TemplateView.as_view(template_name='APIDAS.html'), name='APIDAS'),
    url(r'^type/$', TemplateView.as_view(template_name='type.html'), name='type'),
    url(r'^uses/$', TemplateView.as_view(template_name='uses.html'), name='uses'),
    url(r'^FAQ/$', TemplateView.as_view(template_name='FAQ.html'), name='FAQ'),
    url(r'^genomePW/$', TemplateView.as_view(template_name='genomePW.html'), name='genomePW'),
    url(r'^landOMA/$', TemplateView.as_view(template_name='landOMA.html'), name='landOMA'),
    url(r'^fellowship/$', views.fellowship, name="fellowship"),
    url(r'^thanks/', TemplateView.as_view(template_name='thanks.html'), name='thanks'),

    url(r'^release/$', views.release, name='release'),
    url(r'^release/json/$', views.GenomesJson.as_view(), name="genomes_json"),

    url(r'^current/$', views.CurrentView.as_view(), name='current'),
    url(r'^archives/$', views.ArchiveView.as_view(), name='archives'),
    url(r'^archives/(?P<release>[A-Za-z0-9.]+)/$', views.ArchiveView.as_view(), name='archives'),

    url(r'^syntenyDP/$', views.landDP, name='land_syntenyDP'),
    url(r'^syntenyDP/(?P<g1>[A-Za-z0-9 -]+)/(?P<g2>[A-Za-z0-9 -]+)/(?P<chr1>[A-Za-z0-9 -_%]+)/(?P<chr2>[A-Za-z0-9 -_%]+)$', views.DPviewer, name='syntenyDP'),
    url(r'^syntenyDP/json/(?P<genome>[A-Za-z0-9 -]+)/$', views.ChromosomeJson.as_view(), name="chromosome_json"),
]

if settings.DEBUG:
    import debug_toolbar

    urlpatterns.extend([
        url(r'^__debug__/', include(debug_toolbar.urls)),
    ])
