from django.conf import settings
from django.conf.urls import include, url
from django.urls import path
from django.views.generic.base import TemplateView, RedirectView
from . import views

urlpatterns = [
    url(r'^home/$', views.home, name='home'),

    # Entry
    url(r'^vps/(?P<entry_id>\w+)/$', views.PairsView.as_view(), name="pairs"),
    url(r'^vps/(?P<entry_id>\w+)/fasta/$', views.PairsViewFasta.as_view(), name="pairs_fasta"),
    url(r'^vps/(?P<entry_id>\w+)/json/$', views.PairsJson.as_view(), name="pairs_json"),
    url(r'^vps/(?P<entry_id>\w+)/json_support/$', views.PairsJson_Support.as_view(), name="pairs_support_json"),
    url(r'^vps/(?P<entry_id>\w+)/json_support_sample/$', views.PairsJson_SupportSample.as_view(), name="pairs_support_sample_json"),
    url(r'^pps/(?P<entry_id>\w+)/json/$', views.ParalogsJson.as_view(), name="paralogs_json"),
    url(r'^pps/(?P<entry_id>\w+)/json_sample/$', views.ParalogsSampleJson.as_view(), name="paralogs_sample_json"),
    url(r'^pps/(?P<entry_id>\w+)/$', views.ParalogsView.as_view(), name="pair_paralogs"),
    url(r'^homeologs/(?P<entry_id>\w+)/json/$', views.HomeologsJson.as_view(), name="homeologs_json"),
    url(r'^homeologs/(?P<entry_id>\w+)/json_sample/$', views.HomeologsSampleJson.as_view(), name="homeologs_sample_json"),
    url(r'^homeologs/(?P<entry_id>\w+)/$', views.HomeologsView.as_view(), name="pair_homeologs"),
    url(r'^domains/(?P<entry_id>\w+)/json/$', views.domains_json, name='domains_json'),
    url(r'^synteny/(?P<entry_id>\w+)/$', views.LocalSyntenyView.as_view(), name='synteny'),
    url(r'^synteny/(?P<entry_id>\w+)/(?P<windows>\d)/$', views.LocalSyntenyView.as_view(), name='synteny'),
    url(r'^synteny/(?P<entry_id>\w+)/(?P<mod>\d)/(?P<windows>\d)/$', views.LocalSyntenyView.as_view(), name='synteny'),
    url(r'^info/(?P<entry_id>\w+)/$', views.EntryInfoView.as_view(), name='entry_info'),
    url(r'^info/(?P<entry_id>\w+)/fasta/$', views.InfoViewFasta.as_view(), name='entry_fasta'),
    url(r'^info/(?P<entry_id>\w+)/cds/fasta/$', views.InfoViewCDSFasta.as_view(), name='entry_cds'),
    # TODO: Are these 3 urls really needed?
    url(r'^info/(?P<entry_id>\w+)/go/$', views.Entry_GOA.as_view(), name="entry_goa"),
    url(r'^isoform/(?P<entry_id>\w+)/$', views.Entry_Isoform.as_view(), name="entry_isoform"),
    url(r'^isoform/(?P<entry_id>\w+)/json/$', views.IsoformsJson.as_view(), name="isoforms_json"),
    url(r'^sequences/(?P<entry_id>\w+)/$', views.Entry_sequences.as_view(), name="entry_sequences"),

    # HOG
    url(r'^hog/resolve/(?P<hog_id>HOG:[\w.:_]+)/$', views.resolve_hog_id, name="hog-resolve"),

    url(r'^hog/(?P<hog_id>[\w.:]+)/similar/domain/json/$', views.HOGDomainsJson.as_view(), name='hog_domains_json'),
    url(r'^hog/(?P<hog_id>[\w.:]+)/similar/domain/$', views.HOGSimilarDomain.as_view(), name='hog_similar_domain'),
    url(r'^hog/(?P<hog_id>[\w.:]+)/(?P<level>[A-Za-z0-9 _.()-/]+)/similar/domain/$', views.HOGSimilarDomain.as_view(), name='hog_similar_domain'),

    url(r'^hog/(?P<hog_id>[\w.:]+)/(?P<level>[A-Za-z0-9 _.()-/]+)/similar/profile/$', views.HOGSimilarProfile.as_view(), name='hog_similar_profile'),
    url(r'^hog/(?P<hog_id>[\w.:]+)/similar/profile/$', views.HOGSimilarProfile.as_view(), name='hog_similar_profile'),
    url(r'^hog/(?P<hog_id>[\w.:]+)/(?P<level>[A-Za-z0-9 _.()-/]+)/similar/profile/json/$', views.ProfileJson.as_view(), name='hog_similar_profile_json'),
    url(r'^hog/(?P<hog_id>[\w.:]+)/similar/profile/json/$', views.ProfileJson.as_view(), name='hog_similar_profile_json'),

    url(r'^hog/(?P<hog_id>[\w.:]+)/(?P<level>[A-Za-z0-9 _.()-/]+)/similar/pairwise/$', views.HOGSimilarPairwise.as_view(), name='hog_similar_pairwise'),
    url(r'^hog/(?P<hog_id>[\w.:]+)/similar/pairwise/$', views.HOGSimilarPairwise.as_view(), name='hog_similar_pairwise'),

    url(r'^hog/(?P<hog_id>[\w.:]+)/(?P<level>[A-Za-z0-9 _.()-/]+)/iham/$', views.HOGviewer.as_view(), name='hog_viewer'),
    url(r'^hog/(?P<hog_id>[\w.:]+)/iham/$', views.HOGviewer.as_view(), name='hog_viewer'),

    url(r'^hog/(?P<hog_id>[\w.:]+)/(?P<level>[A-Za-z0-9 _.()-/]+)/fasta/$', views.HOGFasta.as_view(), name='hog_fasta'),
    url(r'^hog/(?P<hog_id>[\w.:]+)/fasta/$', views.HOGFasta.as_view(), name='hog_fasta'),
    url(r'^hog/(?P<hog_id>[\w.:]+)/(?P<level>[A-Za-z0-9 _.()-/]+)/msa/$', views.HOGsMSA.as_view(), name='hog_msa'),
    url(r'^hog/(?P<hog_id>[\w.:]+)/msa/$', views.HOGsMSA.as_view(), name='hog_msa'),

    url(r'^hog/(?P<hog_id>[\w.:]+)/(?P<level>[A-Za-z0-9 _.()-/]+)/table/$', views.HOGtable.as_view(), name='hog_table'),
    url(r'^hog/(?P<hog_id>[\w.:]+)/table/$', views.HOGtable.as_view(), name='hog_table'),

    url(r'^hog/(?P<hog_id>[\w.:]+)/(?P<level>[A-Za-z0-9 _.()-/]+)/synteny/$', views.HOGSynteny.as_view(), name='hog_synteny'),
    url(r'^hog/(?P<hog_id>[\w.:]+)/synteny/$', views.HOGSynteny.as_view(), name='hog_synteny'),
    url(r'^hog/(?P<hog_id>[\w.:]+)/orthoxml/$', views.HOGsOrthoXMLView.as_view(), name="hogs_orthoxml"),

    url(r'^hog/(?P<hog_id>[\w.:]+)/(?P<level>[A-Za-z0-9 _.()-/]+)/info/$', views.HOGInfo.as_view(),
        name='hog_info'),
    url(r'^hog/(?P<hog_id>[\w.:]+)/info/$', views.HOGInfo.as_view(), name='hog_info'),
    url(r'^hog/(?P<hog_id>[\w.:]+)/(?P<level>[A-Za-z0-9 _.()-/]+)/$', views.HOGviewer.as_view(), name="hog_base"),
    url(r'^hog/(?P<hog_id>[\w.:]+)/$', views.HOGviewer.as_view(), name="hog_base"),

    #roothog
    url(r'^hogdata/(?P<entry_id>\w+)/json', views.FamGeneDataJsonFromEntry.as_view(), name="fam_genedata"),

    # OMA Group
    url(r'^group/(?P<group_id>\w+)/$', RedirectView.as_view(url="omagroup_members", permanent=False), name='omagroup-old'),
    url(r'^group/(?P<group_id>\w+)/omagroup_members/$', RedirectView.as_view(url="omagroup_members", permanent=True), name="omagroup-old2"),
    url(r'^omagroup/(?P<group_id>\w+)/$', views.OMAGroup_members.as_view(), name='omagroup_members_short'),
    url(r'^omagroup/(?P<group_id>\w+)/members/$', views.OMAGroup_members.as_view(), name='omagroup_members'),
    url(r'^omagroup/(?P<group_id>\w+)/similar/profile/$', views.OMAGroup_similar_profile.as_view(), name='omagroup_similar_profile'),
    url(r'^omagroup/(?P<group_id>\w+)/ontology/$', views.OMAGroup_ontology.as_view(), name='omagroup_ontology'),
    url(r'^omagroup/(?P<group_id>\w+)/similar/pairwise/$', views.OMAGroup_similar_pairwise.as_view(), name='omagroup_similar_pairwise'),
    url(r'^omagroup/(?P<group_id>\w+)/info/$', views.OMAGroup_info.as_view(), name='omagroup_info'),
    url(r'^omagroup/(?P<group_id>\w+)/alignment/$', views.OMAGroup_align.as_view(), name='omagroup_align'),
    url(r'^omagroup/(?P<group_id>[A-Z0-9]+)/msa/$', views.OMAGroup_align.as_view(), name='omagroup_align'),
    url(r'^omagroup/(?P<group_id>[A-Z0-9]+)/fasta/$', views.OMAGroupFasta.as_view(), name='omagroup-fasta'),
    url(r'^omagroup/(?P<group_id>[A-Z0-9]+)/json/$', views.OMAGroupJson.as_view(), name='omagroup-json'),

    # Genome
    url(r'^genome/(?P<species_id>\w+)/info/$', views.GenomeCentricInfo.as_view(), name='genome_info'),
    url(r'^genome/(?P<species_id>\w+)/genes/$', views.GenomeCentricGenes.as_view(), name='genome_genes'),
    url(r'^genome/(?P<species_id>\w+)/closest/groups/$', views.GenomeCentricClosestGroups.as_view(), name='genome_closest_og'),
    url(r'^genome/(?P<species_id>\w+)/closest/hogs/$', views.GenomeCentricClosestHOGs.as_view(), name='genome_closest_hog'),
    url(r'^genome/(?P<species_id>\w+)/synteny/$', views.GenomeCentricSynteny.as_view(), name='genome_synteny'),

    # AncestralGenome
    url(r'^ancestralgenome/(?P<species_id>[A-Za-z0-9 _.:,()/-]+)/info/$', views.AncestralGenomeCentricInfo.as_view(), name='ancestralgenome_info'),
    url(r'^ancestralgenome/(?P<species_id>[A-Za-z0-9 _.:,()/-]+)/genes/$', views.AncestralGenomeCentricGenes.as_view(), name='ancestralgenome_genes'),

    # HOG via Entry (from external resources)
    url(r'^hogs/(?P<entry_id>\w+)/$', views.HOGtableFromEntry.as_view(), name='hog_table_from_entry'),
    url(r'^hogs/(?P<entry_id>\w+)/vis/$', views.HOGiHamFromEntry.as_view(), name='hog_viewer_from_entry'),
    url(r'^hogs/(?P<entry_id>\w+)/iham/$', views.HOGiHamFromEntry.as_view(), name='hog_viewer_from_entry'),
    url(r'^hogs/(?P<entry_id>\w+)/(?P<level>[A-Za-z0-9 _.()-]+)/$',
        views.HOGtableFromEntry.as_view(), name='hog_table_from_entry'),

    #not sure if those are still needed somewhere. keep for now.
    url(r'^hogs/(?P<entry_id>\w+)/domains/$',
        views.HOGDomainsView.as_view(), name='hog_domains_'),
    url(r'^hogs/(?P<entry_id>\w+)/domains/json$',
        views.HOGDomainsJson.as_view(), name='hog_domains_json_'),


    # Search Widget
    url(r'^search/$', views.Searcher.as_view(), name='search'),
    url(r'^search/fulltext/(?P<query>[A-Za-z0-9 _.:()-/+"]+)/$', views.FullTextJson.as_view(), name="fulltext_json"),

    url(r'^export_markers', views.export_marker_genes, name='export_markers'),
    url(r'^markers/(?P<data_id>\w+)/$', views.MarkerGenesResults.as_view(), name='marker_genes'),

    # static pages that can be rendered directly to a template.
    url(r'^hogs/$', TemplateView.as_view(template_name='explore_HOG.html'), name='hogs'),
    url(r'^synteny/$', TemplateView.as_view(template_name='explore_synteny.html'), name='synteny'),

    url(r'^glossary/$', TemplateView.as_view(template_name='glossary.html'), name='glossary'),
    url(r'^homologs/$', TemplateView.as_view(template_name='help_homologs.html'), name='homologs'),
    url(r'^about/$', TemplateView.as_view(template_name='about_OMA.html'), name='about'),
    #url(r'^export_selection/$', TemplateView.as_view(template_name='dlOMA_exportAllAll.html'), name='export'),
    url(r'^landAnnotation/$', TemplateView.as_view(template_name='explore_Annotation.html'),
        name='landAnnotation'),
    url(r'^team/$', TemplateView.as_view(template_name='about_team.html'), name='team'),
    url(r'^funding/$', TemplateView.as_view(template_name='about_funding.html'), name='funding'),
    url(r'^license/$', TemplateView.as_view(template_name='about_license.html'), name='license'),
    url(r'^APISOAP/$', TemplateView.as_view(template_name='dlSoft_SOAP.html'), name='APISOAP'),
    url(r'^APIDAS/$', TemplateView.as_view(template_name='APIDAS.html'), name='APIDAS'),
    url(r'^type/$', TemplateView.as_view(template_name='help_typesOrthologs.html'), name='type'),
    url(r'^uses/$', TemplateView.as_view(template_name='help_typicalUses.html'), name='uses'),
    url(r'^FAQ/$', TemplateView.as_view(template_name='help_FAQ.html'), name='FAQ'),
    url(r'^genomePW/$', TemplateView.as_view(template_name='tool_genomePW.html'), name='genomePW'),
    url(r'^landOMA/$', TemplateView.as_view(template_name='explore_omaGroup.html'), name='landOMA'),

    url(r'^functions/$', views.function_projection, name='function-projection-input'),
    url(r'^functions/(?P<data_id>\w+)/$', views.FunctionProjectionResults.as_view(), name="function-projection"),

    url(r'^release/$', views.Release.as_view(), name='release'),
    url(r'^release/json/$', views.GenomesJson.as_view(), name="genomes_json"),

    url(r'^current/$', views.CurrentView.as_view(), name='current'),
    url(r'^archives/$', views.ArchiveView.as_view(), name='archives'),
    url(r'^archives/(?P<release>[A-Za-z0-9.]+)/$', views.ArchiveView.as_view(), name='archives'),

    url(r'^dotplot/$', TemplateView.as_view(template_name="tool_synteny_dotplot_genomeselection.html"), name='land_syntenyDP'),
    url(r'^dotplot/(?P<g1>[A-Z0-9]+)/(?P<g2>[A-Z0-9]+)/(?P<chr1>[A-Za-z0-9 _.()-]+)/(?P<chr2>[A-Za-z0-9 _.()-]+)/$',
        views.DotplotViewer, name='synteny_dotplot'),
    url(r'^dotplot/(?P<genome>[A-Za-z0-9 -]+)/json/$', views.ChromosomeJson.as_view(), name="chromosome_json"),
    url(r'^dotplot/(?P<org1>[A-Z0-9]+)/(?P<org2>[A-Z0-9]+)/(?P<chr1>[A-Za-z0-9 _.()-]+)/(?P<chr2>[A-Za-z0-9 _.()-]+)/json/$',
        views.HomologsBetweenChromosomePairJson.as_view(), name='synteny_chr_pair_json'),
    url(r'^tools/$', TemplateView.as_view(template_name='tool_catalog.html'), name='tool_catalog'),
]

if settings.OMA_INSTANCE_NAME != "basf":
    urlpatterns.extend([
        url(r'^fellowship/$', views.fellowship, name="fellowship"),
        url(r'^fellowship/thanks/', TemplateView.as_view(template_name='fellowship_thanks.html'),
            name='fellowship_thanks'),
        url(r'^suggestion/genome/$', views.genome_suggestion, name="genome_suggestion"),
        url(r'^suggestion/genome/thanks$', TemplateView.as_view(template_name="help_genome_suggestion_thanks.html"),
            name="genome_suggestion_thanks"),
    ])

if settings.DEBUG:
    try:
        import debug_toolbar
        urlpatterns.extend([
            url(r'^__debug__/', include(debug_toolbar.urls)),
        ])
    except ImportError:
        pass
