from django.urls import path
from django.views.generic.base import TemplateView
from . import views

urlpatterns = [
    path('mailinglist-subscribe/', views.subscribe, name='mailman-subscribe'),
    path('mailinglist-subscribe/thanks', TemplateView.as_view(template_name="mailman_subscribe/thanks.html"),
         name="mailman-thanks"),
]
