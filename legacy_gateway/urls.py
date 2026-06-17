from django.urls import path

from . import views

# Mount this in the main urls.py with:
#   path("cgi-bin/gateway.pl", include("legacy_gateway.urls"))
# or directly:
#   path("cgi-bin/gateway.pl", views.gateway, name="legacy-gateway")

app_name = "legacy_gateway"

urlpatterns = [
    path("", views.gateway, name="gateway"),
]
