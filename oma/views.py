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


