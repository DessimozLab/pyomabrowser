from django.conf.urls import url, include
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
    url(r'^', include(router.urls)),
    url(r'^pairs/(?P<genome_id1>\w+)/(?P<genome_id2>\w+)/$',
        views.PairwiseRelationAPIView.as_view(), name='pairs'),
    url(r'^pairs/(?P<genome_id1>\w+)/(?P<genome_id2>\w+)/minimal/$',
        views.MinimalPairwiseRelation.as_view(), name="minimal-pairs"),
    url(r'^sequence/$', views.IdentifiySequenceAPIView.as_view(), name='sequence'),
    url(r'^function/$', views.PropagateFunctionAPIView.as_view(), name='function-propagation'),
    url(r'^schema/$', get_schema_view(title="OMA REST API")),
    url(r'^docs', include_docs_urls(title='REST API for the OMA Browser',
                                    description=desc)),
]



