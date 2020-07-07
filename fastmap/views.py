from django.shortcuts import render
from . import views

# Create your views here.
def fastmapping(request):

    return render(request, "fastmapping.html")