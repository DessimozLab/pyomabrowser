from django.conf import settings
from django.urls import path, re_path, register_converter
from django.views.generic.base import TemplateView, RedirectView
from . import url_converter, views

register_converter(url_converter.LevelConverter, 'lev')
register_converter(url_converter.HogIdConverter, 'hog')


urlpatterns = [
    path('home/', views.home, name='home'),

    # Entry
    path('vps/<entry_id>/', views.PairsView.as_view(), name="pairs"),
    path('vps/<entry_id>/fasta/', views.PairsViewFasta.as_view(), name="pairs_fasta"),
    path('vps/<entry_id>/json_support/', views.PairsJson_Support.as_view(), name="pairs_support_json"),
    path('vps/<entry_id>/json_support_sample/', views.PairsJson_SupportSample.as_view(), name="pairs_support_sample_json"),
    path('pps/<entry_id>/json/', views.ParalogsJson.as_view(), name="paralogs_json"),
    path('pps/<entry_id>/json_sample/', views.ParalogsSampleJson.as_view(), name="paralogs_sample_json"),
    path('pps/<entry_id>/', views.ParalogsView.as_view(), name="pair_paralogs"),
    path('homeologs/<entry_id>/json/', views.HomeologsJson.as_view(), name="homeologs_json"),
    path('homeologs/<entry_id>/json_sample/', views.HomeologsSampleJson.as_view(), name="homeologs_sample_json"),
    path('homeologs/<entry_id>/', views.HomeologsView.as_view(), name="pair_homeologs"),
    path('domains/<entry_id>/json/', views.domains_json, name='domains_json'),
    path('synteny/<entry_id>/', views.LocalSyntenyView.as_view(), name='synteny'),
    path('synteny/<entry_id>/<int:windows>/', views.LocalSyntenyView.as_view(), name='synteny'),
    path('synteny/<entry_id>/<int:mod>/<int:windows>/', views.LocalSyntenyView.as_view(), name='synteny'),
    path('info/<entry_id>/', views.EntryInfoView.as_view(), name='entry_info'),
    path('info/<entry_id>/fasta/', views.InfoViewFasta.as_view(), name='entry_fasta'),
    path('info/<entry_id>/cds/fasta/', views.InfoViewCDSFasta.as_view(), name='entry_cds'),
    path('info/<entry_id>/go/', views.Entry_GOA.as_view(), name="entry_goa"),
    path('isoform/<entry_id>/', views.Entry_Isoform.as_view(), name="entry_isoform"),
    path('isoform/<entry_id>/json/', views.IsoformsJson.as_view(), name="isoforms_json"),
    path('sequences/<entry_id>/', views.Entry_sequences.as_view(), name="entry_sequences"),
    path('structure/<entry_id>/', views.EntryStructure.as_view(), name="entry_structure"),
    path('structure/<entry_id>/fasta/', views.EntryStructureFasta.as_view(), name="entry_structure_fasta"),

    # HOG
    path('hog/resolve/<hog:hog_id>/', views.resolve_hog_id, name="hog-resolve"),

    path('hog/<hog:hog_id>/similar/domain/json/', views.HOGDomainsJson.as_view(), name='hog_domains_json'),
    path('hog/<hog:hog_id>/similar/domain/', views.HOGSimilarDomain.as_view(), name='hog_similar_domain'),
    path('hog/<hog:hog_id>/<lev:level>/similar/domain/', views.HOGSimilarDomain.as_view(), name='hog_similar_domain'),

    path('hog/<hog:hog_id>/<lev:level>/similar/profile/', views.HOGSimilarProfile.as_view(), name='hog_similar_profile'),
    path('hog/<hog:hog_id>/similar/profile/', views.HOGSimilarProfile.as_view(), name='hog_similar_profile'),
    path('hog/<hog:hog_id>/<lev:level>/similar/profile/json/', views.ProfileJson.as_view(), name='hog_similar_profile_json'),
    path('hog/<hog:hog_id>/similar/profile/json/', views.ProfileJson.as_view(), name='hog_similar_profile_json'),

    path('hog/<hog:hog_id>/<lev:level>/similar/pairwise/', views.HOGSimilarPairwise.as_view(), name='hog_similar_pairwise'),
    path('hog/<hog:hog_id>/similar/pairwise/', views.HOGSimilarPairwise.as_view(), name='hog_similar_pairwise'),
    path('hog/<hog:hog_id>/<lev:level>/similar/pairwise/json/',views.HOGSimilarPairwiseJSON.as_view(), name='hog_similar_pairwise_json'),
    path('hog/<hog:hog_id>/similar/pairwise/json/', views.HOGSimilarPairwiseJSON.as_view(), name='hog_similar_pairwise_json'),

    path('hog/<hog:hog_id>/<lev:level>/iham/', views.HOGviewer.as_view(), name='hog_viewer'),
    path('hog/<hog:hog_id>/iham/', views.HOGviewer.as_view(), name='hog_viewer'),

    path('hog/<hog:hog_id>/<lev:level>/go/', views.HOGgo.as_view(), name='hog_go'),
    path('hog/<hog:hog_id>/go/', views.HOGgo.as_view(), name='hog_go'),

    path('hog/<hog:hog_id>/<lev:level>/fasta/', views.HOGFasta.as_view(), name='hog_fasta'),
    path('hog/<hog:hog_id>/fasta/', views.HOGFasta.as_view(), name='hog_fasta'),
    path('hog/<hog:hog_id>/<lev:level>/3di-fasta/', views.HOG3diFasta.as_view(), name='hog_3di_fasta'),
    path('hog/<hog:hog_id>/3di-fasta/', views.HOG3diFasta.as_view(), name='hog_3di_fasta'),
    path('hog/<hog:hog_id>/<lev:level>/msa/', views.HOGsMSA.as_view(), name='hog_msa'),
    path('hog/<hog:hog_id>/msa/', views.HOGsMSA.as_view(), name='hog_msa'),
    path('hog/<hog:hog_id>/<lev:level>/structure-msa/', views.HOGsStructureMSA.as_view(), name='hog_msa_structure'),
    path('hog/<hog:hog_id>/structure-msa/', views.HOGsStructureMSA.as_view(), name='hog_msa_structure'),

    path('hog/<hog:hog_id>/<lev:level>/table/', views.HOGtable.as_view(), name='hog_table'),
    path('hog/<hog:hog_id>/table/', views.HOGtable.as_view(), name='hog_table'),

    path('hog/<hog:hog_id>/<lev:level>/synteny/', views.HOGSynteny.as_view(), name='hog_synteny'),
    path('hog/<hog:hog_id>/synteny/', views.HOGSynteny.as_view(), name='hog_synteny'),
    path('hog/<hog:hog_id>/orthoxml/', views.HOGsOrthoXMLView.as_view(), name="hogs_orthoxml"),
    path('hog/<hog:hog_id>/orthoxml/<file_type>/', views.HOGsOrthoXMLView.as_view(), name="hogs_orthoxml"),

    path('hog/<hog:hog_id>/<lev:level>/matreex/', views.Matreex.as_view(), name='matreex'),
    path('hog/<hog:hog_id>/matreex/json/', views.MatreexJson.as_view(), name='matreex-json'),
    path('hog/<hog:hog_id>/matreex/', views.Matreex.as_view(), name='matreex'),


    path('hog/<hog:hog_id>/<lev:level>/info/', views.HOGInfo.as_view(),
        name='hog_info'),
    path('hog/<hog:hog_id>/info/', views.HOGInfo.as_view(), name='hog_info'),
    path('hog/<hog:hog_id>/<lev:level>/', views.HOGviewer.as_view(), name="hog_base"),
    path('hog/<hog:hog_id>/', views.HOGviewer.as_view(), name="hog_base"),

    #roothog
    path('hogdata/<entry_id>/json', views.FamGeneDataJsonFromEntry.as_view(), name="fam_genedata"),

    # OMA Group
    path('group/<group_id>/', RedirectView.as_view(pattern_name="omagroup_members", permanent=False), name='omagroup-old'),
    path('group/<group_id>/omagroup_members/', RedirectView.as_view(pattern_name="omagroup_members", permanent=False), name="omagroup-old2"),
    path('omagroup/<group_id>/', views.OMAGroup_members.as_view(), name='omagroup_members_short'),
    path('omagroup/<group_id>/members/', views.OMAGroup_members.as_view(), name='omagroup_members'),
    path('omagroup/<group_id>/similar/profile/', views.OMAGroup_similar_profile.as_view(), name='omagroup_similar_profile'),
    path('omagroup/<group_id>/ontology/', views.OMAGroup_ontology.as_view(), name='omagroup_ontology'),
    path('omagroup/<group_id>/similar/pairwise/', views.OMAGroup_similar_pairwise.as_view(), name='omagroup_similar_pairwise'),
    path('omagroup/<group_id>/info/', views.OMAGroup_info.as_view(), name='omagroup_info'),
    path('omagroup/<group_id>/alignment/', views.OMAGroup_align.as_view(), name='omagroup_align'),
    path('omagroup/<group_id>/msa/', views.OMAGroup_align.as_view(), name='omagroup_align'),
    path('omagroup/<group_id>/fasta/', views.OMAGroupFasta.as_view(), name='omagroup-fasta'),
    path('omagroup/<group_id>/json/', views.OMAGroupJson.as_view(), name='omagroup-json'),

    # Genome
    path('genome/', views.GenomeResolve.as_view(), name="genome"),
    path('genome/<lev:species_id>/info/', views.GenomeCentricInfo.as_view(), name='genome_info'),
    path('genome/<lev:species_id>/chromosome/', views.GenomeCentricChromosome.as_view(), name='genome_chromosome'),
    path('genome/<lev:species_id>/genes/', views.GenomeCentricGenes.as_view(), name='genome_genes'),
    path('genome/<lev:species_id>/closest/groups/', views.GenomeCentricClosestGroups.as_view(), name='genome_closest_og'),
    path('genome/<lev:species_id>/closest/hogs/', views.GenomeCentricClosestHOGs.as_view(), name='genome_closest_hog'),
    path('genome/<lev:species_id>/synteny/', views.GenomeCentricSynteny.as_view(), name='genome_synteny'),
    path('genome/<lev:species_id>/geneorder/', views.GenomeCentricGeneOrder.as_view(), name='genome_gene_order'),

    # AncestralGenome
    path('ancestralgenome/<lev:species_id>/info/', views.AncestralGenomeCentricInfo.as_view(), name='ancestralgenome_info'),
    path('ancestralgenome/<lev:species_id>/synteny/', views.AncestralGenomeCentricSynteny.as_view(), name='ancestralgenome_synteny'),
    path('ancestralgenome/<lev:species_id>/genes/<lev:level>/', views.AncestralGenomeCentricGenes.as_view(), name='ancestralgenome_genes'),
    path('ancestralgenome/<lev:species_id>/genes/', views.AncestralGenomeCentricGenes.as_view(), name='ancestralgenome_genes'),
    path('ancestralgenome/<lev:species_id>/chromosome/', views.AncestralGenomeCentricChromosome.as_view(), name='ancestralgenome_chromosome'),

    # HOG via Entry (from external resources)
    path('hogs/<entry_id>/', views.HOGtableFromEntry.as_view(), name='hog_table_from_entry'),
    path('hogs/<entry_id>/vis/', views.HOGiHamFromEntry.as_view(), name='hog_viewer_from_entry'),
    path('hogs/<entry_id>/iham/', views.HOGiHamFromEntry.as_view(), name='hog_viewer_from_entry'),
    path('hogs/<entry_id>/<lev:level>/', views.HOGtableFromEntry.as_view(), name='hog_table_from_entry'),

    #not sure if those are still needed somewhere. keep for now.
    path('hogs/<entry_id>/domains/',views.HOGDomainsView.as_view(), name='hog_domains_'),
    path('hogs/<entry_id>/domains/json',views.HOGDomainsJson.as_view(), name='hog_domains_json_'),


    # Search Widget
    path('search-token/', views.token_search, name='search_token'),
    path('search-token/thanks/', TemplateView.as_view(template_name="search_suggestion_thanks.html"),
            name="search_suggestion_thanks"),

    path('search/', views.Searcher.as_view(), name='search'),
    # path('search/fulltext/<query>[A-Za-z0-9 _.:()-/+"]+)/', views.FullTextJson.as_view(), name="fulltext_json"),

    # Async job status
    path('jobs/msa/<job_hash>/', views.MSAStatus.as_view(), name='msa-status'),

    path('export_markers/', views.ExportMarkerGenes.as_view(), name='export_markers'),
    path('markers/<data_id>/', views.MarkerGenesResults.as_view(), name='marker_genes'),

    # static pages that can be rendered directly to a template.
    path('hogs/', TemplateView.as_view(template_name='explore_HOG.html'), name='hogs'),
    path('synteny/', TemplateView.as_view(template_name='explore_synteny.html'), name='synteny'),

    path('glossary/', TemplateView.as_view(template_name='glossary.html'), name='glossary'),
    path('homologs/', TemplateView.as_view(template_name='help_homologs.html'), name='homologs'),
    path('about/', TemplateView.as_view(template_name='about_OMA.html'), name='about'),
    #path('export_selection/', TemplateView.as_view(template_name='dlOMA_exportAllAll.html'), name='export'),
    path('landAnnotation/', TemplateView.as_view(template_name='explore_Annotation.html'),
        name='landAnnotation'),
    path('team/', TemplateView.as_view(template_name='about_team.html'), name='team'),
    path('sab/', TemplateView.as_view(template_name='about_sab.html'), name='sab'),
    path('funding/', TemplateView.as_view(template_name='about_funding.html'), name='funding'),
    path('license/', RedirectView.as_view(pattern_name="license"), name='red-license'),
    path('terms_of_use/', TemplateView.as_view(template_name='about_license.html'), name='license'),
    path('type/', TemplateView.as_view(template_name='help_typesOrthologs.html'), name='type'),
    path('uses/', TemplateView.as_view(template_name='help_typicalUses.html'), name='uses'),
    path('FAQ/', TemplateView.as_view(template_name='help_FAQ.html'), name='FAQ'),
    path('genomePW/', TemplateView.as_view(template_name='tool_genomePW.html'), name='genomePW'),
    path('landOMA/', TemplateView.as_view(template_name='explore_omaGroup.html'), name='landOMA'),

    path('functions/', views.FunctionProjection.as_view(), name='function-projection-input'),
    path('functions/<data_id>/', views.FunctionProjectionResults.as_view(), name="function-projection"),

    path('go_enrichment/', views.go_enrichment , name='go_enrichment'),
    path('go_enrichment_result/<uuid:data_id>/', views.go_enrichment_result , name='go_enrichment_result'),

    path('release/', views.Release.as_view(), name='release'),
    path('release/json/', views.GenomesJson.as_view(), name="genomes_json"),

    path('phylostratigraphy/', TemplateView.as_view(template_name='phylostratigraphy.html'), name='phylostratigraphy'),
    path("speciestree/<slug:root_id>.phyloxml", views.PhyloXMLSpeciesTreeView.as_view(), name="speciestree-phyloxml"),

    path('current/', views.CurrentView.as_view(), name='current'),
    path('archives/', views.ArchiveView.as_view(), name='archives'),
    path('archives/<release>/', views.ArchiveView.as_view(), name='archives'),

    path('dotplot/', TemplateView.as_view(template_name="tool_synteny_dotplot_genomeselection.html"), name='land_syntenyDP'),
    re_path(r'dotplot/(?P<g1>[A-Z0-9]+)/(?P<g2>[A-Z0-9]+)/(?P<chr1>[A-Za-z0-9 _.()-]+)/(?P<chr2>[A-Za-z0-9 _.()-]+)/$',
        views.DotplotViewer, name='synteny_dotplot'),
    path('dotplot/(<lev:genome>/json/', views.ChromosomeJson.as_view(), name="chromosome_json"),
    re_path(r'dotplot/(?P<org1>[A-Z0-9]+)/(?P<org2>[A-Z0-9]+)/(?P<chr1>[A-Za-z0-9 _.()-]+)/(?P<chr2>[A-Za-z0-9 _.()-]+)/json/$',
        views.HomologsBetweenChromosomePairJson.as_view(), name='synteny_chr_pair_json'),
    path('tools/', TemplateView.as_view(template_name='tool_catalog.html'), name='tool_catalog'),
    path("health/", views.health_check, name="health_check"),
]

if settings.OMA_INSTANCE_NAME != "basf":
    urlpatterns.extend([
        path('fellowship/', views.fellowship, name="fellowship"),
        path('fellowship/thanks/', TemplateView.as_view(template_name='fellowship_thanks.html'),
            name='fellowship_thanks'),
        path('suggestion/genome/', views.genome_suggestion, name="genome_suggestion"),
        path('suggestion/genome/thanks', TemplateView.as_view(template_name="help_genome_suggestion_thanks.html"),
            name="genome_suggestion_thanks"),
    ])

if settings.DEBUG:
    try:
        import debug_toolbar
        #urlpatterns.extend([
        #    url(r'^__debug__/', include(debug_toolbar.urls)),
        #])
    except ImportError:
        pass
