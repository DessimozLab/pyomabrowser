import pyoma.browser.db
import django.conf

db = pyoma.browser.db.Database(django.conf.settings.HDF5DB['PATH'])
id_resolver = db.id_resolver
id_mapper = db.id_mapper
tax = db.tax
domain_source = pyoma.browser.db.DomainNameIdMapper(db)
