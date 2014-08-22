from django.shortcuts import render
from django.http import HttpResponse, Http404

from . import utils

# Create your views here.

def pairs(request, entry_id, idtype='OMA'):
    
    entry_nr = utils.id_resolver.resolve(entry_id)
    vps_entry_nr = utils.db.get_vpairs(entry_nr)
    
    query = utils.id_mapper[idtype].map_entry_nr(entry_nr)
    vps = map(utils.id_mapper[idtype].map_entry_nr, vps_entry_nr['EntryNr2'])
    print(len(vps))
    context = {'query': query, 'vps':vps}
    
    return render(request, 'vpairs.html', context)

def hogs(request, entry_id, level, idtype='OMA'):
    entry_nr = utils.id_resolver.resolve(entry_id)
    query = utils.id_mapper[idtype].map_entry_nr(entry_nr)
    try:
        hog_members = utils.db.hog_members(entry_nr, level)
        print(hog_members)
        hog_member_ids = map(utils.id_mapper[idtype].map_entry_nr, hog_members['EntryNr'])
    except utils.Singleton:
        hog_member_ids = [query]
    except ValueError as e:
        raise Http404(e.message)
    context = {'query': query, 'level': level, 'hog_members': hog_member_ids} 
    return render(request, 'hogs.html', context)

def home(request):
    context = {}
    return render(request, 'home.html', context)

def about(request):
    context = {}
    return render(request, 'about.html', context)

def groupCV(request):
    context = {}
    return render(request, 'groupCV.html', context)

def landHOG(request):
    context = {}
    return render(request, 'landHOG.html', context)

def landAnnotation(request):
    context = {}
    return render(request, 'landAnnotation.html', context)


def landsynteny(request):
    context = {}
    return render(request, 'landsynteny.html', context)

def team(request):
    context = {}
    return render(request, 'team.html', context)

def funding(request):
    context = {}
    return render(request, 'funding.html', context)

def license(request):
    context = {}
    return render(request, 'license.html', context)

def current(request):
    context = {}
    return render(request, 'current.html', context)

def archives(request):
    context = {}
    return render(request, 'archives.html', context)

def APISOAP(request):
    context = {}
    return render(request, 'APISOAP.html', context)

def APIDAS(request):
    context = {}
    return render(request, 'APIDAS.html', context)

def type(request):
    context = {}
    return render(request, 'type.html', context)

def uses(request):
    context = {}
    return render(request, 'uses.html', context)

def FAQ(request):
    context = {}
    return render(request, 'FAQ.html', context)

def genomePW(request):
    context = {}
    return render(request, 'genomePW.html', context)

def nutshell(request):
    context = {}
    return render(request, 'nutshell.html', context)

def dataset(request):
    context = {}
    return render(request, 'dataset.html', context)


def landOMA(request):
    context = {}
    return render(request, 'landOMA.html', context)



