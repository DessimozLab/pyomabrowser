from django.shortcuts import render
from django.http import HttpResponse, Http404

from . import utils

# Create your views here.

def pairs(request, entry_id, idtype='OMA'):
    
    entry_nr = utils.id_resolver.resolve(entry_id)
    vps_entry_nr = utils.db.get_vpairs(entry_nr)
    
    query = utils.id_mapper[idtype].map_entry_nr(entry_nr)
    vps = map(utils.id_mapper[idtype].map_entry_nr, vps_entry_nr['EntryNr2'])
    print(len(vps))
    context = {'query': query, 'vps':vps}
    
    return render(request, 'vpairs.html', context)

def hogs(request, entry_id, level, idtype='OMA'):
    entry_nr = utils.id_resolver.resolve(entry_id)
    query = utils.id_mapper[idtype].map_entry_nr(entry_nr)
    try:
        hog_members = utils.db.hog_members(entry_nr, level)
        print(hog_members)
        hog_member_ids = map(utils.id_mapper[idtype].map_entry_nr, hog_members['EntryNr'])
    except utils.Singleton:
        hog_member_ids = [query]
    except ValueError as e:
        raise Http404(e.message)
    context = {'query': query, 'level': level, 'hog_members': hog_member_ids} 
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

def seqCV(request):
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



