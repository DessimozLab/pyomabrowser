from django.urls import path, include
from . import views

urlpatterns = [
    #path('search/', views.search, name='search')
    path('result/<slug:term>/',
        views.propose_modelorg, name="result"),
]



