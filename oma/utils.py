from future.builtins import super

import tables
import numpy
import numpy.lib.recfunctions
import django.conf
import re
import json
import os

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
        self.re_fam = re.compile(r'HOG:(?P<fam>\d{7,})')

    def ensure_entry(self, entry):
        """This method allows to use an entry or an entry_nr.
        If necessary it will load the entry from the entry_nr,
        otherwise returning the same object again."""
        if isinstance(entry, int):
            return self.entry_by_entry_nr(entry)
        return entry

    def entry_by_entry_nr(self, entry_nr):
        """Returns the entry from the /Protein/Entries table
        corresponding to entry_nr."""
        entry = self.db.root.Protein.Entries.read_where(
                   'EntryNr == %d'%(entry_nr))
        if len(entry) != 1:
            raise ValueError('there are %d entries with entry_nr %d'%(len(entry),entry_nr))
        return entry[0]

    def _get_vptab(self, entry_nr):
        genome = id_mapper['OMA'].genome_of_entry_nr(entry_nr)['UniProtSpeciesCode']
        return self.db.get_node('/VPairs/{}'.format(genome))
    
    def count_vpairs(self, entry_nr):
        vpTab = self._get_vptab(entry_nr)
        return len(vpTab.read_where('(EntryNr1==%d)'%(entry_nr)))
    
    def get_vpairs(self, entry_nr):
        vpTab = self._get_vptab(entry_nr)
        dat = vpTab.read_where('(EntryNr1==%d)'%(entry_nr))
        e = vpTab.get_enum('RelType')
        res = numpy.lib.recfunctions.append_fields(
                dat[['EntryNr1','EntryNr2']],
                names = 'RelType',
                data = map(lambda x: e(x), dat['RelType']),
                usemask=False)
        return res

    def neighbour_genes(self, entry_nr, windows=1):
        """Returns neighbor genes around a query gene.

        This method returns a tuple containing a numpy recarray with 
        gene entries located around the query gene, and an index 
        pointing to the query gene. The genes are sorted according to 
        their position on the chromosome. 
        
        The *windows* parameter specifies the number of genes up- and
        downstream of the query gene that should be reported. Note
        that the actual number can be smaller if the query gene is close
        to a chromosome start or end."""
        if windows<=0 or not isinstance(windows, int):
            raise ValueError('windows parameters must be a positive integer value')

        dat = self.entry_by_entry_nr(entry_nr)
        target_chr = dat['Chromosome']
        genome_range = self._genome_range(entry_nr)
        f = 5
        data = self.db.root.Protein.Entries.read_where(
                '(EntryNr >= %d) & (EntryNr <= %d) & '
                '(Chromosome == b"%s") & '
                '((AltSpliceVariant == 0) |'
                ' (AltSpliceVariant == EntryNr))'%( 
                   max(genome_range[0], entry_nr-f*windows),
                   min(genome_range[1], entry_nr+f*windows),
                   target_chr))
        data.sort(order=['EntryNr'])
        idx = data['EntryNr'].searchsorted(entry_nr)
        res = data[max(0,idx-windows):min(len(data),idx+windows+1)]
        idx = res['EntryNr'].searchsorted(entry_nr)
        return (res, idx)


    def hog_family(self, entry):
        entry = self.ensure_entry(entry)
        m = self.re_fam.match(entry['OmaHOG'])
        if m is None:
            raise Singleton(entry)
        return int(m.group('fam'))

    def hog_levels_of_fam(self, fam_nr):
        return self.db.root.HogLevel.read_where(
                '(Fam=={})'.format(fam_nr))['Level']
    
    def hog_members(self, entry_nr, level):
        """Returns member entries for a given taxonomic level."""
        query = self.entry_by_entry_nr(entry_nr)
        queryFam = self.hog_family(query)
        hoglev = None
        for hog_candidate in self.db.root.HogLevel.where(
                '(Fam == %d) & (Level == b"%s")'%(queryFam, level)):
            if query['OmaHOG'].startswith(hog_candidate['ID']):
                hoglev = hog_candidate
                break
        if hoglev is None:
            raise ValueError('Level "%s" undefined for query gene'%(level))
        hog_range = self._hog_lex_range(hoglev['ID'])
        # get the proteins which have that HOG number
        memb = self.db.root.Protein.Entries.read_where(
                '(b"%s" <= OmaHOG) & (OmaHOG < b"%s")'%hog_range)
        # last, we need to filter the proteins to the tax range of interest
        memb = filter(lambda x: level in tax.get_parent_taxa(
            id_mapper['OMA'].genome_of_entry_nr(x['EntryNr'])['NCBITaxonId'])['Name'], memb)
        return memb
        
    def _hog_lex_range(self, hog):
        """return the lexographic range of a hog. 
        
        This can be used to search of sub-hogs which are nested in
        the query hog. The semantics is such that 
        _hog_lex_range[0] <= hog < _hog_lex_range[1].
        This is equivalent to say that a sub-hog starts with the
        query hog."""
        return hog, hog[0:-1]+chr(1+ord(hog[-1]))

            
    def _genome_range(self, g):
        return id_mapper['OMA'].genome_range(g)

        

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
        match = self.omaid_re.match(omaid)
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

    def _from_numeric(self, e_id):
        nr = int(e_id)
        if not 0 < nr <= self.max_entry_nr:
            raise InvalidId('%d out of protein range: %s'%(nr, e_id))
        return nr

    def _from_omaid(self, e_id):
        return id_mapper['OMA'].omaid_to_entry_nr(e_id)

    def search_xrefs(self, e_id):
        raise NotImplemented('xref search not yet implemented')

    def resolve(self, e_id):
        """maps an id to the entry_nr of the current OMA release."""
        try:
            nr = self._from_numeric(e_id)
        except ValueError:
            try: 
                nr = self._from_omaid(e_id)
            except InvalidOmaId:
                nr = self.search_xrefs(e_id)
        return nr


class Taxonomy(object):
    """Taxonomy provides an interface to navigate the taxonomy data. 
    
    For performance reasons, it will load at instantiation the data
    into memory. Hence, it should only be instantiated once."""
    def __init__(self, db_handle):
        self.tax_table = db_handle.root.Taxonomy.read()
        self.taxid_key = self.tax_table.argsort(order=('NCBITaxonId'))
        try:
            with open(os.environ['DARWIN_BROWSERDATA_PATH']+'/TaxLevels.drw') as f:
                taxStr = f.read()
            tax_json = json.loads(("["+taxStr[14:-3]+"]").replace("'",'"'))
            self.all_hog_levels = frozenset([t.encode('utf-8') for t in tax_json])
        except Exception:
            forbidden_chars = re.compile(r'[^A-Za-z. -]')
            self.all_hog_levels = frozenset([l for l in self.tax_table['Name'] 
                if forbidden_chars.search(l) is None])


    def _table_idx_from_numeric(self, tid):
        i = self.tax_table['NCBITaxonId'].searchsorted(tid, 
                sorter=self.taxid_key) 
        idx = self.taxid_key[i]
        if self.tax_table[idx]['NCBITaxonId'] != tid:
            raise InvalidTaxonId("%d is an invalid/unknown taxonomy id"%(tid))
        return idx

    def _taxon_from_numeric(self,tid):
        idx = self._table_idx_from_numeric(tid)
        return self.tax_table[idx]

    def get_parent_taxa(self, query):
        """Get array of taxonomy entries leading towards the 
        root of the taxonomy."""
        idx = []
        parent = query
        while parent != 0:
            i = self._table_idx_from_numeric(parent)
            idx.append(i)
            parent = self.tax_table[i]['ParentTaxonId']
        return self.tax_table.take(idx)


class InvalidTaxonId(Exception):
    pass

class InvalidId(Exception):
    pass

class InvalidOmaId(InvalidId):
    pass

class UnknownIdType(Exception):
    pass

class UnknownSpecies(Exception):
    pass

class Singleton(Exception):
    def __init__(self, entry, msg=None):
        super().__init__(msg)
        self.entry = entry


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
tax = Taxonomy(db.db)
