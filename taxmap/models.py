import abc
import pickle
import os
import numpy
import tables
from pyoma.browser.db import FuzzyMatcher
from pyoma.browser.models import Singleton
from pathlib import Path
from collections import namedtuple

# Create your models here.
CandidateTaxonomyCounterpart = namedtuple("CandidateTaxonomyCounterpart", ("taxid", "name", "jaccard", "name_sim"))

class Taxon(metaclass=abc.ABCMeta):
    def __init__(self, taxid, name, counterparts=None):
        self.taxid = taxid
        self.name = name
        self.counterparts = [CandidateTaxonomyCounterpart(*c) for c in counterparts] if counterparts is not None else []

    def yield_fuzzy_matcher_values(self):
        yield self.name, self.taxid

class GTDBTaxon(Taxon):
    source = "GTDB Taxonomy"
    def __init__(self, gtdb_taxid:int, gtdb_name:str, valid_oma_tax:bool, ncbi_counterparts:list=None, **kwargs):
        super().__init__(gtdb_taxid, gtdb_name, ncbi_counterparts)
        self.valid = valid_oma_tax
        self.oma_representative = kwargs.get("representative", None)

class NCBITaxon(Taxon):
    source = "NCBI Taxonomy"
    def __init__(self, ncbi_taxid:int, sciname:str, valid_oma_tax:bool=False, gtdb_candidates:list=None, **kwargs):
        super().__init__(ncbi_taxid, sciname, gtdb_candidates)
        self.valid = valid_oma_tax
        self.oma_representative = kwargs.get("representative", None)

class ExtantTaxon(Taxon):
    def __init__(self, taxid, sciname, code, counterpart=None, valid=True, acc=None):
        counterparts = [(counterpart, sciname, 1, 1)] if counterpart else None
        super().__init__(taxid, sciname, counterparts)
        self.code = code
        self.valid = valid
        self.gtdb_acc = acc[3:] if acc and acc[:3] in ('RS_', 'GB_') else acc
        self.source = "NCBI Taxonomy" if taxid > 0 else "GTDB Taxonomy"

    def yield_fuzzy_matcher_values(self):
        yield from super().yield_fuzzy_matcher_values()
        if self.gtdb_acc is not None:
            yield self.gtdb_acc, self.taxid


def create_ancestral_taxon(data):
    if 'ncbi_taxid' in data:
        return NCBITaxon(**data)
    elif 'gtdb_taxid' in data:
        return GTDBTaxon(**data)

def yield_extant_taxon(GS, ncbi_taxid=None, gtdb_taxid=None, sciname=None, gtdb_acc=None):
    if ncbi_taxid is None:
        gs = GS[numpy.where(GS['NCBITaxonId'] == gtdb_taxid)[0]][0]
        yield ExtantTaxon(taxid=gtdb_taxid, sciname=gs['SciName'].decode(), code=gs['UniProtSpeciesCode'].decode(), valid=True, acc=gtdb_acc)
    elif gtdb_taxid is None:
        gs = GS[numpy.where(GS['NCBITaxonId'] == ncbi_taxid)[0]][0]
        yield ExtantTaxon(taxid=ncbi_taxid, sciname=sciname, code=gs['UniProtSpeciesCode'].decode(), valid=True)
    else:
        # we have both, so GTDB is valid, NCBI is counterpart
        gs = GS[numpy.where(GS['NCBITaxonId'] == gtdb_taxid)[0]][0]
        yield ExtantTaxon(taxid=gtdb_taxid, sciname=sciname, code=gs['UniProtSpeciesCode'].decode(), valid=True, acc=gtdb_acc, counterpart=ncbi_taxid)
        yield ExtantTaxon(taxid=ncbi_taxid, sciname=sciname, code=gs['UniProtSpeciesCode'].decode(), valid=False, counterpart=gtdb_taxid)


class TaxonMapperService(metaclass=Singleton):
    def __init__(self):
        data_path = Path(os.getenv("DARWIN_BROWSERDATA_PATH")) / "taxonomymap.pkl"
        db_path = Path(os.getenv("DARWIN_BROWSERDATA_PATH")) / "OmaServer.h5"
        #self.lookup = FuzzyMatcher()
        if data_path.exists() and db_path.exists():
            with open(data_path, 'rb') as fin:
                data = pickle.load(fin)
            taxid_map = {}
            for anc in data['ancestral']:
                t = create_ancestral_taxon(anc)
                taxid_map[t.taxid] = t
            with tables.open_file(db_path) as h5:
                GS = h5.root.Genome.read()
            for ext in data['extant']:
                for t in yield_extant_taxon(GS, **ext):
                    taxid_map[t.taxid] = t

            self.taxid_map = taxid_map
        else:
            self.taxid_map = {}
        vals = [tup for tax in taxid_map.values() for tup in tax.yield_fuzzy_matcher_values()]
        fuzzy_keys, fuzzy_map = zip(*vals)
        self.lookup = FuzzyMatcher(fuzzy_keys, fuzzy_map, 0.75)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self.taxid_map[key]
        else:
            match = self.lookup.search_approx(key)
            return self.taxid_map[match[0][2]]

    def search(self, key):
        if isinstance(key, int):
            return self[key]
        matches = self.lookup.search_approx(key)
        return {self.taxid_map[k[2]]: (k[0], k[1]) for k in matches if k[0] > 0.5*matches[0][0]}

