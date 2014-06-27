from django.shortcuts import render
from django.http import HttpResponse

from . import utils

# Create your views here.

def pairs(request, entry_id, idtype='OMA'):
    
    entry_nr = utils.id_resolver.resolve(entry_id)
    vps_entry_nr = utils.db.get_vpairs(entry_nr)
    
    query = utils.get_id_mapper[idtype].map_entry_nr(entry_nr)
    vps = map(utils.get_id_mapper[idtype].map_entry_nr, vps_entry_nr['EntryNr2'])
    print(len(vps))
    context = {'query': query, 'vps':vps}
    
    return render(request, 'vpairs.html', context)


