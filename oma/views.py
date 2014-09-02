from django.shortcuts import render
from django.http import HttpResponse, Http404
from collections import OrderedDict
import logging
import itertools

from . import utils
from . import misc

logger = logging.getLogger(__name__)

# Create your views here.
def pairs(request, entry_id, idtype='OMA'):
    
    entry_nr = utils.id_resolver.resolve(entry_id)
    vps_entry_nr = utils.db.get_vpairs(entry_nr)
    
    query = utils.id_mapper[idtype].map_entry_nr(entry_nr)
    vps = map(utils.id_mapper[idtype].map_entry_nr, vps_entry_nr['EntryNr2'])
    print(len(vps))
    context = {'query': query, 'vps':vps}
    
    return render(request, 'vpairs.html', context)


def synteny(request, entry_id, mod=4, windows=4, idtype='OMA'):
    """loads data to visualize the synteny around a query 
    gene and it's orthologs.
    the parameter 'mod' is used to keep the color between
    calls on different entries compatible, i.e. they selected
    gene should keep it's color.
    the window paramter is used to select the size of the 
    neighborhood."""
    entry_nr = utils.id_resolver.resolve(entry_id)
    genome=utils.id_mapper['OMA'].genome_of_entry_nr(entry_nr)
    try:
        lin=utils.tax.get_parent_taxa(genome['NCBITaxonId'])
    except Exception:
        logger.warning("cannot get NCBI Taxonomy for {} ({})".format(
            genome['UniProtSpeciesCode'],
            genome['NCBITaxonId']))
        lin = []
    taxa=[]
    for i in lin:
        taxa.append(i[2])
    if len(taxa)>2:
        sciname = taxa[0]
        kingdom = taxa[-1]
    else:
        sciname = "unknown"
        kingdom = "unknown"

    windows = int(windows)
    ngs_entry_nr = utils.db.neighbour_genes(entry_nr, windows)
    positions = list(range(-windows, windows+1)) #list of intergers for gene positions

    gene_left = ngs_entry_nr[-1]

    blank_l=windows-gene_left

    blank_r1=windows+len(ngs_entry_nr[0])-gene_left
    blank_r2=windows+windows+1

    geneinfos = []
    md_geneinfos = {} #gene informations for first row, entry gene species
    md_geneinfos['genes']={}
    query = utils.id_mapper[idtype].map_entry_nr(entry_nr)

    species = query[0:5] #Species name of the entr gene


    md_geneinfos['species']=species
    for i in range(blank_l):
        md_geneinfos['genes'][i]={"type":"blank"}
    for i in range(blank_r1,blank_r2):
        md_geneinfos['genes'][i]={"type":"blank"}


    for index, info in enumerate(ngs_entry_nr[0][0:]):
        geneinfo = {
            "entryid":info[0],
            "genename":utils.id_mapper[idtype].map_entry_nr(info[0]),
            "dir":info[-2],
            "type":(index-gene_left+int(mod))%(windows+windows+1),
            "geneindex":index}

        geneinfo["species"] = geneinfo["genename"][0:5]
        geneinfo["genenumber"]= geneinfo["genename"][5:]
        geneinfo["orthologs"] = utils.db.get_vpairs(info[0])['EntryNr2']

        if geneinfo["geneindex"]==gene_left:
            entry_dir = geneinfo["dir"]
            md_geneinfos['entry_dir']=entry_dir


        geneinfos.append(geneinfo)
        md_geneinfos['genes'][index+blank_l]=geneinfo
        md_geneinfos['genes'] = OrderedDict(
                sorted(md_geneinfos['genes'].items(), 
                key=lambda t: t[0]))


    vps_entry_nr = utils.db.get_vpairs(entry_nr)
    orthologs = vps_entry_nr['EntryNr2']

    o_md_geneinfos = {}

    colors = {0:'#9E0142',1:'#FDAE61',2:'#E6F598',3:'#3288BD',4:'#D53E4F', 5:'#FEE08B',
    6:'#66C2A5',7:'#5E4FA2',8:'#F46D43',9:'#FFFFBF',10:'#ABDDA4'}
    stripes ={}

    o_sorting = {}
    for ortholog in orthologs:
        if utils.id_mapper[idtype].map_entry_nr(ortholog)[0:5] in o_sorting:
            o_sorting = o_sorting
        else:
            o_genome=utils.id_mapper['OMA'].genome_of_entry_nr(ortholog)
            try:
                o_lin=utils.tax.get_parent_taxa(o_genome['NCBITaxonId'])
            except Exception:
                logger.warning("cannot get NCBI Taxonomy for {} ({})".format(
                    genome['UniProtSpeciesCode'],
                    genome['NCBITaxonId']))
                o_lin=[]
            o_taxa=[]
            for i in o_lin:
                o_taxa.append(i[2])

            match = len(set(taxa) & set(o_taxa))
            o_sorting[utils.id_mapper[idtype].map_entry_nr(ortholog)[0:5]] = match
    o_sorting= OrderedDict(sorted(o_sorting.items(), key=lambda t: t[1], reverse=True))
    o_sorting = o_sorting.keys()[0:100]
    osd = {} #ortholog sorting dictionary
    for row, each in enumerate(o_sorting):
        osd[each]=row

    for ortholog in orthologs:
        o_species =utils.id_mapper[idtype].map_entry_nr(ortholog)[0:5]
        if o_species in o_sorting:
            #get neighbouring genes for each ortholog
            o_ngs_entry_nr = utils.db.neighbour_genes(int(ortholog), windows) 

            row_number = osd[o_species]

            o_blank_l=windows-o_ngs_entry_nr[-1]
            o_blank_r1=windows+len(o_ngs_entry_nr[0])-o_ngs_entry_nr[-1]
            o_blank_r2=windows+windows+1

            o_md_geneinfos[ortholog]={'o_species':o_species}
            o_md_geneinfos[ortholog]['row_number']=row_number
            o_md_geneinfos[ortholog]['o_genes']={}

            for i in range(o_blank_l):
                o_md_geneinfos[ortholog]['o_genes'][i]={"o_type":"blank"}
            for i in range(o_blank_r1,o_blank_r2):
                o_md_geneinfos[ortholog]['o_genes'][i]={"o_type":"blank"}

            o_allinfo = o_ngs_entry_nr[0]
            o_separate = o_allinfo[0:] #each gene information in original form


            for index, info in enumerate(o_separate):
                syntenyorthologs = ["not found"]

                o_geneinfo = {
                "entryid":info[0],
                "genename":utils.id_mapper[idtype].map_entry_nr(info[0]),
                "dir":info[-2],}

                o_geneinfo["species"] = o_geneinfo["genename"][0:5]
                o_geneinfo["genenumber"]= o_geneinfo["genename"][5:]


                if o_geneinfo["entryid"]==ortholog:
                    o_md_geneinfos[ortholog]["row_dir"]=o_geneinfo["dir"]

                for geneinfo in geneinfos:
                    if o_geneinfo["entryid"] in geneinfo["orthologs"]:
                        syntenyorthologs.append(str(geneinfo["type"])) #type for color determination


                if len(syntenyorthologs)==1:
                    o_geneinfo["o_type"] = "not found"
                elif len(syntenyorthologs)==2:
                    o_geneinfo["o_type"]=syntenyorthologs[1]
                elif len(syntenyorthologs)>=3:
                    stripe=''
                    st_name = ''
                    x=0
                    for i in syntenyorthologs[1:]:
                        st_name=st_name+(i+"-")
                        if st_name in stripe:
                            stripe=stripe
                        else:
                            stripe=stripe+(colors[int(i)]+' '+str(x)+'px,'+colors[int(i)]+' '+str(x+15)+'px,')
                        x += 15

                    stripes[st_name]=stripe[:-1]
                    syntenyorthologs.append(st_name)


                    o_geneinfo["o_type"]=syntenyorthologs[1:]


                o_md_geneinfos[ortholog]['o_genes'][index+o_blank_l]=o_geneinfo

            if o_md_geneinfos[ortholog]["row_dir"] == md_geneinfos['entry_dir']:
                o_md_geneinfos[ortholog]['o_genes'] = OrderedDict(sorted(o_md_geneinfos[ortholog]['o_genes'].items(), key=lambda t: t[0]))
            elif o_md_geneinfos[ortholog]["row_dir"] != md_geneinfos['entry_dir']:
                o_md_geneinfos[ortholog]['o_genes'] = OrderedDict(sorted(o_md_geneinfos[ortholog]['o_genes'].items(), key=lambda t: t[0], reverse=True))

    o_md_geneinfos= OrderedDict(
            sorted(o_md_geneinfos.items(), 
            key=lambda t: t[1]['row_number']))

    context = {'query':query,'positions':positions, 'windows':windows,
          'md':md_geneinfos, 'o_md':o_md_geneinfos, 'colors':colors, 
          'stripes':stripes, 'nr_vps':len(orthologs), 
          'entry':{'omaid':query, 'sciname':sciname, 'kingdom':kingdom,},
          'tab':'synteny'
        }

    return render(request, 'synteny.html', context)



def hogs(request, entry_id, level=None, idtype='OMA'):
    entry_nr = utils.id_resolver.resolve(entry_id)
    query = utils.id_mapper[idtype].map_entry_nr(entry_nr)

    entry = utils.db.entry_by_entry_nr(entry_nr)
    genome=utils.id_mapper['OMA'].genome_of_entry_nr(entry_nr)
    
    hog_member_entries = []
    hog = None
    levels = []
    try:
        fam = utils.db.hog_family(entry)
        levs_of_fam = frozenset(utils.db.hog_levels_of_fam(fam))
        lineage = utils.tax.get_parent_taxa(genome['NCBITaxonId'])
        levels = [l for l in itertools.chain(lineage['Name'], ('LUCA',)) 
                if l in utils.tax.all_hog_levels and l in levs_of_fam]
        hog = {'id': entry['OmaHOG'], 'fam': fam, 
                'downloadURL':misc.downloadURL_hog(fam)}
        if not level is None:
            hog_member_entries = utils.db.hog_members(entry_nr, level)
    except utils.Singleton:
        pass
    except ValueError as e:
        raise Http404(e.message)
    except utils.InvalidTaxonId:
        logger.error("cannot get NCBI Taxonomy for {} ({})".format(
            genome['UniProtSpeciesCode'],
            genome['NCBITaxonId']))
    
    hog_members = []
    for memb in hog_member_entries:
        t = {}
        t['omaid'] = utils.id_mapper['OMA'].map_entry_nr(memb['EntryNr'])
        g=utils.id_mapper['OMA'].genome_of_entry_nr(memb['EntryNr'])
        t['sciname'] = g['SciName']
        t['kingdom'] = utils.tax.get_parent_taxa(g['NCBITaxonId'])[-1]['Name']
        hog_members.append(t)

    nr_vps = utils.db.count_vpairs(entry_nr)
    context = {'entry': {'omaid': query, 'sciname': genome['SciName'],
            'kingdom':utils.tax.get_parent_taxa(genome['NCBITaxonId'])[-1]['Name']}, 
            'level': level, 'hog_members': hog_members,
            'nr_vps': nr_vps, 'tab':'hogs', 'levels':levels[::-1]}
    if not hog is None:
        context['hog'] = hog

    logging.debug("context:" + str(context))
    return render(request, 'hogs.html', context)


def home(request):
    context = {}
    return render(request, 'home.html', context)

def about(request):
    context = {}
    return render(request, 'about.html', context)

def groupCV(request): #OMAGroupCV
    context = {}
    # _groupNumber (22252)
    # _description (calcium/calmodulin-dependent protein kinase IG)
    # _numberOfMembers  [xEuka + xBact + xArch]
    # _fingerprint (PWINGNT)
    #
    #
    #
    #
    #
    #
    #
    #
    #
    return render(request, 'groupCV.html', context)

def landHOG(request):
    context = {}
    return render(request, 'landHOG.html', context)

def landAnnotation(request):
    context = {}
    return render(request, 'landAnnotation.html', context)


def landsynteny(request):
    context = {}
    return render(request, 'landsynteny.html', context)

def team(request):
    context = {}
    return render(request, 'team.html', context)

def funding(request):
    context = {}
    return render(request, 'funding.html', context)

def license(request):
    context = {}
    return render(request, 'license.html', context)

def current(request):
    context = {}
    return render(request, 'current.html', context)

def archives(request):
    context = {}
    return render(request, 'archives.html', context)

def APISOAP(request):
    context = {}
    return render(request, 'APISOAP.html', context)

def APIDAS(request):
    context = {}
    return render(request, 'APIDAS.html', context)

def type(request):
    context = {}
    return render(request, 'type.html', context)

def uses(request):
    context = {}
    return render(request, 'uses.html', context)

def FAQ(request):
    context = {}
    return render(request, 'FAQ.html', context)

def genomePW(request):
    context = {}
    return render(request, 'genomePW.html', context)

def nutshell(request):
    context = {}
    return render(request, 'nutshell.html', context)

def dataset(request):
    context = {}
    return render(request, 'dataset.html', context)

def seqCVprotein(request):
    context = {}
    return render(request, 'seqCVprotein.html', context)


def landOMA(request):
    context = {}
    return render(request, 'landOMA.html', context)

def genomeCV(request):
    context = {}
    return render(request, 'genomeCV.html', context)

def seqCV(request, entry_id, tab='hogs'):
    context = {}
    # Entry number of the protein
    # Database id
    # Specie name + E/A/B
    #   <span class="label label-danger "><abbr class='abbrNoUnder'title="Eukariota">E</abbr></span> 
    #   <span class="label label-success "><abbr class='abbrNoUnder'title="Archae">A</abbr></span> 
    #   <span class="label label-primary "><abbr class='abbrNoUnder'title="Bacteria">B</abbr></span>
    # Number Of orthologs
    return render(request, 'seqCV.html', context)

def informationSeqCV(request):
    context = {}
    # _description (calcium/calmodulin-dependent protein kinase IG [Source:HGNC Symbol;Acc:14585])
    # _specieId (HUMAN)
    # _specieName (Homo Sapiens)
    # _locus (Chromosome 1: join(209...)
    # _proteinId (Q96NX5)
    # _uniprotId1 (KCC1G_HUMAN)
    # _uniprotId2 (Acc.: Q96NX5)
    # _EnsemblId1 (ENSG00000008118)
    # _EnsemblId2 (ENSP00000009105)
    # _EnsemblId3 (ENST00000009105)
    # _RefseqId1 (NP_065172)
    # _RefseqId2 (NP_065172.1)
    # _RefseqId3 (GI: 14196445)
    # _entrez (57172)
    # _HGNCId (CAMK1G)
    # _HGNCInfo (calcium/calmodulin-dependent protein kinase IG)
    # _NCBIID1 (AAH32787.1)
    # _NCBIID2 (AAL28100.1)
    # _GOTerm (nucleotide binding)
    # _GOId (GO:0000166)
    # _evidenceType (Publication)
    # _evidenceRef (PMID:18782753)
    # _Sequence

    return render(request, 'informationSeqCV.html', context)

def orthologsSeqCV(request):
    context = {}
    # list of orthologs with E/A/B + _speciesName + _speciesId
    return render(request, 'orthologsSeqCV.html', context)

def syntenySeqCV(request):
    context = {}
    return render(request, 'syntenySeqCV.html', context)

def HOGsSeqCV(request):
    context = {}
    return render(request, 'HOGsSeqCV.html', context)

def OMAGSeqCV(request):
    context = {}
    return render(request, 'OMAGSeqCV.html', context)

def alignGroupCV(request):
    context = {}
    # list of sequences with _speciesId & _sequence
    return render(request, 'alignGroupCV.html', context)

def closeGroupCV(request):
    context = {}
    return render(request, 'closeGroupCV.html', context)

def seqCValign(request):
    context = {}
    return render(request, 'seqCValign.html', context)

def seqCVclose(request):
    context = {}
    return render(request, 'seqCVclose.html', context)


def ontologyHOGCV(request):
    context = {}
    return render(request, 'ontologyHOGCV.html', context)

def alignHOGCV(request):
    context = {}
    return render(request, 'alignHOGCV.html', context)

def proteinHOGCV(request):
    context = {}
    return render(request, 'proteinHOGCV.html', context)   

def seqCVontology(request):
    context = {}
    return render(request, 'seqCVontology.html', context)

def ArchivesJul2013(request):
    context = {}
    return render(request, 'ArchivesJul2013.html', context)

def ArchivesDec2012(request):
    context = {}
    return render(request, 'ArchivesDec2012.html', context)

def ArchivesMar2012(request):
    context = {}
    return render(request, 'ArchivesMar2012.html', context)

def ArchivesMay2011(request):
    context = {}
    return render(request, 'ArchivesMay2011.html', context)

def ArchivesNov2010(request):
    context = {}
    return render(request, 'ArchivesNov2010.html', context)

def ArchivesMay2010(request):
    context = {}
    return render(request, 'ArchivesMay2010.html', context)

def ArchivesOct2009(request):
    context = {}
    return render(request, 'ArchivesOct2009.html', context)

def ArchivesApr2009(request):
    context = {}
    return render(request, 'ArchivesApr2009.html', context)



def HOGCV(request):
    context = {}
    return render(request, 'HOGCV.html', context)

def seqCVproteinHOG(request):
    context = {}
    return render(request, 'seqCVproteinHOG.html', context)

def seqCValignHOG(request):
    context = {}
    return render(request, 'seqCValignHOG.html', context)

def seqCVontologyHOG(request):
    context = {}
    return render(request, 'seqCVontologyHOG.html', context)



def ontologyGroupCV(request):
    context = {}
    # list of rows with _speciesId & _dataOfTheSquare(orange,grey,invisible, IEA or IPI, etc) & annotation

    return render(request, 'ontologyGroupCV.html', context)

def proteinGroupCV(request):
    context = {}
    # list of orthologs with TAXON{E/A/B + _speciesName} & _speciesId & _crossReference & _annotation
    return render(request, 'proteinGroupCV.html', context)



