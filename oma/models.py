from . import utils
from . import misc


class ProteinEntry(object):
    def __init__(self, e):
        self._entry = e

    @classmethod
    def from_entry_nr(cls, eNr):
        e = utils.db.entry_by_entry_nr(eNr)
        return cls(e)

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

    @misc.LazyProperty
    def genome(self):
        g = utils.id_mapper['OMA'].genome_of_entry_nr(self._entry['EntryNr'])
        return Genome(g)

    @misc.LazyProperty
    def omaid(self):
        return utils.id_mapper['OMA'].map_entry_nr(self._entry['EntryNr'])

    @misc.LazyProperty
    def cdna(self):
        return utils.db.get_cdna(self._entry).decode()

    @misc.LazyProperty
    def sequence(self):
        return utils.db.get_sequence(self._entry).decode()

    @misc.LazyProperty
    def description(self):
        return utils.db.get_description(self._entry).decode()

    @misc.LazyProperty
    def hog_family_nr(self):
        return utils.db.hog_family(self._entry)



class Genome(object):
    def __init__(self, g):
        self._genome = g

    @property
    def ncbi_taxon_id(self):
        return int(self._genome['NCBITaxonId'])

    @property
    def uniprot_species_code(self):
        return self._genome['UniProtSpeciesCode'].decode()

    @property
    def sciname(self):
        return self._genome['SciName'].decode()

    @misc.LazyProperty
    def species_and_strain_as_dict(self):
        return misc.format_sciname(self.sciname)

    def species(self):
        return self.species_and_strain_as_dict['species']

    def strain(self):
        return self.species_and_strain_as_dict['strain']

    @misc.LazyProperty
    def kingdom(self):
        # TODO: store directly in db
        return utils.tax.get_parent_taxa(self._genome['NCBITaxonId'])[-1]['Name'].decode()

    def is_polyploid(self):
        #TODO: update once stored in database
        return self._genome['UniProtSpeciesCode'] == b'WHEAT'

    @misc.LazyProperty
    def lineage(self):
        return [lev['Name'].decode() for lev in utils.tax.get_parent_taxa(self._genome['NCBITaxonId'])]

    @misc.LazyProperty
    def ll(self):
        raise utils.InvalidTaxonId()

    def __repr__(self):
        return "<Genome({uniprot_species_code} ({ncbi_taxon_id}))>".format(self)