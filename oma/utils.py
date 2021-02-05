import pyoma.browser.db
import pyoma.browser.models
import django.conf
import functools
import os
import json


db = pyoma.browser.db.Database(django.conf.settings.HDF5DB['PATH'])
id_resolver = db.id_resolver
id_mapper = db.id_mapper
tax = db.tax
domain_source = pyoma.browser.db.DomainNameIdMapper(db)

ProteinEntry = functools.partial(pyoma.browser.models.ProteinEntry, db)
HOG = functools.partial(pyoma.browser.models.HOG, db)
Genome = functools.partial(pyoma.browser.models.Genome, db)
PairwiseRelation = functools.partial(pyoma.browser.models.PairwiseRelation, db)
GeneOntologyAnnotation = functools.partial(pyoma.browser.models.GeneOntologyAnnotation, db)


def load_genomes_json_file():
    for path in (os.getenv('DARWIN_BROWSERDATA_PATH'),
                 os.path.join(os.getenv('DARWIN_BROWSERDATA_PATH'),'..', 'downloads'),
                 os.getenv('DARWIN_BROWSERDATA_PATH'),
                 ""):
        fn = os.path.join(path, "genomes.json")
        if os.path.exists(fn):
            with open(fn, 'rb') as fh:
                data = json.load(fh)
            return data
    raise pyoma.browser.db.DBConsistencyError("cannot find \"genomes.json\" file.")