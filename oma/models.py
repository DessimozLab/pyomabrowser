def format_sciname(sci, short=False):
    p = set([sci.find(x) for x in ['(', 'serogroup', 'serotype', 'serovar',
                                   'biotype', 'subsp', 'pv.', 'bv.']])
    if sci.startswith('Escherichia coli'):
        p.add(sci.find('O'))
    p.discard(-1)
    p = min(p) if len(p) > 0 else len(sci)
    return {'species': sci[0:p], 'strain': sci[p:]}


class LazyProperty(object):
    """Decorator to evaluate a property only on access.

    Compute the attribute value and caches it in the instance.
    Python Cookbook (Denis Otkidach) http://stackoverflow.com/users/168352/denis-otkidach
    This decorator allows you to create a property which can be computed once and
    accessed many times."""

    def __init__(self, method, name=None):
        # record the unbound-method and the name
        self.method = method
        self.name = name or method.__name__
        self.__doc__ = method.__doc__

    def __get__(self, inst, cls):
        if inst is None:
            return self
        # compute, cache and return the instance's attribute value
        result = self.method(inst)
        # setattr redefines the instance's attribute so this doesn't get called again
        setattr(inst, self.name, result)
        return result


class Singleton(type):
    """A meta-class to enforce a Singleton, e.g. a class that can be
    instantiated only exactly once.

    Modified from Python Cookbook, 3rd Edition, p 357ff.

    :Example:

        class Foo(metaclass=Singleton):
            def __init__(self):
                pass  #This part is executed only once
    """
    def __init__(self, *args, **kwargs):
        self.__instance = None
        super(Singleton, self).__init__(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        if self.__instance is None:
            self.__instance = super(Singleton, self).__call__(*args, **kwargs)
        return self.__instance


class ProteinEntry(object):
    def __init__(self, db, e):
        self._entry = e
        self._db = db

    @classmethod
    def from_entry_nr(cls, db, eNr):
        e = db.entry_by_entry_nr(eNr)
        return cls(db, e)

    @property
    def entry_nr(self):
        return int(self._entry['EntryNr'])

    @property
    def oma_group(self):
        return int(self._entry['OmaGroup'])

    @property
    def oma_hog(self):
        return self._entry['OmaHOG'].decode()

    @property
    def canonicalid(self):
        return self._entry['CanonicalId'].decode()

    @LazyProperty
    def genome(self):
        g = self._db.id_mapper['OMA'].genome_of_entry_nr(self._entry['EntryNr'])
        return Genome(self._db, g)

    @LazyProperty
    def omaid(self):
        return self._db.id_mapper['OMA'].map_entry_nr(self._entry['EntryNr'])

    @LazyProperty
    def cdna(self):
        return self._db.get_cdna(self._entry).decode()

    @LazyProperty
    def sequence(self):
        return self._db.get_sequence(self._entry).decode()

    @LazyProperty
    def description(self):
        return self._db.get_description(self._entry).decode()

    @LazyProperty
    def hog_family_nr(self):
        return self._db.hog_family(self._entry)

    def __repr__(self):
        return "<{}({}, {})>".format(self.__class__.__name__, self.entry_nr, self.omaid)


class Genome(object):
    def __init__(self, db, g):
        self._genome = g
        self._db = db

    @property
    def ncbi_taxon_id(self):
        return int(self._genome['NCBITaxonId'])

    @property
    def uniprot_species_code(self):
        return self._genome['UniProtSpeciesCode'].decode()

    @property
    def sciname(self):
        return self._genome['SciName'].decode()

    @LazyProperty
    def species_and_strain_as_dict(self):
        return format_sciname(self.sciname)

    def species(self):
        return self.species_and_strain_as_dict['species']

    def strain(self):
        return self.species_and_strain_as_dict['strain']

    @LazyProperty
    def kingdom(self):
        # TODO: store directly in db
        return self._db.tax.get_parent_taxa(self._genome['NCBITaxonId'])[-1]['Name'].decode()

    def is_polyploid(self):
        return self._genome['IsPolyploid']

    @LazyProperty
    def lineage(self):
        return [lev['Name'].decode() for lev in self._db.tax.get_parent_taxa(self._genome['NCBITaxonId'])]

    def __repr__(self):
        return "<{}({}, {})>".format(self.__class__.__name__, self.uniprot_species_code,
                                     self.ncbi_taxon_id)
