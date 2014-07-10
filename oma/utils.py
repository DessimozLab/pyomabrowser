import tables
import numpy
import numpy.lib.recfunctions
import django.conf
import re

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
    """This is the main interface to the oma database. Queries 
    will typically be issued by methods of this object. Typically
    the result of queries will be numpy recarray objects."""
    def __init__(self, db=None):
        if db is None:
            db = django.conf.settings.HDF5DB['PATH']

        if isinstance(db, (str, unicode)):
            self.db = tables.open_file(db, 'r')
        elif isinstance(db, tables.File):
            self.db = db
        else:
            raise ValueError(str(db)+' is not a valid database type')
        
        self.id_resolver = IDResolver(self.db)

    def get_vpairs(self, entry_nr):
        genome = id_mapper['OMA'].genome_of_entry_nr(entry_nr)['UniProtSpeciesCode']
        vpTab = self.db.get_node('/VPairs/%s'%(genome))
        dat = vpTab.read_where('(EntryNr1==%d)'%(entry_nr))
        e = vpTab.get_enum('RelType')
        res = numpy.lib.recfunctions.append_fields(
                dat[['EntryNr1','EntryNr2']],
                names = 'RelType',
                data = map(lambda x: e(x), dat['RelType']),
                usemask=False)
        return res

    def get_neighbor_gene_nr(self, entry_nr, windows=1):
        """a method which returns a list of tuples with the entry 
        numbers and their orientation (strain) of the genes within
        "window" steps next to the query gene, if they exist. 
        Neighbors might not exist if the gene is at the end/beginning
        of a chromosome/scaffold."""
        entryTab = self.db.get_node('/Protein/Entries')
        dat = entryTab.read_where('EntryNr == %d'%(entry_nr))[0]
        target_chr = dat['Chromosome']
        upstream = []
        downstream = []
        genome_range = self._genome_range(entry_nr)
        for e in entryTab.where('EntryNr < %d'%(entry_nr), steps=-1):
            if (len(upstream)>windows or e['Chromosome'] != target_chr or
                    e['EntryNr']<genome_range[0]):
                break
            if e['AltSpliceVariant']>0 and e['AltSpliceVariant']!=e['EntryNr']:
                continue
            upstream.append(e)
        for e in entryTab.where('EntryNr > %d'%(entry_nr)):
            if (len(downstream)>windows or e['Chromosome'] != target_chr or
                    e['EntryNr']>genome_range[1]):
                break
            if e['AltSpliceVariant']>0 and e['AltSpliceVariant']!=e['EntryNr']:
                continue
            downstream.append(e)

        return (upstream, dat, downstream)

    def _genome_range(self, g):
        return self.id_mapper['OMA'].genome_range(g)

        

class OmaIdMapper(object):
    def __init__(self, db):
        self.cached_table = db.root.Genome.read()
        self.entry_off_keys = self.cached_table.argsort(order=('EntryOff'))
        self.genome_keys = self.cached_table.argsort(
                order=('UniProtSpeciesCode'))
        self.omaid_re = re.compile(r'(?P<genome>[A-Z][A-Z0-9]{4})(?P<nr>\d+)')

    def genome_of_entry_nr(self, e_nr):
        """returns the genome code belonging to a given entry_nr"""
        idx = self.cached_table['EntryOff'].searchsorted(
                e_nr - 1, side='right', 
                sorter=self.entry_off_keys)
        return self.cached_table[self.entry_off_keys[idx-1]]

    def map_entry_nr(self, entry_nr):
        genome = self.genome_of_entry_nr(entry_nr)
        return "%s%05d"%(genome['UniProtSpeciesCode'], 
                entry_nr-genome['EntryOff'])

    def genome_from_UniProtCode(self, code):
        idx = self.cached_table['UniProtSpeciesCode'].searchsorted(
                code, sorter=self.genome_keys)
        genome = self.cached_table[self.genome_keys[idx]]
        if genome['UniProtSpeciesCode'] != code:
            raise UnknownSpecies('%s is unknown'%(code))
        return genome

    def omaid_to_entry_nr(self, omaid):
        """returns the internal numeric entrynr from a 
        UniProtSpeciesCode+nr id. this is the inverse 
        function of 'map_entry_nr'."""
        match = self.omaid_re(omaid)
        if match is None:
            raise InvalidOmaId(omaid)
        code, nr = match.group('genome'), int(match.group('nr'))
        genome = self.genome_from_UniProtCode(code)
        if nr<=0 or nr>genome['TotEntries']:
            raise InvalidOmaId(omaid)
        return genome['EntryOff']+int(match.group('nr'))

    def genome_range(self, query):
        """returns the internal range of EntryNr associated with
        'query'. 'query' can be either a numeric id of a protein 
        or a UniProtSpeciesCode of a genome. If 'query' is unknown
        by the database, an InvalidOmaId exception is raised"""
        if isinstance(query, int):
            genome_row = self.genome_of_entry_nr(query)
            if (query <= 0 or query > genome_row['EntryOff'] +
                    genome_row['TotEntries']):
                raise InvalidOmaId(query)
        else:
            genome_row = self.genome_from_UniProtCode(query)
        return (genome_row['EntryOff']+1, 
                genome_row['EntryOff']+genome_row['TotEntries'],)
        

class IDResolver(object):
    def __init__(self, db_handle):
        self.db = db_handle
        entry_nr_Col = db_handle.root.Protein.Entries.cols.EntryNr
        self.max_entry_nr = entry_nr_Col[entry_nr_Col.index[-1]] 

    def _as_numeric(self, e_id):
        nr = int(e_id)
        if not 0 < nr <= self.max_entry_nr:
            raise InvalidId('%d out of protein range: %s'%(nr, e_id))
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

class InvalidId(Exception):
    pass

class InvalidOmaId(InvalidId):
    pass

class UnknownIdType(Exception):
    pass

class UnknownSpecies(Exception):
    pass

class IdMapperFactory(object):
    def __init__(self, db_obj):
        self.db = db_obj
        self.mappers={}

    def __getitem__(self, idtype):
        try:
            mapper = self.mappers[idtype]
        except KeyError:
            try:
                mapper = globals()[str(idtype).title()+'IdMapper'](self.db.db)
                self.mappers[idtype]=mapper
            except KeyError:
                raise UnknownIdType(str(idtype)+' is unknown')
        return mapper 


db = Database()
id_resolver = IDResolver(db.db)
id_mapper = IdMapperFactory(db)

