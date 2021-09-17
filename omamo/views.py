import os.path

from django.shortcuts import render
from django.conf import settings
from oma import utils

import tables
import pandas
import os
import logging
logger = logging.getLogger(__name__)


# Create your views here.
def propose_modelorg(request, term):
    goterm = utils.db.gene_ontology.term_by_id(term)
    df = pandas.read_csv(settings.OMAMO["CSV"], delimiter="\t", index_col=0)
    process = df[df["GO ID"] == goterm.id]
    res = []
    for rid, row in process.iterrows():
        row = row.to_dict()
        row['Human Genes'] = row['Human Genes'].split(",")
        row["Species Genes"] = row["Species Genes"].split(",")
        species = utils.Genome(utils.id_mapper['OMA'].genome_from_UniProtCode(row['Species']))
        row['taxon'] = species.species_and_strain_as_dict
        row['kingdom'] = species.kingdom
        res.append(row)
    context = {'goterm': goterm,
               'result': res}
    return render(request, "omamo_result.html", context)

