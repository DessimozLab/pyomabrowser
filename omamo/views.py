from django.shortcuts import render
from django.conf import settings
from django.http import HttpResponseBadRequest
from oma import utils
import pandas
import logging
logger = logging.getLogger(__name__)


def uniq(seq):
    """return uniq elements of a list, preserving order
    :param seq: an iterable to be analyzed
    """
    seen = set()
    return [x for x in seq if not (x in seen or seen.add(x))]


def search(request):
    # build a lookup table for the biological process terms for the autocomplete
    go_lookup = [{'value': "{} - {}".format(val, val.name), 'data': val.id}
                 for key, val in utils.db.gene_ontology.terms.items() if val.aspect == 1]
    context = {'go_auto_data': go_lookup}
    if request.method == 'GET' and 'query' in request.GET:
        try:
            goterm = utils.db.gene_ontology.term_by_id(request.GET.get('query'))
        except ValueError as e:
            return HttpResponseBadRequest(str(e))
        df = pandas.read_csv(settings.OMAMO["CSV"], delimiter="\t", index_col=0)
        process = df[df["GO ID"] == goterm.id]
        res = []
        for rid, row in process.iterrows():
            row = row.to_dict()
            row['Human Genes'] = uniq(row['Human Genes'].split(","))
            row["Species Genes"] = uniq(row["Species Genes"].split(","))
            species = utils.Genome(utils.id_mapper['OMA'].genome_from_UniProtCode(row['Species']))
            row['taxon'] = species.species_and_strain_as_dict
            row['kingdom'] = species.kingdom
            res.append(row)
        context['goterm'] = goterm
        context['result'] = res
        context['result_tab'] = True
    else:
        context['result_tab'] = False

    return render(request, "omamo_search.html", context)