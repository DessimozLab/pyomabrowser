import tables
import numpy
import numpy.lib.recfunctions

from .startup import db_handle

def search_indexed_col(table, colname, element, side='left'):
    """return the row index of a table for which holds:
    row[i,col] <= search element < row[i+1,col]"""

    if not (colname in table.colindexes and
            table.colindexes[colname].is_csi):
        raise ValueError('not sorted')

    c = table.col(colname)
    idx = table.colindexes[colname]
    lo, hi = 0, len(c)
    if side=='left':
        while lo < hi:
            mid = (lo+hi)//2
            if c[idx[mid]] < element: lo = mid+1
            else: hi = mid
    else:
        while lo < hi:
            mid = (lo+hi)//2
            if element < c[idx[mid]]: hi = mid
            else: lo = mid+1
    return idx[lo], lo


class Database(object):
    def __init__(self, db=db_handle):
        self.db = db
        self.oma_mapper = get_id_mapper['OMA']

    def get_vpairs(self, entry_nr):
        genome = self.oma_mapper.genome_of_entry_nr(entry_nr)['UniProtSpeciesCode']
        vpTab = self.db.get_node('/VPairs/%s'%(genome))
        dat = vpTab.read_where('(EntryNr1==%d)'%(entry_nr))
        e = vpTab.get_enum('RelType')
        res = numpy.lib.recfunctions.append_fields(
                dat[['EntryNr1','EntryNr2']],
                names = 'RelType',
                data = map(lambda x: e(x), dat['RelType']),
                usemask=False)
        return res


class OmaIdMapper(object):
    def __init__(self, db=db_handle):
        self.db = db

    def genome_of_entry_nr(self, e_nr):
        """returns the genome code belonging to a given entry_nr"""
        genome_tab = self.db.root.Genome
        row, idx_row = search_indexed_col(genome_tab, 'EntryOff', e_nr-1, side='right')
        row_idx = genome_tab.cols.EntryOff.index[idx_row-1]
        return genome_tab[row_idx]


    def map_entry_nr(self, entry_nr):
        genome = self.genome_of_entry_nr(entry_nr)
        return "%s%05d"%(genome['UniProtSpeciesCode'], 
                entry_nr-genome['EntryOff'])


class IDResolver(object):
    def __init__(self, db=db_handle):
        self.db = db
        entry_nr_Col = db.root.Protein.Entries.cols.EntryNr
        self.max_entry_nr = entry_nr_Col[entry_nr_Col.index[-1]] 

    def _as_numeric(self, e_id):
        nr = int(e_id)
        if not 0 < nr <= self.max_entry_nr:
            raise ValueError('%d out of protein range: %s'%(nr, e_id))
        return nr

    def search_xrefs(self, e_id):
        raise NotImplemented('xref search not yet implemented')

    def resolve(self, e_id):
        """maps an id to the entry_nr of the current OMA release."""
        try:
            nr = self._as_numeric(e_id)
        except ValueError:
            nr = self.search_xrefs(e_id)
        return nr


class UnknownIdType(Exception):
    pass

class IdMapperFactory(object):
    def __init__(self):
        self.mappers={}

    def __getitem__(self, idtype):
        try:
            mapper = self.mappers[idtype]
        except KeyError:
            try:
                mapper = globals()[str(idtype).title()+'IdMapper']()
                self.mappers[idtype]=mapper
            except KeyError:
                raise UnknownIdType(str(idtype)+' is unknown')
        return mapper 


id_resolver = IDResolver()
get_id_mapper = IdMapperFactory()
db = Database()

