import itertools

import numpy
import tables
from django.shortcuts import render
from django.conf import settings
from django.http import HttpResponseBadRequest
from django.utils.html import escape
from oma import utils
import pandas
import logging
logger = logging.getLogger(__name__)

GO_LOOKUP = [{'value': "{} - {}".format(val, val.name), 'data': val.id}
             for key, val in utils.db.gene_ontology.terms.items() if val.aspect == 1]


def uniq(seq):
    """return uniq elements of a list, preserving order
    :param seq: an iterable to be analyzed
    """
    seen = set()
    return [x for x in seq if not (x in seen or seen.add(x))]


def search(request):
    # build a lookup table for the biological process terms for the autocomplete
    context = {'go_auto_data': GO_LOOKUP}
    if request.method == 'GET' and 'query' in request.GET:
        query = request.GET.get('query')
        try:
            goterm = utils.db.gene_ontology.term_by_id(query)
        except ValueError as e:
            return HttpResponseBadRequest(escape(str(e)))
        res = []
        with tables.open_file(settings.OMAMO["H5"]) as h5:
            sum_iter = h5.get_node("/omamo/Summary").where("GOnr == {}".format(goterm.id))
            details = h5.get_node("/omamo/detail").read_where("GOnr == {}".format(goterm.id))
            for row in sum_iter:
                details_for_species = details[numpy.where(details['Species'] == row['Species'])]
                species = utils.Genome(utils.id_mapper['OMA'].genome_from_UniProtCode(row['Species'].decode()))
                data = {"kingdom": species.kingdom,
                        "taxon": species.species_and_strain_as_dict,
                        "species": species.uniprot_species_code,
                        "nr_orthologs": int(row["NrOrthologs"]),
                        "function_sim": "{:.4f} ± {:.4f}".format(row['FuncSim_Mean'], row['FuncSim_Std']),
                        "score": row['Score'],
                        "human_genes": [{'enr': int(d['EntryNr']),
                                         'omaid': utils.db.id_mapper['OMA'].map_entry_nr(d['EntryNr']),
                                         'label': d['Label'].decode()}
                                        for d in details_for_species if d['Ref'] == 0],
                        "species_genes": [{'enr': int(d['EntryNr']),
                                           'omaid': utils.db.id_mapper['OMA'].map_entry_nr(d['EntryNr']),
                                           'label': d['Label'].decode()}
                                         for d in details_for_species if d['Ref'] == 1],
                        }
                res.append(data)

        context['goterm'] = goterm
        context['result'] = res
        context['result_tab'] = True
    else:
        context['result_tab'] = False

    return render(request, "omamo_search.html", context)