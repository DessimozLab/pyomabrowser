from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

# namespace for the API
app_name = 'oma_rest'

router = DefaultRouter()
router.register(r'protein', views.ProteinEntryViewSet, basename='protein')
router.register(r'group', views.OmaGroupViewSet, basename='group')
router.register(r'version', views.APIVersion, basename='version')
router.register(r'xref', views.XRefsViewSet, basename='xref')
router.register(r'genome', views.GenomeViewSet, basename='genome')
router.register(r'hog', views.HOGViewSet, basename='hog')
router.register(r'taxonomy', views.TaxonomyViewSet, basename='taxonomy')
router.register(r'synteny', views.SyntenyViewSet, basename="synteny")

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
    path('enrichment/', views.CreateEnrichmentAnalysisView.as_view(), name='enrichment-create'),
    path('enrichment/status/<slug:id>/', views.StatusEnrichmentAnalysisView.as_view(), name='enrichment-status'),
    path('schema/', SpectacularAPIView.as_view(versioning_class=None), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='oma_rest:schema'), name='swagger-ui'),
    path('docs/redoc/', SpectacularRedocView.as_view(url_name='oma_rest:schema'), name='redoc'),
]



