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


def search(request):
    # build a lookup table for the biological process terms for the autocomplete
    context = {'go_auto_data': GO_LOOKUP}
    if request.method == 'GET' and 'query' in request.GET:
        query = request.GET.get('query')
        try:
            goterm = utils.db.gene_ontology.term_by_id(query)
            if goterm.aspect != 1:  # not a BP term
                raise ValueError("Requested GO term '{}' is not part of the biological_process ontology".format(goterm))
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

            if len(res) == 0:
                def filter_existing_goterms(terms):
                    n = h5.get_node('/omamo/Summary')
                    for t in terms:
                        try:
                            dummy = next(n.where('GOnr == {}'.format(t.id)))
                            yield t
                        except StopIteration:
                            pass

                ic = {row['GOnr']: row['ic'] for row in h5.get_node('/ic')[:]}
                if ic[goterm.id] < 5:
                    # too low IC, report possible children terms
                    go = utils.db.gene_ontology
                    subterms = (t for t in go.get_subterms(goterm, max_steps=2) if ic.get(t.id, 0) >= 5)
                    context['suggested_go_terms'] = list(filter_existing_goterms(subterms))
                    context['suggest_reason'] = 'too general'
                else:
                    parent_terms = (t for t in utils.db.gene_ontology.get_superterms_incl_queryterm(goterm)
                                    if ic.get(t.id, 0) >= 5)
                    context['suggested_go_terms'] = list(filter_existing_goterms(parent_terms))
                    context['suggest_reason'] = "too specific"




        context['goterm'] = goterm
        context['result'] = res
        context['result_tab'] = ("suggested_go_terms" not in context) or (len(context['suggested_go_terms']) == 0)
    else:
        context['result_tab'] = False

    return render(request, "omamo_search.html", context)