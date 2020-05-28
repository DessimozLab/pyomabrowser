import pyoma.browser.db
import pyoma.browser.models
import django.conf
import functools
import json
import os

db = pyoma.browser.db.Database(django.conf.settings.HDF5DB['PATH'])
id_resolver = db.id_resolver
id_mapper = db.id_mapper
tax = db.tax
domain_source = pyoma.browser.db.DomainNameIdMapper(db)

ProteinEntry = functools.partial(pyoma.browser.models.ProteinEntry, db)
Genome = functools.partial(pyoma.browser.models.Genome, db)
PairwiseRelation = functools.partial(pyoma.browser.models.PairwiseRelation, db)
GeneOntologyAnnotation = functools.partial(pyoma.browser.models.GeneOntologyAnnotation, db)


# approximate taxon search
taxon_json_list = json.load(open(os.path.join(os.environ['DARWIN_BROWSERDATA_PATH'], 'genomes.json'), 'r'))
values = []
maps_to = []

def browse_json(d, values, maps_to, cpt):

    for k, v in d.items():

        cpt += 1

        for key in {"id","name"}:
            if k == key and "children" in d.keys():
                values.append(v)
                maps_to.append(cpt)

        if k == 'children':
            for c in v:

                values, maps_to, cpt = browse_json(c, values, maps_to, cpt)
    return values, maps_to, cpt

values, maps_to, cpt = browse_json(taxon_json_list, values, maps_to, 1)

taxon_approx_search = pyoma.browser.db.FuzzyMatcher(values, maps_to, rel_sim_cutoff=0.6)
