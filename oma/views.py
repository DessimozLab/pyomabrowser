from __future__ import print_function
from builtins import map
from builtins import str
from builtins import range
import collections
import json
from django.shortcuts import render
from django.conf import settings
from django.http import HttpResponse, Http404, HttpResponseRedirect
from django.views.decorators.cache import cache_control
from django.views.generic import TemplateView

from collections import OrderedDict
import numpy
import tweepy
import logging
import itertools
import os
import re
import time
import glob
from io import BytesIO

from . import utils
from . import misc
from . import forms

logger = logging.getLogger(__name__)


class EntryCentricView(TemplateView):
    def get_entry(self, entry_id):
        """resolve any ID and return an entry or a 404 if it is unknown"""
        try:
            entry_nr = utils.id_resolver.resolve(entry_id)
        except utils.InvalidId:
            raise Http404('requested id is unknown')
        entry = utils.db.entry_by_entry_nr(entry_nr)
        return entry

    def get_vpairs(self, entry):
        vps = utils.db.get_vpairs(entry['EntryNr'])
        for vp in vps:
            yield vp

    def get_hog(self, entry, level):
        pass


# Create your views here.
def pairs(request, entry_id, idtype='OMA'):
    entry_nr = utils.id_resolver.resolve(entry_id)
    vps_entry_nr = utils.db.get_vpairs(entry_nr)

    query = utils.id_mapper[idtype].map_entry_nr(entry_nr)
    vps = list(map(utils.id_mapper[idtype].map_entry_nr, vps_entry_nr['EntryNr2']))
    print(len(vps))
    context = {'query': query, 'vps': vps}

    return render(request, 'vpairs.html', context)


def synteny(request, entry_id, mod=4, windows=4, idtype='OMA'):
    """loads data to visualize the synteny around a query 
    gene and it's orthologs.
    the parameter 'mod' is used to keep the color between
    calls on different entries compatible, i.e. they selected
    gene should keep it's color.
    the window paramter is used to select the size of the 
    neighborhood."""

    try:
        entry_nr = utils.id_resolver.resolve(entry_id)
    except utils.InvalidId:
        raise Http404('requested id unknown')

    genome = utils.id_mapper['OMA'].genome_of_entry_nr(entry_nr)
    try:
        lin = utils.tax.get_parent_taxa(genome['NCBITaxonId'])
    except Exception:
        logger.warning("cannot get NCBI Taxonomy for {} ({})".format(
            genome['UniProtSpeciesCode'],
            genome['NCBITaxonId']))
        lin = []
    taxa = []
    for i in lin:
        taxa.append(i[2])
    if len(taxa) > 2:
        sciname = taxa[0].decode()
        kingdom = taxa[-1].decode()
    else:
        sciname = u"unknown"
        kingdom = u"unknown"

    windows = int(windows)
    ngs_entry_nr, gene_left = utils.db.neighbour_genes(entry_nr, windows)
    positions = list(range(-windows, windows + 1))  # list of intergers for gene positions

    blank_l = windows - gene_left
    blank_r1 = windows + len(ngs_entry_nr) - gene_left
    blank_r2 = 2 * windows + 1

    geneinfos = []
    md_geneinfos = {}  # gene informations for first row, entry gene species
    md_geneinfos['genes'] = {}
    query = utils.id_mapper[idtype].map_entry_nr(entry_nr)

    species = genome['UniProtSpeciesCode'].decode()  # Species name of the entr gene

    md_geneinfos['species'] = species
    for i in range(blank_l):
        md_geneinfos['genes'][i] = {"type": "blank"}
    for i in range(blank_r1, blank_r2):
        md_geneinfos['genes'][i] = {"type": "blank"}

    all_entry_nrs = []
    for index, info in enumerate(ngs_entry_nr):
        geneinfo = {
            "entryid": info['EntryNr'],
            "species": species,
            "genenumber": "{0:05d}".format(info['EntryNr'] - genome['EntryOff']),
            "dir": info['LocusStrand'],
            "type": str((index - gene_left + int(mod)) % (windows + windows + 1)),
            "geneindex": index}
        geneinfo["orthologs"] = utils.db.get_vpairs(info['EntryNr'])['EntryNr2']

        if geneinfo["geneindex"] == gene_left:
            entry_dir = geneinfo["dir"]
            md_geneinfos['entry_dir'] = entry_dir

        geneinfos.append(geneinfo)
        all_entry_nrs.append(info['EntryNr'])

        md_geneinfos['genes'][index + blank_l] = geneinfo
        md_geneinfos['genes'] = OrderedDict(
            sorted(list(md_geneinfos['genes'].items()),
                   key=lambda t: t[0]))

    vps_entry_nr = utils.db.get_vpairs(entry_nr)
    orthologs = vps_entry_nr['EntryNr2']

    o_md_geneinfos = {}

    colors = {0: '#9E0142', 1: '#FDAE61', 2: '#E6F598', 3: '#3288BD', 4: '#D53E4F', 5: '#FEE08B',
              6: '#66C2A5', 7: '#5E4FA2', 8: '#F46D43', 9: '#FFFFBF', 10: '#ABDDA4'}
    stripes = {}

    o_sorting = {}
    for ortholog in orthologs:
        o_genome = utils.id_mapper['OMA'].genome_of_entry_nr(ortholog)
        if not o_genome['UniProtSpeciesCode'] in o_sorting:
            try:
                o_lin = utils.tax.get_parent_taxa(o_genome['NCBITaxonId'])
            except Exception:
                logger.warning("cannot get NCBI Taxonomy for {} ({})".format(
                    o_genome['UniProtSpeciesCode'],
                    o_genome['NCBITaxonId']))
                o_lin = []
            num_match = 0
            for i in range(1, min(len(o_lin), len(taxa))):
                if taxa[-i] == o_lin[-i]["Name"]:
                    num_match += 1
            o_sorting[o_genome['UniProtSpeciesCode']] = num_match
    o_sorting = OrderedDict(sorted(list(o_sorting.items()), key=lambda t: t[1], reverse=True))
    o_sorting = [g.decode() for g in o_sorting.keys()][0:50]
    osd = {}  # ortholog sorting dictionary
    for row, each in enumerate(o_sorting):
        osd[each] = row

    for ortholog in orthologs:
        genome = utils.id_mapper['OMA'].genome_of_entry_nr(ortholog)
        o_species = genome['UniProtSpeciesCode'].decode()
        if o_species in o_sorting:
            # get neighbouring genes for each ortholog
            o_neighbors, centerIdx = utils.db.neighbour_genes(int(ortholog), windows)

            row_number = osd[o_species]

            o_blank_l = windows - centerIdx
            o_blank_r1 = windows + len(o_neighbors) - centerIdx
            o_blank_r2 = windows + windows + 1

            o_md_geneinfos[ortholog] = {'o_species': o_species,
                                        'o_sciname': genome['SciName'].decode(),
                                        'row_number': row_number,
                                        'o_genes': {}, }

            for i in range(o_blank_l):
                o_md_geneinfos[ortholog]['o_genes'][i] = {"o_type": "blank"}
            for i in range(o_blank_r1, o_blank_r2):
                o_md_geneinfos[ortholog]['o_genes'][i] = {"o_type": "blank"}

            for index, info in enumerate(o_neighbors):
                all_entry_nrs.append(info['EntryNr'])
                syntenyorthologs = ["not found"]
                o_genome = utils.id_mapper['OMA'].genome_of_entry_nr(info[0])

                o_geneinfo = {
                    "entryid": info['EntryNr'],
                    "species": o_genome['UniProtSpeciesCode'].decode(),
                    "genenumber": "{0:05d}".format(info['EntryNr'] - o_genome['EntryOff']),
                    "sciname": o_genome['SciName'].decode(),
                    "dir": info['LocusStrand'], }

                if o_geneinfo["entryid"] == ortholog:
                    o_md_geneinfos[ortholog]["row_dir"] = o_geneinfo["dir"]

                for geneinfo in geneinfos:
                    if o_geneinfo["entryid"] in geneinfo["orthologs"]:
                        syntenyorthologs.append(str(geneinfo["type"]))  #type for color determination

                if len(syntenyorthologs) == 1:
                    o_geneinfo["o_type"] = "not found"
                elif len(syntenyorthologs) == 2:
                    o_geneinfo["o_type"] = syntenyorthologs[1]
                elif len(syntenyorthologs) >= 3:
                    stripe = ''
                    st_name = ''
                    x = 0
                    for i in syntenyorthologs[1:]:
                        st_name = st_name + (i + "-")
                        if st_name in stripe:
                            stripe = stripe
                        else:
                            stripe = stripe + (
                                colors[int(i)] + ' ' + str(x) + 'px,' + colors[int(i)] + ' ' + str(x + 15) + 'px,')
                        x += 15

                    stripes[st_name] = stripe[:-1]
                    syntenyorthologs.append(st_name)

                    o_geneinfo["o_type"] = syntenyorthologs[1:]

                o_md_geneinfos[ortholog]['o_genes'][index + o_blank_l] = o_geneinfo

            if o_md_geneinfos[ortholog]["row_dir"] == md_geneinfos['entry_dir']:
                o_md_geneinfos[ortholog]['o_genes'] = OrderedDict(
                    sorted(list(o_md_geneinfos[ortholog]['o_genes'].items()), key=lambda t: t[0]))
            elif o_md_geneinfos[ortholog]["row_dir"] != md_geneinfos['entry_dir']:
                o_md_geneinfos[ortholog]['o_genes'] = OrderedDict(
                    sorted(list(o_md_geneinfos[ortholog]['o_genes'].items()), key=lambda t: t[0], reverse=True))

    linkout_mapper = utils.id_mapper['Linkout']
    xrefs = linkout_mapper.xreftab_to_dict(
        linkout_mapper.map_many_entry_nrs(all_entry_nrs))
    for genedict in list(md_geneinfos['genes'].values()):
        if 'entryid' in genedict:
            genedict['xrefs'] = xrefs[genedict['entryid']]
    for o in list(o_md_geneinfos.values()):
        for genedict in list(o['o_genes'].values()):
            if 'entryid' in genedict:
                genedict['xrefs'] = xrefs[genedict['entryid']]

    o_md_geneinfos = OrderedDict(
        sorted(list(o_md_geneinfos.items()),
               key=lambda t: t[1]['row_number']))

    context = {'query': query, 'positions': positions, 'windows': windows,
               'md': md_geneinfos, 'o_md': o_md_geneinfos, 'colors': colors,
               'stripes': stripes, 'nr_vps': len(orthologs),
               'entry': {'omaid': query, 'sciname': misc.format_sciname(sciname),
                         'kingdom': kingdom,
                         'is_homeolog_species': (b"WHEAT" == species)},
               'tab': 'synteny', 'xrefs': xrefs
    }
    return render(request, 'synteny.html', context)


class PairsView(EntryCentricView):
    template_name = "pairs.html"
    attr_of_member = ('omaid', 'sciname', 'kingdom', 'RelType')

    def get_context_data(self, entry_id, **kwargs):
        context = super(PairsView, self).get_context_data(**kwargs)
        entry = self.get_entry(entry_id)
        genome = utils.id_mapper['OMA'].genome_of_entry_nr(entry['EntryNr'])
        vps_raw = sorted(self.get_vpairs(entry), key=lambda x: x['RelType'])
        vps = []
        for vp in vps_raw:
            t = {'omaid': utils.id_mapper['OMA'].map_entry_nr(vp['EntryNr2'])}
            g = utils.id_mapper['OMA'].genome_of_entry_nr(vp['EntryNr2'])
            t['sciname'] = misc.format_sciname(g['SciName'].decode())
            t['kingdom'] = utils.tax.get_parent_taxa(g['NCBITaxonId'])[-1]['Name'].decode()
            t['RelType'] = vp['RelType']
            if 'sequence' in self.attr_of_member:
                t['sequence'] = utils.db.get_sequence(vp['EntryNr2'])
            vps.append(t)

        context.update(
            {'entry': {'omaid': utils.id_mapper['OMA'].map_entry_nr(entry['EntryNr']),
                       'sciname': misc.format_sciname(genome['SciName'].decode()),
                       'kingdom': utils.tax.get_parent_taxa(genome['NCBITaxonId'])[-1]['Name'].decode(),
                       'is_homeolog_species': ("WHEAT" == genome['UniProtSpeciesCode']),
                       'RelType': 'self'},
             'vps': vps, 'nr_vps': len(vps), 'tab': 'orthologs'})
        if 'sequence' in self.attr_of_member:
            context['entry']['sequence'] = utils.db.get_sequence(entry)
        return context


class PairsViewFasta(PairsView):
    attr_of_member = ('omaid', 'sciname', 'kingdom', 'RelType', 'sequence')

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        seqs = []
        header = []
        for memb in itertools.chain([context['entry']], context['vps']):
            seqs.append(memb['sequence'])
            header.append(' | '.join(
                [memb['omaid'], memb['RelType'], '[{species}{strain}]'.format(**memb['sciname'].decode())]))

        response = HttpResponse(content_type='text/plain')
        response.write(misc.as_fasta(seqs, header))
        return response



class HOGsView(EntryCentricView):
    template_name = "hogs.html"
    attr_of_member = ('omaid', 'sciname', 'kingdom')

    def get_context_data(self, entry_id, level=None, idtype='OMA', **kwargs):
        context = super(HOGsView, self).get_context_data(**kwargs)

        entry = self.get_entry(entry_id)
        query = utils.id_mapper[idtype].map_entry_nr(entry['EntryNr'])
        genome = utils.id_mapper['OMA'].genome_of_entry_nr(entry['EntryNr'])

        hog_member_entries = []
        hog = None
        levels = []
        try:
            fam = utils.db.hog_family(entry)
            levs_of_fam = frozenset(utils.db.hog_levels_of_fam(fam))
            lineage = utils.tax.get_parent_taxa(genome['NCBITaxonId'])
            levels = [l for l in itertools.chain(lineage['Name'], ('LUCA',))
                      if l in utils.tax.all_hog_levels and l in levs_of_fam]
            hog = {'id': entry['OmaHOG'], 'fam': fam}
            if not level is None:
                hog_member_entries = utils.db.hog_members(entry, level)
        except utils.Singleton:
            pass
        except ValueError as e:
            raise Http404(str(e))
        except utils.InvalidTaxonId:
            logger.error("cannot get NCBI Taxonomy for {} ({})".format(
                genome['UniProtSpeciesCode'],
                genome['NCBITaxonId']))

        hog_members = []
        for memb in hog_member_entries:
            t = {}
            t['omaid'] = utils.id_mapper['OMA'].map_entry_nr(memb['EntryNr'])
            g = utils.id_mapper['OMA'].genome_of_entry_nr(memb['EntryNr'])
            t['sciname'] = misc.format_sciname(g['SciName'].decode())
            t['kingdom'] = utils.tax.get_parent_taxa(g['NCBITaxonId'])[-1]['Name'].decode()
            t['hogid'] = memb['OmaHOG'].decode()
            if 'sequence' in self.attr_of_member:
                t['sequence'] = utils.db.get_sequence(memb)
            hog_members.append(t)

        nr_vps = utils.db.count_vpairs(entry['EntryNr'])
        context.update(
            {'entry': {'omaid': query,
                       'sciname': misc.format_sciname(genome['SciName'].decode()),
                       'kingdom': utils.tax.get_parent_taxa(genome['NCBITaxonId'])[-1]['Name'].decode(),
                       'is_homeolog_species': (b"WHEAT" == genome['UniProtSpeciesCode'])},
             'level': level, 'hog_members': hog_members,
             'nr_vps': nr_vps, 'tab': 'hogs', 'levels': levels[::-1]})
        if not hog is None:
            context['hog'] = hog
        return context


class HOGsFastaView(HOGsView):
    attr_of_member = ('omaid', 'sciname', 'kingdom', 'sequence')

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        seqs = []
        header = []
        for memb in context['hog_members']:
            seqs.append(memb['sequence'])
            header.append(' | '.join(
                [memb['omaid'], memb['hogid'], '[{species}{strain}]'.format(**memb['sciname'])]))

        response = HttpResponse(content_type='text/plain')
        response.write(misc.as_fasta(seqs, header))
        return response


class HOGsOrthoXMLView(HOGsView):
    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        try:
            fam = context['hog']['fam']
            orthoxml = utils.db.get_orthoxml(fam)
        except KeyError:
            raise Http404('requested id is not part of any HOG')
        except ValueError as e:
            raise Http404(e.message)
        response = HttpResponse(content_type='text/plain')
        response.write(orthoxml)
        return response


class HOGsVis(EntryCentricView):
    template_name = "hog_vis.html"

    def _build_per_species_table(self, entries, subhogids_per_lev, taxonomy):
        per_species = {}
        for e in entries:
            genome = utils.id_mapper['OMA'].genome_of_entry_nr(e['EntryNr'])
            species_dict = per_species.get(genome['SciName'].decode(), {})
            for lin in taxonomy.get_parent_taxa(genome['NCBITaxonId']):
                lin_str = lin['Name'].decode()
                if not lin_str in species_dict:
                    species_dict[lin_str] = [[] for _ in range(len(subhogids_per_lev[lin['Name']]))]
                for k, subhogid in enumerate(subhogids_per_lev[lin['Name']]):
                    if e['OmaHOG'].startswith(subhogid):
                        species_dict[lin_str][k].append(int(e['EntryNr']))
                        break
                else:
                    raise ValueError('no id found for {}({})'.format(e['EntryNr'], e['OmaHOG']))
            per_species[genome['SciName'].decode()] = species_dict
        return per_species

    def get_context_data(self, entry_id, idtype='OMA', **kwargs):
        context = super(HOGsVis, self).get_context_data(**kwargs)
        entry = self.get_entry(entry_id)
        query = utils.id_mapper[idtype].map_entry_nr(entry['EntryNr'])
        genome = utils.id_mapper['OMA'].genome_of_entry_nr(entry['EntryNr'])

        context.update({'tab': 'hogs',
                        'entry': {'omaid': query,
                                  'entry_nr': entry['EntryNr'],
                                  'sciname': misc.format_sciname(genome['SciName'].decode()),
                                  'kingdom': utils.tax.get_parent_taxa(genome['NCBITaxonId'])[-1]['Name'].decode(),
                                  'is_homeolog_species': (b"WHEAT" == genome['UniProtSpeciesCode'])},
                        })
        try:
            fam_nr = utils.db.hog_family(entry)
            levs_of_fam = frozenset(utils.db.hog_levels_of_fam(fam_nr))
            # TODO: avoid doing work twice!
            phylo = utils.tax.phylogeny(levs_of_fam)
            phylo2 = utils.tax.get_induced_taxonomy(levs_of_fam)
            subhogids_per_level = dict((lev, utils.db.get_subhogids_at_level(fam_nr, lev)) for lev in phylo2.tax_table['Name'])
            fam_memb = utils.db.member_of_fam(fam_nr)
            per_species = self._build_per_species_table(fam_memb, subhogids_per_level, phylo2)
            xrefs = {int(e['EntryNr']): {'omaid': utils.id_mapper['OMA'].map_entry_nr(e['EntryNr']),
                                    'id': e['CanonicalId'].decode()} for e in fam_memb}

            context.update({'fam': {'id': 'HOG:{:07d}'.format(fam_nr)},
                            'hog_members': fam_memb,
                            'per_species': json.dumps(per_species),
                            'species_tree': json.dumps(phylo),
                            'xrefs': json.dumps(xrefs),
                            'cnt_per_kingdom': {'Eukaryota': 6, 'Archaea': 1},
                            })
        except utils.Singleton:
            context['isSingleton'] = True
        return context



@cache_control(max_age=1800)
def home(request):
    n_latest_tweets = 3
    try:
        auth = tweepy.OAuthHandler(settings.TWITTER_CONSUMER_KEY, settings.TWITTER_CONSUMER_SECRET)
        auth.set_access_token(settings.TWITTER_ACCESS_TOKEN, settings.TWITTER_ACCESS_TOKEN_SECRET)

        api = tweepy.API(auth)

        public_tweets = api.user_timeline('@OMABrowser', exclude_replies=True,
                                          trim_user=True, include_rts=False, include_entities=True)
        # r = re.compile(r"(http://[^ ]+)")
        tweets = []
        for tweet in public_tweets[:n_latest_tweets]:
            text = tweet.text
            # replace t.co shortened URLs by true urls
            for url in sorted(tweet.entities['urls'], key=lambda x: x['indices'], reverse=True):
                text = (text[:url['indices'][0]] +
                        '<a href="' + url['expanded_url'] + '">' + url['expanded_url'] + '</a>' +
                        text[url['indices'][1]:])
            tweets.append(text)
    except tweepy.TweepError:
        tweets = ['Currently no tweets found']

    context = {'tweets': tweets}
    return render(request, 'home.html', context)


def fellowship(request):
    if request.method == 'POST':
        form = forms.FellowshipApplicationForm(request.POST, request.FILES)
        if form.is_valid():
            att = [(request.FILES[c].name, request.FILES[c]) for c in request.FILES]
            dir = os.path.expanduser(os.path.join('~', 'log', 'fellowship', time.strftime('%Y%b%d-%H%M%S')))
            os.makedirs(dir)
            with open(dir + '/info.txt', 'w') as fh:
                fh.write("Name: {name}\nEmail: {email}\n\nStatement: {interest}".format(**form.cleaned_data))
            for attachement in att:
                with open(dir + '/' + attachement[0], 'wb') as fh:
                    fh.write(attachement[1].read())

            return HttpResponseRedirect('/oma/thanks/')  # Redirect after POST
    else:
        form = forms.FellowshipApplicationForm()
    return render(request, 'fellowship.html', {'form': form})


class CurrentView(TemplateView):
    template_name = "current.html"
    _re_rel2name = re.compile(r'(?:(?P<scope>[A-Za-z]+).)?(?P<month>[A-Za-z]{3})(?P<year>\d{4})')

    def _get_all_releases_with_downloads(self, prefix_filter='All.'):
        try:
            root = os.environ['DARWIN_BROWSER_SHARE']
        except KeyError:
            logger.warn('Cannot determine root dir for downloads.')
            root = ""
        candidate_dirs = list(map(os.path.basename, glob.glob(root + "/" + prefix_filter + "*")))
        rels = [{'name': self._name_from_release(d), 'id': d, 'date': d[max(0, d.find('.') + 1):]}
                for d in candidate_dirs if os.path.exists(os.path.join(root, d, "downloads"))]
        rels = sorted(rels, key=lambda x: -time.mktime(time.strptime(x['name'], "%b %Y")))
        return rels

    def _name_from_release(self, rel):
        """returns the human readable name of a release id, i.e. All.Sep2014 --> Sep 2014"""
        m = self._re_rel2name.match(rel)
        if not m is None:
            rel = "{month} {year}".format(**m.groupdict())
        return rel

    def _get_previous_releases(self, cur, all, cnt=4):
        """return the cnt previous releases from a list of all.

        The method assumes the list is sorted from new releases to old ones."""
        try:
            for i, rel in enumerate(all):
                if rel['id'] == cur['id']:
                    return all[i+1:i+cnt+1]
        except KeyError:
            pass

    def download_root(self, context):
        return "/All"

    def get_release_data(self, release):
        relname = utils.db.get_release_name()
        relid = 'All.' + relname.replace(' ', '')
        return {'name': relname, 'id': relid, 'date': relname.replace(' ', '')}

    def get_context_data(self, release=None, **kwargs):
        context = super(CurrentView, self).get_context_data(**kwargs)
        context['release'] = self.get_release_data(release)
        context['all_releases'] = self._get_all_releases_with_downloads()
        context['release_with_backlinks'] = self._get_previous_releases(context['release'], context['all_releases'])
        context['download_root'] = self.download_root(context)
        return context


class ArchiveView(CurrentView):
    template_name = "archives.html"

    def get_release_data(self, release):
        res = {}
        if not release is None:
            res['id'] = release
            res['name'] = self._name_from_release(release)
            res['date'] = res['name'].replace(' ', '')
        return res

    def download_root(self, context):
        return "/" + context['release'].get('id', '')
