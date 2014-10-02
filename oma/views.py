from django.shortcuts import render
from django.conf import settings
from django.http import HttpResponse, Http404
from collections import OrderedDict
from django.views.decorators.cache import cache_control

import tweepy
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
        o_species = utils.id_mapper[idtype].map_entry_nr(ortholog)[0:5]
        if not o_species in o_sorting:
            o_genome=utils.id_mapper['OMA'].genome_of_entry_nr(ortholog)
            try:
                o_lin=utils.tax.get_parent_taxa(o_genome['NCBITaxonId'])
            except Exception:
                logger.warning("cannot get NCBI Taxonomy for {} ({})".format(
                    o_genome['UniProtSpeciesCode'],
                    o_genome['NCBITaxonId']))
                o_lin=[]
            num_match = 0
            for i in range(1, min(len(o_lin), len(taxa))): 
                if taxa[-i] == o_lin[-i]["Name"]:
                    num_match += 1 
            o_sorting[o_species] = num_match
    o_sorting= OrderedDict(sorted(o_sorting.items(), key=lambda t: t[1], reverse=True))
    o_sorting = o_sorting.keys()[0:50]
    osd = {} #ortholog sorting dictionary
    for row, each in enumerate(o_sorting):
        osd[each]=row


    for ortholog in orthologs:
        genome = utils.id_mapper[idtype].genome_of_entry_nr(ortholog)
        o_species = genome['UniProtSpeciesCode']
        if o_species in o_sorting:
            #get neighbouring genes for each ortholog
            o_ngs_entry_nr = utils.db.neighbour_genes(int(ortholog), windows) 

            row_number = osd[o_species]

            o_blank_l=windows-o_ngs_entry_nr[-1]
            o_blank_r1=windows+len(o_ngs_entry_nr[0])-o_ngs_entry_nr[-1]
            o_blank_r2=windows+windows+1

            o_md_geneinfos[ortholog]={'o_species': o_species, 
                                      'o_sciname': genome['SciName'],
                                      'row_number': row_number,
                                      'o_genes': {},}

            for i in range(o_blank_l):
                o_md_geneinfos[ortholog]['o_genes'][i]={"o_type":"blank"}
            for i in range(o_blank_r1,o_blank_r2):
                o_md_geneinfos[ortholog]['o_genes'][i]={"o_type":"blank"}

            o_allinfo = o_ngs_entry_nr[0]
            o_separate = o_allinfo[0:] #each gene information in original form


            for index, info in enumerate(o_separate):
                syntenyorthologs = ["not found"]
                o_genome = utils.id_mapper[idtype].genome_of_entry_nr(info[0])

                o_geneinfo = {
                    "entryid": info[0],
                    "species": o_genome['UniProtSpeciesCode'],
                    "genenumber": info[0]-o_genome['EntryOff'],
                    "sciname": o_genome['SciName'],
                    "dir":info[-2],}

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
          'entry':{'omaid':query, 'sciname':sciname, 'kingdom':kingdom,
                   'is_homeolog_species':("WHEAT"==species)}, 
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
            'kingdom':utils.tax.get_parent_taxa(genome['NCBITaxonId'])[-1]['Name'],
            'is_homeolog_species':("WHEAT"==genome['UniProtSpeciesCode'])}, 
            'level': level, 'hog_members': hog_members,
            'nr_vps': nr_vps, 'tab':'hogs', 'levels':levels[::-1]}
    if not hog is None:
        context['hog'] = hog

    logging.debug("context:" + str(context))
    return render(request, 'hogs.html', context)


@cache_control(max_age=1800)
def home(request):
    n_latest_tweets = 3
    auth = tweepy.OAuthHandler(settings.TWITTER_CONSUMER_KEY, settings.TWITTER_CONSUMER_SECRET)
    auth.set_access_token(settings.TWITTER_ACCESS_TOKEN, settings.TWITTER_ACCESS_TOKEN_SECRET)

    api = tweepy.API(auth)

    public_tweets = api.user_timeline('@OMABrowser', exclude_replies=True, 
        trim_user=True, include_rts=False, include_entities=True  )
    #r = re.compile(r"(http://[^ ]+)")
    tweets = []
    for tweet in public_tweets[:n_latest_tweets]:
        text = tweet.text
        # replace t.co shortened URLs by true urls
        for url in sorted(tweet.entities['urls'], key=lambda x: x['indices'], reverse=True):
            text = (text[:url['indices'][0]] + 
                    '<a href="' + url['expanded_url'] + '">' + url['expanded_url'] + '</a>' + 
                    text[url['indices'][1]:])
        tweets.append(text)

    context = {'tweets':tweets}
    return render(request, 'home.html', context)

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


