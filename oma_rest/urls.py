from django.conf.urls import url, include
from rest_framework.urlpatterns import format_suffix_patterns
from rest_framework.routers import DefaultRouter
from . import views
from rest_framework.schemas import get_schema_view

router = DefaultRouter()
router.register(r'protein', views.ProteinEntryViewSet, base_name='protein')
router.register(r'domain', views.ProteinDomains, base_name='domain')
router.register(r'group', views.OmaGroupViewSet, base_name='group')
router.register(r'version', views.APIVersion, base_name='version')
router.register(r'xref', views.XRefsViewSet, base_name='xref')

urlpatterns = [
    url(r'^', include(router.urls)),
    url(r'^schema/$', get_schema_view(title="OMA Rest API"))
]