from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from rest_framework.schemas import get_schema_view
from rest_framework.documentation import include_docs_urls
from django.template.loader import render_to_string

router = DefaultRouter()
router.register(r'protein', views.ProteinEntryViewSet, base_name='protein')
router.register(r'group', views.OmaGroupViewSet, base_name='group')
router.register(r'version', views.APIVersion, base_name='version')
router.register(r'xref', views.XRefsViewSet, base_name='xref')
router.register(r'genome', views.GenomeViewSet, base_name='genome')
router.register(r'hog', views.HOGViewSet, base_name='hog')
router.register(r'taxonomy', views.TaxonomyViewSet, base_name='taxonomy')

# create docu-description from template
desc = render_to_string("oma_rest/documentation_description.html", {})
urlpatterns = [
    path('', include(router.urls)),
    path('pairs/<slug:genome_id1>/<slug:genome_id2>/',
        views.PairwiseRelationAPIView.as_view(), name='pairs'),
    path('pairs/<slug:genome_id1>/<slug:genome_id2>/minimal/',
        views.MinimalPairwiseRelation.as_view(), name="minimal-pairs"),
    path('summary/shared_ancestry/<slug:genome_id1>/<slug:genome_id2>/',
         views.SharedAncestrySummaryAPIView.as_view(), name='shared-ancestry-summary'),
    path('sequence/', views.IdentifiySequenceAPIView.as_view(), name='sequence'),
    path('function/', views.PropagateFunctionAPIView.as_view(), name='function-propagation'),
    path('schema/', get_schema_view(title="OMA REST API")),
    path('docs', include_docs_urls(title='REST API for the OMA Browser',
                                    description=desc)),
]



