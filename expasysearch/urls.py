from django.urls import path
from . import views

urlpatterns = [
    path('search/', views.expasy_search, name='expasy-search'),
    #path('', views.expasy_search),
]
