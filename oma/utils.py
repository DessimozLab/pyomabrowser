import pyoma.browser.db
import pyoma.browser.models
import django.conf
import functools

db = pyoma.browser.db.Database(django.conf.settings.HDF5DB['PATH'])
id_resolver = db.id_resolver
id_mapper = db.id_mapper
tax = db.tax
domain_source = pyoma.browser.db.DomainNameIdMapper(db)

ProteinEntry = functools.partial(pyoma.browser.models.ProteinEntry, db)
Genome = functools.partial(pyoma.browser.models.Genome, db)
PairwiseRelation = functools.partial(pyoma.browser.models.PairwiseRelation, db)
GeneOntologyAnnotation = functools.partial(pyoma.browser.models.GeneOntologyAnnotation, db)
