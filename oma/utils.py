from future.builtins import super

import tables
import numpy
import numpy.lib.recfunctions
import django.conf
import re
import json
import os
import collections
import logging
from ete2 import Tree, SeqMotifFace, TreeStyle, add_face_to_node, NodeStyle

logger = logging.getLogger(__name__)

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
        try:
            t = entry['AltSpliceVariant']
            return entry
        except (TypeError, AttributeError, IndexError):
            if isinstance(entry, (int, numpy.number)):
                return self.entry_by_entry_nr(entry)
            raise TypeError('Invalid type to retrieve an Entry')
        except Exception:
            raise TypeError('Invalid type to retrieve an Entry')

    def entry_by_entry_nr(self, entry_nr):
        """Returns the entry from the /Protein/Entries table
        corresponding to entry_nr."""
        entry = self.db.root.Protein.Entries[entry_nr-1]
        if entry['EntryNr'] != entry_nr:
            logger.warning('EntryNr {} not at position {}. Using index instead'.format(entry_nr, entry_nr-1))
            entry = self.db.root.Protein.Entries.read_where(
                   'EntryNr == %d'%(entry_nr))
            if len(entry) != 1:
                raise ValueError("there are {} entries with entry_nr {}".format(len(entry), entry_nr))
            entry = entry[0]
        return entry

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
        return res, idx


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

    def get_orthoxml(self, fam):
        """returns the orthoxml of a given toplevel HOG family

        :param fam: numeric id of requested toplevel hog"""
        idx = self.db.root.OrthoXML.Index.read_where('Fam == {}'.format(fam))
        if len(idx) < 1:
            raise ValueError('cannot retrieve orthoxml for {}'.format(fam))
        idx = idx[0]
        return self.db.root.OrthoXML.Buffer[idx['HogBufferOffset']:idx['HogBufferOffset']+idx['HogBufferLength']].tostring()
        
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

    def get_sequence(self, entry):
        """get the protein sequence of a given entry as a string"""
        entry = self.ensure_entry(entry)
        seqArr = self.db.get_node('/Protein/SequenceBuffer')
        seq = seqArr[entry['SeqBufferOffset']:entry['SeqBufferOffset']+entry['SeqBufferLength']-1]
        return seq.tostring()

    def get_release_name(self):
        return self.db.get_node_attr('/', 'oma_version').decode()

    def get_domains(self, entry_nr):
        try:
            return self.db.root.Annotations.Domains.read_where('EntryNr == {:d}'.format(entry_nr))
        except ValueError as e:
            raise InvalidId('require a numeric entry id, got {}'.format(entry_nr))


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
        self.max_entry_nr = entry_nr_Col[int(entry_nr_Col.index[-1])]

    def _from_numeric(self, e_id):
        nr = int(e_id)
        if not 0 < nr <= self.max_entry_nr:
            raise InvalidId('%d out of protein range: %s'%(nr, e_id))
        return nr

    def _from_omaid(self, e_id):
        return id_mapper['OMA'].omaid_to_entry_nr(e_id)

    def search_xrefs(self, e_id):
        """search for all xrefs. TODO: what happens if xref is ambiguous?"""
        res = set([x['EntryNr'] for x in id_mapper['XRef'].search_xref(e_id)])
        if len(res)==0:
            raise InvalidId(e_id)
        elif len(res) > 1:
            raise NotImplemented('Cross-ref "{}" is ambiguous'.format(e_id))
        return int(res.pop())

    def resolve(self, e_id):
        """maps an id to the entry_nr of the current OMA release."""
        try:
            nr = self._from_numeric(e_id)
        except ValueError:
            try: 
                nr = self._from_omaid(e_id)
            except (InvalidOmaId, UnknownSpecies) as e:
                nr = self.search_xrefs(e_id)
        return nr


class Taxonomy(object):
    """Taxonomy provides an interface to navigate the taxonomy data. 
    
    For performance reasons, it will load at instantiation the data
    into memory. Hence, it should only be instantiated once."""

    def __init__(self, db_handle):
        self.tax_table = db_handle.root.Taxonomy.read()
        self.taxid_key = self.tax_table.argsort(order=('NCBITaxonId'))
        self._load_valid_taxlevels()

    def _load_valid_taxlevels(self):
        forbidden_chars = re.compile(r'[^A-Za-z. -]')
        try:
            with open(os.environ['DARWIN_BROWSERDATA_PATH'] + '/TaxLevels.drw') as f:
                taxStr = f.read()
            tax_json = json.loads(("[" + taxStr[14:-3] + "]").replace("'", '"'))
            self.all_hog_levels = frozenset([t.encode('utf-8') for t in
                                             tax_json if forbidden_chars.search(t) is None])
        except Exception:
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
        count = 0
        while parent != 0:
            i = self._table_idx_from_numeric(parent)
            idx.append(i)
            tmp = self.tax_table[i]['ParentTaxonId']
            if tmp == parent:
                raise InvalidTaxonId("%d has itself as parent"%(tmp))
            parent = tmp 
            count += 1
            if count > 100:
                raise InvalidTaxonId("%d exceeds max depth of 100. Infinite recursion?"%(query))
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
                self.mappers[idtype] = mapper
            except KeyError:
                raise UnknownIdType('{} is unknown'.format(str(idtype)))
        return mapper 


class XrefIdMapper(object):
    def __init__(self, db_handle):
        self.xref_tab = db_handle.get_node('/XRef')
        self.xrefEnum = self.xref_tab.get_enum('XRefSource')
        self.idtype = frozenset(self.xrefEnum._values.keys())

    def map_entry_nr(self, entry_nr):
        res = set([row for row in self.xref_tab.where('EntryNr=={}'.format(entry_nr))
            if row['XRefSource'] in self.idtype])
        return res

    def _combine_query_values(self, field, values):
        parts = ['({}=={})'.format(field, z) for z in values]
        return '|'.join(parts)


    def map_many_entry_nrs(self, entry_nrs):
        """map several entry_nrs with as few db queries as possible to their
        cross-references. The function returns a numpy recarray containing all 
        fields as defined in the table."""
        mapped_junks = []
        junk_size = 32 - len(self.idtype) # respect max number of condtion variables.
        source_condition = self._combine_query_values('XRefSource',self.idtype)
        for start in range(0, len(entry_nrs), junk_size):
            condition = "({}) & ({})".format(
                    self._combine_query_values('EntryNr',
                        entry_nrs[start:start+junk_size]),
                    source_condition)
            mapped_junks.append(self.xref_tab.read_where(condition))
        return numpy.lib.recfunctions.stack_arrays(
                mapped_junks,
                usemask=False)

    def search_xref(self, xref):
        res = self.xref_tab.read_where('XRefId=="{}"'.format(xref.encode('utf-8')))
        if len(res) > 0 and len(self.idtype) < len(self.xrefEnum):
            res = res[numpy.in1d(res['XRefSource'], list(self.idtype))]
        return res

    def xreftab_to_dict(self, tab):
        xrefdict = collections.defaultdict(dict)
        for row in tab:
            try:
                typ = self.xrefEnum._values[row['XRefSource']]
            except IndexError as e:
                logger.warn('invalid XRefSource value in {}'.format(row))
                continue
            if typ not in xrefdict[row['EntryNr']]:
                xrefdict[row['EntryNr']][typ] = {'id':row['XRefId']}
        return xrefdict


        
class UniProtIdMapper(XrefIdMapper):
    def __init__(self, db):
        super().__init__(db)
        self.idtype = frozenset([self.xrefEnum[z] 
            for z in ['UniProtKB/SwissProt', 'UniProtKB/TrEMBL']])


class LinkoutIdMapper(XrefIdMapper):
    def __init__(self, db):
        super().__init__(db)
        self.idtype = frozenset([self.xrefEnum[z]
            for z in ['UniProtKB/SwissProt', 'UniProtKB/TrEMBL',
                      'Ensembl Protein', 'EntrezGene']])

    def url(self, typ, id_):
        # TODO: improve url generator in external module with all xrefs
        url = None
        if typ.startswith('UniProtKB'):
            url = 'http://uniprot.org/uniprot/{}'.format(id_)
        elif typ == 'EntrezGene':
            url = 'http://www.ncbi.nlm.nih.gov/gene/{}'.format(id_)
        elif typ.startswith('Ensembl'):
            url = 'http://ensembl.org/id/{}'.format(id_)
        return url


    def xreftab_to_dict(self, tab):
        xref = super().xreftab_to_dict(tab)
        for d in xref.values():
            for typ, elem in d.items():
                elem['url'] = self.url(typ, elem['id'])
        return xref

class DrawDomains(object):
    def __init__(self, domains, seq, height=20, width=None, arch=True, name='motifs'):
        """Creating an instance of the class for a protein sequence creates an ETE tree branch with the architecture."""
        motifs, cath_ids = self.get_motifs(domains, seq, height, width, arch)
        if len(motifs) > 0: 
            architecture = self.branch(seq, motifs)
            self.svg_string = self.get_svg_string(architecture, cath_ids, name)

    def chunks(self, l, n):
        for i in range(0, len(l), n):
            yield l[i:i+n]

    def regions(self, regions_string):
        rlist = regions_string.split(':')
        rintlist = list(map(int, rlist))
        return(list(self.chunks(rintlist, 2)))

    def branch(self, seq, motifs):
        t = Tree()
        t.populate(1) # Make a single branch tree
        for l in t.iter_leaves():
            l.add_face(SeqMotifFace(seq, motifs), 0, "aligned")
        nstyle = NodeStyle()
        nstyle["size"] = 0 # As good as remove the node which we don't need
        for n in t.traverse():
            n.set_style(nstyle)
        return t

    def get_motifs(self, domains, seq, height=20, width=None, arch=True):
        motifs = []
        cath_ids = []
        dt = 0 # the number of unique domain types
        for row in domains:
            cath_ids.append(row[1])
            cath_list = row[1].split('.')
            if cath_list[0] == '1' or cath_list[0] == '2' or cath_list[0] == '3' or cath_list[0] == '4':
                col, shape, architecture = self.col_shape_arch(cath_list) # row[1] is the CATH code domain string
                for pos in self.regions(row[2]):
                    if arch:
                        motifs.append([pos[0], pos[1], shape, width, height, None, col, "arial|8|black|"+architecture+": "+row[1]])
                    else:
                        motifs.append([pos[0], pos[1], shape, width, height, None, col, "arial|8|black|"+row[1]])
        return motifs, cath_ids

    def col_shape_arch(self, cath): 
        """Assign a colour and shape for each of the 40 domain architectures in CATH"""
        if cath[0] == '1': # Mainly Alpha
            shape = '[]'
            if cath[1] == '10':
                col = '#FFB2B2'
                arch = 'Orthogonal Bundle'
            elif cath[1] == '20':
                col = '#FF8080'
                arch = 'Up-down Bundle'
            elif cath[1] == '25':
                col = '#FF4D4D'
                arch = 'Alpha Horseshoe'
            elif cath[1] == '40':
                col = '#FF1919'
                arch = 'Alpha solenoid'
            elif cath[1] == '50':
                col = '#E60000'
                arch = 'Alpha/alpha barrel'
            else:
                col = None
                arch = None
        elif cath[0] == '2': # Mainly Beta
            shape = 'o'
            if cath[1] == '10':
                col = '#E6E6FF'
                arch = 'Ribbon'
            elif cath[1] == '20':
                col = '#B2B2FF'
                arch = 'Single Sheet'
            elif cath[1] == '30':
                col = '#8080FF'
                arch = 'Roll'
            elif cath[1] == '40':
                col = '#4D4DFF'
                arch = 'Beta Barrel'
            elif cath[1] == '50':
                col = '#1919FF'
                arch = 'Clam'
            elif cath[1] == '60':
                col = '#0000E6'
                arch = 'Sandwich'
            elif cath[1] == '70':
                col = '#008AB8'
                arch = 'Distorted Sandwich'
            elif cath[1] == '80':
                col = '#19A3D1'
                arch = 'Trefoil'
            elif cath[1] == '90':
                col = '#4DB8DB'
                arch = 'Orthogonal Prism'
            elif cath[1] == '100':
                col = '#80CCE6'
                arch = 'Aligned Prism'
            elif cath[1] == '102':
                col = '#70DBDB'
                arch = '3-layer Sandwich'
            elif cath[1] == '105':
                col = '#33CCCC'
                arch = '3 Propellor'
            elif cath[1] == '110':
                col = '#29A3A3'
                arch = '4 Propellor'
            elif cath[1] == '115':
                col = '#00B85C'
                arch = '5 Propellor'
            elif cath[1] == '120':
                col = '#19D175'
                arch = '6 Propellor'
            elif cath[1] == '130':
                col = '#4DDB94'
                arch = '7 Propellor'
            elif cath[1] == '140':
                col = '#80E6B2'
                arch = '8 Propellor'
            elif cath[1] == '150':
                col = '#B2F0D1'
                arch = '2 Solenoid'
            elif cath[1] == '160':
                col = '#B2CC80'
                arch = '3 Solenoid'
            elif cath[1] == '170':
                col = '#94B84D'
                arch = 'Beta Complex'
            else:
                col = None
                arch = None
        elif cath[0] == '3': # Alpha Beta
            shape = '<>'
            if cath[1] == '10':
                col = '#FFFF80'
                arch = 'Roll'
            elif cath[1] == '15':
                col = '#FFFF19'
                arch = 'Super Roll'
            elif cath[1] == '20':
                col = '#E6E600'
                arch = 'Alpha-Beta Barrel'
            elif cath[1] == '30':
                col = '#B2B200'
                arch = '2-Layer Sandwich'
            elif cath[1] == '40':
                col = '#E68A00'
                arch = '3-Layer(aba) Sandwich'
            elif cath[1] == '50':
                col = '#FFA319'
                arch = '3-Layer(bba) Sandwich'
            elif cath[1] == '55':
                col = '#FFB84D'
                arch = '3-Layer(bab) Sandwich'
            elif cath[1] == '60':
                col = '#FFCC80'
                arch = '4-Layer Sandwich'
            elif cath[1] == '65':
                col = '#FFE0B2'
                arch = 'Alpha-beta prism'
            elif cath[1] == '70':
                col = '#FFF5E6'
                arch = 'Box'
            elif cath[1] == '75':
                col = '#F5D6CC'
                arch = '5-Stranded Propellor'
            elif cath[1] == '80':
                col = '#EBAD99'
                arch = 'Alpha-Beta Horseshoe'
            elif cath[1] == '90':
                col = '#E08566'
                arch = 'Alpha-Beta Complex'
            elif cath[1] == '100':
                col = '#D14719'
                arch = 'Ribosomal Protein L15; Chain: K; domain 2'
            else:
                col = None
                arch = None
        elif cath[0] == '4': # Few Secondary Structures
            shape = 'v'
            if cath[1] == '10':
                col = '#CC00FF'
                arch = 'Irregular'
            else:
                col = None
                arch = None
        return col, shape, arch
                
    def get_svg_string(self, architecture, cath_ids, name="motif"):
        """Create an svg of the domain architecture"""
        ts = TreeStyle()
        ts.show_leaf_name = False
        ts.show_scale = False
        architecture.render("oma/static/image/domains/%s.svg"%name, tree_style=ts, units="mm")
        f = open("oma/static/image/domains/%s.svg"%name, "r")
        svg_string = f.read()
        f.close()
        """Edit the svg to include relevant CATH page link for each domain"""
        svg_string_original = svg_string
        for cath_id in cath_ids:
            string_indices = [m.start() for m in re.finditer(cath_id, svg_string_original)]
            for string_index in string_indices:
                substring = svg_string_original[0:string_index]
                sub_rev = substring[::-1]
                x = [m.start() for m in re.finditer('txet<', sub_rev)][0]
                pos = len(sub_rev)-x-1
                text = "<tex"+svg_string_original[pos:string_index+len(cath_id)+7]
                link = 'xlink:href="http://www.cathdb.info/version/latest/superfamily/' + cath_id + '"'
                new_text = '<a ' + link + '>' + text + '</a>'
                if new_text not in svg_string:
                    svg_string = svg_string.replace(text, new_text)
        os.remove("oma/static/image/domains/%s.svg"%name)
        return svg_string

db = Database()
id_resolver = IDResolver(db.db)
id_mapper = IdMapperFactory(db)
tax = Taxonomy(db.db)
