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
    url(r'^hogs/(?P<entry_id>\w+)/(?P<level>[A-Za-z0-9 _.()-]+)/$', views.HOGsView.as_view(),
        name='hogs'),
    url(r'^hogs/(?P<entry_id>\w+)/(?P<level>[A-Za-z0-9 _.()-]+)/fasta/$',
        views.HOGsFastaView.as_view(), name='hogs_fasta'),
    url(r'^hogs/(?P<entry_id>\w+)/(?P<level>[A-Za-z0-9 _.()-]+)/json/$',
        views.HOGsJson.as_view(), name='hog_json'),
    url(r'^hogs/(?P<entry_id>\w+)/(?P<level>[A-Za-z0-9 _.()-]+)/msa/$',
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
    url(r'^group/(?P<entry_id>\w+)/$', views.EntryCentricOMAGroup.as_view(), name="omagroup-entry"),
    url(r'^group/(?P<entry_id>\w+)/msa/$', views.EntryCentricOMAGroupMSA.as_view(), name="omagroup-entry-msa"),
    url(r'^omagroup/(?P<group_id>[A-Z0-9]+)/$', views.OMAGroup.as_view(), name='omagroup'),
    url(r'^omagroup/(?P<group_id>[A-Z0-9]+)/msa/$', views.OMAGroupMSA.as_view(), name='omagroup-msa'),
    url(r'^omagroup/(?P<group_id>[A-Z0-9]+)/fasta/$', views.OMAGroupFasta.as_view(), name='omagroup-fasta'),
    url(r'^omagroup/(?P<group_id>[A-Z0-9]+)/json/$', views.OMAGroupJson.as_view(), name='omagroup-json'),

    url(r'^export_markers', views.export_marker_genes, name='export_markers'),
    url(r'^markers/(?P<data_id>\w+)/$', views.MarkerGenesResults.as_view(), name='marker_genes'),
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
    url(r'^fellowship/thanks/', TemplateView.as_view(template_name='fellowship_thanks.html'), name='fellowship_thanks'),
    url(r'^suggestion/genome/$', views.genome_suggestion, name="genome_suggestion"),
    url(r'^suggestion/genome/thanks$', TemplateView.as_view(template_name="genome_suggestion_thanks.html"), name="genome_suggestion_thanks"),
    url(r'^functions/$', views.function_projection, name='function-projection-input'),
    url(r'^functions/(?P<data_id>\w+)/$', views.FunctionProjectionResults.as_view(), name="function-projection"),

    url(r'^release/$', views.Release.as_view(), name='release'),
    url(r'^release/json/$', views.GenomesJson.as_view(), name="genomes_json"),

    url(r'^current/$', views.CurrentView.as_view(), name='current'),
    url(r'^archives/$', views.ArchiveView.as_view(), name='archives'),
    url(r'^archives/(?P<release>[A-Za-z0-9.]+)/$', views.ArchiveView.as_view(), name='archives'),

    url(r'^dotplot/$', TemplateView.as_view(template_name="synteny_dotplot_genomeselection.html"), name='land_syntenyDP'),
    url(r'^dotplot/(?P<g1>[A-Z0-9]+)/(?P<g2>[A-Z0-9]+)/(?P<chr1>[A-Za-z0-9 _.()-]+)/(?P<chr2>[A-Za-z0-9 _.()-]+)/$',
        views.DotplotViewer, name='synteny_dotplot'),
    url(r'^dotplot/(?P<genome>[A-Za-z0-9 -]+)/json/$', views.ChromosomeJson.as_view(), name="chromosome_json"),
    url(r'^dotplot/(?P<org1>[A-Z0-9]+)/(?P<org2>[A-Z0-9]+)/(?P<chr1>[A-Za-z0-9 _.()-]+)/(?P<chr2>[A-Za-z0-9 _.()-]+)/json/$',
        views.HomologsBetweenChromosomePairJson.as_view(), name='synteny_chr_pair_json')
]

if settings.DEBUG:
    import debug_toolbar

    urlpatterns.extend([
        url(r'^__debug__/', include(debug_toolbar.urls)),
    ])
