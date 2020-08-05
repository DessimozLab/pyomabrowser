# -*- coding: utf-8 -*-

from __future__ import print_function, division

import shlex
import types
from builtins import map
from builtins import str
from builtins import range
import hashlib
import collections
import pandas as pd
from django.shortcuts import render, redirect
from django.conf import settings
from django.http import HttpResponse, Http404, HttpResponseBadRequest, HttpResponseRedirect, JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control, never_cache
from django.views.generic import TemplateView, View
from django.views.generic.base import ContextMixin
from django.urls import reverse
from django.core.mail import EmailMessage
from django.template import Context
from django.template.loader import render_to_string, get_template
from django.contrib.staticfiles.templatetags.staticfiles import static



from collections import OrderedDict, defaultdict

import tweepy
import logging
import itertools
import os
import re
import time
import glob
import json
import numpy

from . import tasks
from . import utils
from . import misc
from . import forms
from .models import FileResult
from pyoma.browser import db, models

logger = logging.getLogger(__name__)

#<editor-fold desc="General">

# --- General -------
class JsonModelMixin(object):
    """Mixin class to serialize parts of an object to json.

    This class provides the means to serialize the desired parts
    of an object as json. The method :py:meth:`to_json_dict` can
    be called on an iterable, and attributes or methods without
    any argument can will be converted to a dict. This is restricted
    to the attributes/methods defined in :py:attr:`json_fields`.
    These can also be chained together.

    :Example:

    TODO!"""
    json_fields = None

    def to_json_dict(self, iter):
        for row in iter:
            obj_dict = {}
            for accessor, name in self.json_fields.items():
                if name is None:
                    name = accessor
                obj = row
                try:
                    for attr in accessor.split('.'):
                        obj = getattr(obj, attr)
                        if isinstance(obj, (classmethod, types.MethodType)):
                            obj = obj()
                except AttributeError as e:
                    logger.warning('cannot access ' + accessor + ": " + str(e))
                    raise
                obj_dict[name] = obj
            yield obj_dict

    def as_json(self, iter):
        return list(self.to_json_dict(iter))


class FastaResponseMixin(object):
    """A mixin to generate Fasta response."""
    def get_fastaheader(self, member):
        return " | ".join([member.omaid, member.canonicalid, '[{}]'.format(member.genome.sciname)])

    def get_sequence(self, member):
        return member.sequence

    def render_to_fasta_response(self, members):
        seqs = []
        headers = []
        for memb in members:
            seqs.append(self.get_sequence(memb))
            headers.append(self.get_fastaheader(memb))
        return HttpResponse(content_type='text/plain', content=misc.as_fasta(seqs, headers))


class FastaView(FastaResponseMixin, ContextMixin, View):
    """Renders a context into fasta format.

    The default implementation of :meth:`render_to_response` passes the complete
    context to the render method. This usually needs to be overwritten such that an
    iterable with :class:`ProteinEntry` is passed."""

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        return self.render_to_response(context)

    def render_to_response(self, context):
        return self.render_to_fasta_response(context)


class AsyncMsaMixin(object):
    def get_msa_results(self, group_type, *args):
        msa_id = hashlib.md5(group_type.encode('utf-8'))
        for arg in args:
            msa_id.update(str(arg).encode('utf-8'))
        msa_id = msa_id.hexdigest()
        try:
            logger.debug('fetching FileResult for {}'.format(msa_id))
            r = FileResult.objects.get(data_hash=msa_id)
            do_compute = r.remove_erroneous_or_long_pending()
        except FileResult.DoesNotExist:
            do_compute = True

        if do_compute:
            logger.info('require computing msa for {} {}'.format(group_type, args))
            r = FileResult(data_hash=msa_id, result_type='msa_{}'.format(group_type),
                           state="pending")
            r.save()
            tasks.compute_msa.delay(msa_id, group_type, *args)
        return {'msa_file_obj': r}

# //</editor-fold>

#//<editor-fold desc="Entry Centric">

#  --- Entry Centric -------
class EntryCentricMixin(object):
    def get_entry(self, entry_id):
        """resolve any ID and return an entry or a 404 if it is unknown"""
        try:
            entry_nr = utils.id_resolver.resolve(entry_id)
        except (db.InvalidId, db.AmbiguousID):
            raise Http404('requested id is unknown')
        entry = utils.db.entry_by_entry_nr(entry_nr)

        # this need to be added to have root level hog id
        model_entry  = models.ProteinEntry(utils.db, entry)

        if model_entry.oma_hog:
            model_entry.oma_hog_root = model_entry.oma_hog.split(".")[0]
        else:
            model_entry.oma_hog_root = None

        return model_entry


# Information
class InfoBase(ContextMixin, EntryCentricMixin):
    def get_context_data(self, entry_id, **kwargs):
        context = super(InfoBase, self).get_context_data(**kwargs)
        entry = self.get_entry(entry_id)

        nr_ortholog_relations = utils.db.nr_ortholog_relations(entry.entry_nr)


        context.update({'entry': entry, 'tab': 'geneinformation', 'nr_vps': nr_ortholog_relations['NrAnyOrthologs'],
                        'nr_pps':  nr_ortholog_relations['NrHogInducedPWParalogs']  })
        return context


class EntryInfoView(InfoBase, TemplateView):
    template_name = "entry_info.html"


class InfoViewFasta(InfoBase, FastaView):
    def get_fastaheader(self, member):
        return " | ".join([member.omaid, member.canonicalid,
                           "[{}]".format(member.genome.sciname)])

    def render_to_response(self, context, **kwargs):
        return self.render_to_fasta_response([context['entry']])


# Synteny
def synteny(request, entry_id, mod=4, windows=4, idtype='OMA'):
    """loads data to visualize the synteny around a query
    gene and its orthologs.
    the parameter 'mod' is used to keep the color between
    calls on different entries compatible, i.e. they selected
    gene should keep its color.
    the window paramter is used to select the size of the
    neighborhood."""

    try:
        entry_nr = utils.id_resolver.resolve(entry_id)
    except db.InvalidId:
        raise Http404('requested id unknown')
    entry = models.ProteinEntry.from_entry_nr(utils.db, entry_nr)
    genome = utils.id_mapper['OMA'].genome_of_entry_nr(entry_nr)
    # this need to be added to have root level hog id
    entry.oma_hog_root = entry.oma_hog.split(".")[0]
    try:
        taxa = entry.genome.lineage
    except db.InvalidTaxonId:
        logger.warning("cannot get NCBI Taxonomy for {!r}".format(entry.genome))
        taxa = []

    windows = int(windows)
    ngs_entry_nr, gene_left = utils.db.neighbour_genes(entry_nr, windows)
    positions = list(range(-windows, windows + 1))  # list of intergers for gene positions

    blank_l = windows - gene_left
    blank_r1 = windows + len(ngs_entry_nr) - gene_left
    blank_r2 = 2 * windows + 1

    geneinfos = []
    md_geneinfos = {'genes': {}}  # gene informations for first row, entry gene species
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
            "species": entry.genome.uniprot_species_code,
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

    # select the closest NR_GENOMES_TO_KEEP genomes
    NR_GENOMES_TO_KEEP = 50
    nr_shared_lins_per_genome = collections.Counter()
    for ortholog in orthologs:
        o_genome = utils.Genome(utils.id_mapper['OMA'].genome_of_entry_nr(ortholog))
        if not o_genome.uniprot_species_code in nr_shared_lins_per_genome:
            num_match = 0
            try:
                for i in range(1, min(len(o_genome.lineage), len(taxa))):
                    if taxa[-i] == o_genome.lineage[-i]:
                        num_match += 1
            except db.InvalidTaxonId:
                logger.exception("cannot get NCBI Taxonomy for {} ({})"
                                 .format(o_genome.uniprot_species_code, o_genome.ncbi_taxon_id))
            nr_shared_lins_per_genome[o_genome.uniprot_species_code] = num_match
    o_sorting = [g[0] for g in nr_shared_lins_per_genome.most_common(NR_GENOMES_TO_KEEP)]

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
                            stripe += colors[int(i)] + ' ' + str(x) + 'px,' + colors[int(i)] + ' ' + str(x + 15) + 'px,'
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


    nr_ortholog_relations = utils.db.nr_ortholog_relations(entry.entry_nr)

    context = {'positions': positions, 'windows': windows,
               'md': md_geneinfos, 'o_md': o_md_geneinfos, 'colors': colors,
               'stripes': stripes, 'nr_vps': nr_ortholog_relations['NrAnyOrthologs'],
               'nr_pps': nr_ortholog_relations['NrHogInducedPWParalogs'],
               'entry': entry,
               'tab': 'synteny', 'xrefs': xrefs
    }
    return render(request, 'entry_localSynteny.html', context)


# Orthologs
class PairsBase(ContextMixin, EntryCentricMixin):
    """Base class to collect data for pairwise orthologs."""

    _max_entry_to_load = 25

    def get_context_data(self, entry_id, **kwargs):


        context = super(PairsBase, self).get_context_data(**kwargs)
        entry = self.get_entry(entry_id)

        nr_ortholog_relations = utils.db.nr_ortholog_relations(entry.entry_nr)

        if nr_ortholog_relations['NrAnyOrthologs'] < self._max_entry_to_load:
            load_full_data = 0
            url = reverse('pairs_support_json', args=(entry.omaid,))
        else:
            url = reverse('pairs_support_sample_json', args=(entry.omaid,))
            load_full_data = reverse('pairs_support_json', args=(entry.omaid,))

        context.update(
            {'entry': entry, 'nr_pps': nr_ortholog_relations['NrHogInducedPWParalogs'], 'nr_vps': nr_ortholog_relations['NrAnyOrthologs'], 'tab': 'orthologs',
             'table_data_url': url , 'load_full_data': load_full_data, 'sample_size': self._max_entry_to_load,
             })

        return context


class PairsJson(PairsBase, JsonModelMixin, View):
    json_fields = {'omaid': 'protid', 'genome.kingdom': 'kingdom',
                   'genome.species_and_strain_as_dict': 'taxon',
                   'canonicalid': 'xrefid', 'RelType': 'RelType'}

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        data = list(self.to_json_dict(context['vps']))
        return JsonResponse(data, safe=False)


class PairsJson_Support(PairsBase, JsonModelMixin, View):


    json_fields = {'omaid': 'protid', 'genome.kingdom': 'kingdom',
                   'genome.species_and_strain_as_dict': 'taxon',
                   'canonicalid': 'xrefid', 'RelType': 'RelType', 'type_p': 'type_p','type_h':'type_h','type_g':'type_g'}

    def get(self, request, *args, **kwargs):

        context = self.get_context_data(**kwargs)

        entry = context['entry']

        # Get orthologs
        # /!\ in orde  d introduce mistake, we keep the var vps and nr_vps. Nevertheless, this object will contain vps, HOG pairs and GO pair.
        orthologs_dict = {}
        entry_db = utils.db.entry_by_entry_nr(entry.entry_nr)

        start = time.time()

        ## Get VPS
        vps_raw = sorted(utils.db.get_vpairs(entry.entry_nr), key=lambda x: x['RelType'])
        pps = utils.db.get_hog_induced_pairwise_paralogs(entry.entry_nr)
        for rel in itertools.chain(vps_raw):
            pw_relation = models.ProteinEntry.from_entry_nr(utils.db, rel['EntryNr2'])
            # pw_relation.RelType = rel['RelType']
            # if len(rel['RelType']) == 3:
            #    pw_relation.RelType += " ortholog"

            pw_relation.type_p = 1

            orthologs_dict[rel['EntryNr2']] = pw_relation

        ## Get HOG orthologs
        hog_pair = utils.db.get_hog_induced_pairwise_orthologs(entry_db)
        for en in hog_pair:

            if en[0] in orthologs_dict.keys():
                pw_relation = orthologs_dict[en[0]]
            else:
                pw_relation = models.ProteinEntry.from_entry_nr(utils.db, en[0])

            if not hasattr(pw_relation, 'RelType'):
                pw_relation.RelType = en[-1].decode()

            pw_relation.type_h = 1

            orthologs_dict[en[0]] = pw_relation

        ## Get OG orthologs

        if entry.oma_group != 0:

            OG_pair = list(utils.db.oma_group_members(entry.oma_group))
            OG_pair.remove(entry_db)

            for ent in OG_pair:

                if ent[0] in orthologs_dict.keys():
                    pw_relation = orthologs_dict[ent[0]]
                else:
                    pw_relation = models.ProteinEntry.from_entry_nr(utils.db, ent[0])

                # if not hasattr(pw_relation, 'RelType'):
                #    pw_relation.RelType = None

                pw_relation.type_g = 1

                orthologs_dict[ent[0]] = pw_relation

        vps = orthologs_dict.values()

        # populate with inference evidence missing attribute
        for rel in vps:

            if not hasattr(rel, 'RelType'):
                rel.RelType = None

            if not hasattr(rel, 'type_p'):
                rel.type_p = 0

            if not hasattr(rel, 'type_h'):
                rel.type_h = 0

            if not hasattr(rel, 'type_g'):
                rel.type_g = 0

        end = time.time()
        logger.info("[{}] Pairs modeled {}".format(context['entry'].omaid, start - end))

        entry.RelType = 'self'
        if entry._entry['AltSpliceVariant'] in (0, entry.entry_nr):
            entry.alt_splicing_variant = entry.omaid
        else:
            entry.alt_splicing_variant = utils.id_mapper['OMA'].map_entry_nr(entry._entry['AltSpliceVariant'])

        longest_seq = 0
        if len(vps) > 0:
            longest_seq = max(e.sequence_length for e in vps)


        start = time.time()

        data = list(self.to_json_dict(vps))

        end = time.time()

        logger.info("[{}] Json formatting {}".format(context['entry'].omaid, start - end))

        return JsonResponse(data, safe=False)


class PairsJson_SupportSample(PairsBase, JsonModelMixin, View):

        json_fields = {'omaid': 'protid', 'genome.kingdom': 'kingdom',
                       'genome.species_and_strain_as_dict': 'taxon',
                       'canonicalid': 'xrefid', 'RelType': 'RelType', 'type_p': 'type_p', 'type_h': 'type_h',
                       'type_g': 'type_g'}

        def get(self, request, *args, **kwargs):

            context = self.get_context_data(**kwargs)

            entry = context['entry']
            entry_db = utils.db.entry_by_entry_nr(entry.entry_nr)

            orthologs_dict = {}
            vps_raw = sorted(utils.db.get_vpairs(entry.entry_nr), key=lambda x: x['RelType'])
            for rel in itertools.chain(vps_raw):
                pw_relation = models.ProteinEntry.from_entry_nr(utils.db, rel['EntryNr2'])
                pw_relation.type_p = 1
                orthologs_dict[rel['EntryNr2']] = pw_relation

            vps = orthologs_dict.values()
            if len(vps) > PairsBase._max_entry_to_load:
                vps = list(vps)
                vps = vps[0:PairsBase._max_entry_to_load]

            # populate with inference evidence missing attribute
            for rel in vps:

                rel_db = utils.db.entry_by_entry_nr(rel.entry_nr)

                if not hasattr(rel, 'RelType'):
                    rel.RelType = None

                if not hasattr(rel, 'type_p'):
                    rel.type_p = 0

                if not hasattr(rel, 'type_h'):

                    rel.type_h = 1

                    prefix = os.path.commonprefix((entry_db["OmaHOG"], rel_db["OmaHOG"])).decode()
                    if "." in prefix and prefix[-1].isdigit():
                        rel.type_h = 0


                if not hasattr(rel, 'type_g'):
                    if entry.oma_group != 0:
                        if entry.oma_group == rel.oma_group:
                            rel.type_g = 1
                        else:
                            rel.type_g = 0
                    else:
                        rel.type_g = 0


            entry.RelType = 'self'

            data = list(self.to_json_dict(vps))

            return JsonResponse(data, safe=False)


class PairsView(TemplateView, PairsBase):
    template_name = "entry_orthology.html"


class PairsViewFasta(FastaView, PairsBase):
    """returns a fasta represenation of all the pairwise orthologs"""
    def get_fastaheader(self, memb):
        return ' | '.join(
                [memb.omaid, memb.canonicalid, memb.reltype,
                 '[{}]'.format(memb.genome.sciname)])

    def render_to_response(self, context, **kwargs):
        return self.render_to_fasta_response(itertools.chain([context['entry']], context['vps']))


# Paralogs
class ParalogsBase(ContextMixin, EntryCentricMixin):
    """Base class to collect data for paralogs."""

    _max_entry_to_load = 25

    def get_context_data(self, entry_id, **kwargs):

        context = super(ParalogsBase, self).get_context_data(**kwargs)
        entry = self.get_entry(entry_id)

        nr_ortholog_relations = utils.db.nr_ortholog_relations(entry.entry_nr)

        if nr_ortholog_relations['NrHogInducedPWParalogs'] < self._max_entry_to_load:
            load_full_data = 0
            url = reverse('paralogs_json', args=(entry.omaid,))
        else:
            url = reverse('paralogs_sample_json', args=(entry.omaid,))
            load_full_data = reverse('paralogs_json', args=(entry.omaid,))

        context.update(
            {'entry': entry, 'nr_pps': nr_ortholog_relations['NrHogInducedPWParalogs'],
             'nr_vps': nr_ortholog_relations['NrAnyOrthologs'], 'tab': 'paralogs',
             'table_data_url': url, 'load_full_data': load_full_data, 'sample_size': self._max_entry_to_load,
             })

        return context


class ParalogsView(TemplateView, ParalogsBase):
    template_name = "entry_paralogy.html"


class ParalogsJson(ParalogsBase, JsonModelMixin, View):

    json_fields = {'omaid': 'protid', 'genome.kingdom': 'kingdom',
                   'genome.species_and_strain_as_dict': 'taxon',
                   'canonicalid': 'xrefid', 'DivergenceLevel': 'DivergenceLevel'}

    def get(self, request, *args, **kwargs):

        context = self.get_context_data(**kwargs)

        entry = context['entry']

        pps = []

        for p in utils.db.get_hog_induced_pairwise_paralogs(entry.entry_nr):
            pm = models.ProteinEntry.from_entry_nr(utils.db, p[0])
            pm.DivergenceLevel = p["DivergenceLevel"].decode('utf-8')
            pps.append(pm)

        start = time.time()

        data = list(self.to_json_dict(pps))

        end = time.time()

        logger.info("[{}] Json formatting {}".format(context['entry'].omaid, end - start))

        return JsonResponse(data, safe=False)


class ParalogsSampleJson(ParalogsBase, JsonModelMixin, View):
    json_fields = {'omaid': 'protid', 'genome.kingdom': 'kingdom',
                   'genome.species_and_strain_as_dict': 'taxon',
                   'canonicalid': 'xrefid', 'DivergenceLevel': 'DivergenceLevel'}

    def get(self, request, *args, **kwargs):

        context = self.get_context_data(**kwargs)

        entry = context['entry']

        pps = []

        for p in utils.db.get_hog_induced_pairwise_paralogs(entry.entry_nr):
            pm = models.ProteinEntry.from_entry_nr(utils.db, p[0])
            pm.DivergenceLevel = p["DivergenceLevel"].decode('utf-8')
            pps.append(pm)

        if len(pps) > ParalogsBase._max_entry_to_load:
            pps = list(pps)
            pps = pps[0:PairsBase._max_entry_to_load]

        data = list(self.to_json_dict(pps))

        return JsonResponse(data, safe=False)


# Isoform
class Entry_Isoform(TemplateView, InfoBase):
    template_name = "entry_isoform.html"

    def get_context_data(self, entry_id, **kwargs):
        context = super(Entry_Isoform, self).get_context_data(entry_id, **kwargs)
        entry = self.get_entry(entry_id)

        isoforms = entry.alternative_isoforms
        main_isoform = entry.is_main_isoform

        for iso in isoforms:
            if iso.is_main_isoform:
                main_isoform = iso

        isoforms = isoforms.append(entry)

        context.update(
            {'entry': entry,
             'tab': 'isoform',
             'isoforms': isoforms,
             'main_isoform': main_isoform,
             'table_data_url': reverse('isoforms_json', args=(entry.omaid,))})
        return context


class IsoformsJson(Entry_Isoform, JsonModelMixin, View):
    json_fields = {'omaid': 'protid',
                   'canonicalid': 'xrefid',
                   'sequence_length': 'seqlen',
                   'is_main_isoform': None,
                   'locus_start': 'locus_start',
                   'locus_end' : 'locus_end',
                   'exons.as_list_of_dict': 'exons'}


    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        data = list(self.to_json_dict(context['isoforms']))

        return JsonResponse(data, safe=False)

# GOA
class Entry_GOA(TemplateView, InfoBase):
    template_name = "entry_goa.html"

    def get_context_data(self, entry_id, **kwargs):
        context = super(Entry_GOA, self).get_context_data(entry_id, **kwargs)
        entry = self.get_entry(entry_id)

        context.update(
            {'entry': entry,
              'tab': 'goa'})
        return context


# Sequences
class Entry_sequences(TemplateView, InfoBase):
    template_name = "entry_sequences.html"

    def get_context_data(self, entry_id, **kwargs):
        context = super(Entry_sequences, self).get_context_data(entry_id, **kwargs)
        entry = self.get_entry(entry_id)

        context.update(
            {'entry': entry,
              'tab': 'sequences'})
        return context


class FamBase(ContextMixin, EntryCentricMixin):

    def get_context_data(self, entry_id, start=0, stop=None, **kwargs):
        context = super(FamBase, self).get_context_data(**kwargs)
        entry = self.get_entry(entry_id)
        famhog_id = utils.db.format_hogid(utils.db.hog_family(entry.entry_nr))
        fam_members = list(utils.db.iter_members_of_hog_id(famhog_id, start, stop))
        context.update({'entry': entry, 'fam_members': fam_members})
        return context


class FamGeneDataJson(FamBase, JsonModelMixin, View):
    json_fields = {'entry_nr': 'id', 'omaid': 'protid', 'sequence_length': None,
                   'genome.species_and_strain_as_dict': 'taxon',
                   'canonicalid': 'xrefid', 'gc_content': None}

    def get(self, request, *args, **kwargs):
        offset = int(request.GET.get('offset', 0))
        limit = request.GET.get('limit', None)
        if limit is not None:
            limit = offset + int(limit)
        context = self.get_context_data(start=offset, stop=limit, **kwargs)
        data = [x for x in self.to_json_dict(context['fam_members'])]
        response = JsonResponse(data, safe=False)
        response['Access-Control-Allow-Origin'] = '*'
        return response


class InfoView(InfoBase, TemplateView):
    template_name = "entry_info.html"

    def get_context_data(self, entry_id, **kwargs):
        context = super(InfoView, self).get_context_data(entry_id, **kwargs)

        nr_ortholog_relations = utils.db.nr_ortholog_relations(context['entry'].entry_nr)
        context['nr_pps']= nr_ortholog_relations['NrHogInducedPWParalogs']
        context['nr_vps']= nr_ortholog_relations['NrAnyOrthologs']
        context['tab'] = 'geneinformation'
        if context['entry'].genome.is_polyploid:
            context['nr_hps'] = utils.db.count_homoeologs(context['entry'].entry_nr)
        return context


class InfoViewFasta(InfoBase, FastaView):
    def get_fastaheader(self, member):
        return " | ".join([member.omaid, member.canonicalid,
                           "[{}]".format(member.genome.sciname)])

    def render_to_response(self, context, **kwargs):
        return self.render_to_fasta_response([context['entry']])


class InfoViewCDSFasta(InfoViewFasta):
    def get_sequence(self, member):
        return member.cdna


class HomoeologBase(ContextMixin, EntryCentricMixin):
    def get_context_data(self, entry_id, **kwargs):
        context = super(HomoeologBase, self).get_context_data(**kwargs)
        entry = self.get_entry(entry_id)
        hps_raw = sorted(utils.db.get_homoeologs(entry.entry_nr), key=lambda x: -x['Confidence'])
        hps = [models.PairwiseRelation(utils.db, rel) for rel in hps_raw]

        if entry.is_main_isoform:
            entry.alt_splicing_variant = entry.omaid
        else:
            entry.alt_splicing_variant = utils.id_mapper['OMA'].map_entry_nr(entry._entry['AltSpliceVariant'])

        longest_seq = 0
        if len(hps) > 0:
            longest_seq = max(e.entry_2.sequence_length for e in hps)

        nr_ortholog_relations = utils.db.nr_ortholog_relations(context['entry'].entry_nr)

        context.update(
            {'entry': entry, 'nr_vps': nr_ortholog_relations['NrAnyOrthologs'], 'nr_vps':nr_ortholog_relations['NrAnyOrthologs'],
             'hps': hps, 'nr_hps': len(hps), 'tab': 'homoeologs',
             'longest_seq': longest_seq})
        return context


class HomoeologView(HomoeologBase, TemplateView):
    template_name = "homoelogs.html"


class HomoeologFasta(HomoeologBase, FastaView):
    """returns a fasta represenation of all the homoeologs"""
    def get_fastaheader(self, memb):
        reltype = memb.reltype if hasattr(memb, 'reltype') else 'self'
        conf = memb.confidence if hasattr(memb, 'confidence') else 100
        return ' | '.join(
                [memb.omaid, memb.canonicalid, reltype,
                 'Confidence:{:.2f}'.format(conf),
                 '[{}]'.format(memb.genome.sciname)])

    def render_to_response(self, context, **kwargs):
        extended_entries = []
        for rel in context['hps']:
            e = rel.entry_2
            e.confidence = rel.confidence
            e.reltype = rel.rel_type
            extended_entries.append(e)

        return self.render_to_fasta_response(itertools.chain(
            [context['entry']], extended_entries))


class HomoeologJson(HomoeologBase, JsonModelMixin, View):
    json_fields = {'entry_2.omaid': 'protid',
                   'entry_2.genome.kingdom': 'kingdom',
                   'entry_2.genome.species_and_strain_as_dict': 'taxon',
                   'entry_2.canonicalid': 'xrefid',
                   'confidence': None, 'entry_2.subgenome': 'subgenome'}

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        data = list(self.to_json_dict(context['hps']))
        return JsonResponse(data, safe=False)

# //</editor-fold>

#<editor-fold desc="Genome Centric">

class GenomeBase(ContextMixin):
    def get_context_data(self, specie_id, **kwargs):
        context = super(GenomeBase, self).get_context_data(**kwargs)
        try:
            genome_obj = models.Genome(utils.db, utils.db.id_mapper['OMA'].genome_from_UniProtCode(specie_id))
            meta = utils.db.per_species_metadata_retriever(specie_id)
            context['genome'] = genome_obj
            context['genome_meta'] = meta
        except db.InvalidId as e:
            raise Http404(e)
        return context


class GenomeCentricInfo(GenomeBase, TemplateView):
    template_name = "genome_info.html"

    def get_context_data(self, specie_id, **kwargs):
        context = super(GenomeCentricInfo, self).get_context_data(specie_id, **kwargs)

        prot_in_group = context['genome_meta'].get_nr_genes_in_group(group_type="OMAGroup")
        prot_in_hogs = context['genome_meta'].get_nr_genes_in_group(group_type="HOG")

        context.update({'tab': 'information', "prot_in_group":prot_in_group, "prot_in_hogs" :prot_in_hogs })
        return context


class GenomeCentricGenes(GenomeBase, TemplateView):
    template_name = "genome_genes.html"

    def get_context_data(self, specie_id, **kwargs):
        context = super(GenomeCentricGenes, self).get_context_data(specie_id, **kwargs)

        context.update({'tab': 'genes', 'api_base': 'genome', 'api_url': '/api/genome/{}/proteins/?&per_page=250000'.format(specie_id)})
        return context


class GenomeCentricClosestGroups(GenomeBase, TemplateView):
    template_name = "genome_closest_groups.html"

    def get_context_data(self, specie_id, **kwargs):
        context = super(GenomeCentricClosestGroups, self).get_context_data(specie_id, **kwargs)
        gr_close_raw = context['genome_meta'].get_most_similar_species(limit=10, group_type='OMAGroup')
        gr_close = []
        for g in gr_close_raw:
            gr_close.append({'genome':models.Genome(utils.db, utils.db.id_mapper['OMA'].genome_from_UniProtCode(g[0])), 'nbr':g[1]})
        gr_least_raw = context['genome_meta'].get_least_similar_species(limit=10, group_type='OMAGroup')
        gr_least = []
        for g in gr_least_raw:
            gr_least.append({'genome': models.Genome(utils.db, utils.db.id_mapper['OMA'].genome_from_UniProtCode(g[0])) , 'nbr': g[1]})
        context.update({'tab': 'closest', 'subtab':'groups', 'closest':gr_close, 'least':gr_least })
        return context


class GenomeCentricClosestHOGs(GenomeBase, TemplateView):
    template_name = "genome_closest_hogs.html"

    def get_context_data(self, specie_id, **kwargs):
        context = super(GenomeCentricClosestHOGs, self).get_context_data(specie_id, **kwargs)
        hog_closest_raw = context['genome_meta'].get_most_similar_species(limit=10, group_type='HOG')
        hog_least_raw = context['genome_meta'].get_least_similar_species(limit=10, group_type='HOG')

        hog_closest = []
        for g in hog_closest_raw:
            hog_closest.append({'genome':models.Genome(utils.db, utils.db.id_mapper['OMA'].genome_from_UniProtCode(g[0])), 'nbr':g[1]})

        hog_least = []
        for g in hog_least_raw:
            hog_least.append({'genome':models.Genome(utils.db, utils.db.id_mapper['OMA'].genome_from_UniProtCode(g[0])), 'nbr':g[1]})


        context.update({'tab': 'closest', 'subtab':'hogs', 'closest':hog_closest, 'least':hog_least })
        return context


class GenomeCentricSynteny(GenomeBase, TemplateView):
    template_name = "genome_synteny.html"

    def get_context_data(self, specie_id, **kwargs):
        context = super(GenomeCentricSynteny, self).get_context_data(specie_id, **kwargs)
        genome_obj = models.Genome(utils.db, utils.db.id_mapper['OMA'].genome_from_UniProtCode(specie_id))
        context.update({'tab': 'synteny', 'genome_obj':genome_obj})
        return context

#</editor-fold >

#<editor-fold desc="Ancestral Genome Centric">

class AncestralGenomeBase(ContextMixin):

    def get_context_data(self, specie_id, **kwargs):
        context = super(AncestralGenomeBase, self).get_context_data(**kwargs)
        try:

            url = os.path.join(os.environ['DARWIN_BROWSERDATA_PATH'], 'genomes.json')

            def iterdict(d, search, query):
                for k, v in d.items():
                    if k == 'taxid' or  k == 'name':
                        if str(v).lower() == str(query).lower():
                            search = d
                    if k == 'children':
                        for c in v:
                            search = iterdict(c, search, query)
                return search


            def count_species(d, cpt):
                for k, v in d.items():
                    cpt +=1
                    if k == 'children':
                        for c in v:
                            cpt = count_species(c, cpt)
                return cpt

            search = iterdict(json.load(open(url, 'r')), False, specie_id)


            if search:

                context['taxid'] = search['taxid']
                context['genome_name'] = search['name']
                context['nr_hogs'] = search['nr_hogs']
                context['nbr_species'] = count_species(search, 0)

            else:
                raise ValueError
        except ValueError as e:
            raise Http404(e)
        return context


class AncestralGenomeCentricInfo(AncestralGenomeBase, TemplateView):
    template_name = "ancestralgenome_info.html"

    def get_context_data(self, specie_id, **kwargs):
        context = super(AncestralGenomeCentricInfo, self).get_context_data(specie_id, **kwargs)

        context.update({'tab': 'information'})
        return context


class AncestralGenomeCentricGenes(AncestralGenomeBase, TemplateView):
    template_name = "ancestralgenome_genes.html"

    def get_context_data(self, specie_id, **kwargs):
        context = super(AncestralGenomeCentricGenes, self).get_context_data(specie_id, **kwargs)

        context.update({'tab': 'genes', 'api_url': '/api/hog/?level={}&per_page=250000'.format(context['genome_name'])})
        return context



#</editor-fold >

#<editor-fold desc="HOGs Centric">


class HOG_Base(ContextMixin):
    def get_context_data(self, hog_id, level=None, **kwargs):
        context = super(HOG_Base, self).get_context_data(**kwargs)

        try:

            # "dirty" check to verify hog id is correct
            members = [x for x in utils.db.member_of_hog_id(hog_id)]
            if not members:
                raise ValueError('requested hog id is unknown')

            subhogs_list = utils.db.get_subhogs(hog_id)
            fam = utils.db.parse_hog_id(hog_id)


            # Check if level is valid
            if level is None:
                hog = next((x for x in subhogs_list if x.is_root == True), None)
            else:
                hog = next((x for x in subhogs_list if x.level == level), None)

            if hog is None:
                raise ValueError('requested hog cannot be found at level {}'.format(level))


            # check if sub hog or not
            if len(hog_id.split('.')) > 1:
                is_subhog = True
            else:
                if hog.is_root:
                    is_subhog = False
                else:
                    is_subhog = True

            # get members:
            members_sub = [x for x in utils.db.member_of_hog_id(hog_id, level=level)]

            #update context
            context['hog_id'] = hog_id
            context['root_id'] = hog_id.split('.')[0]
            context['hog_fam'] = fam
            context['level'] = hog.level
            context['members'] = members_sub
            context['is_subhog'] = is_subhog
            context['api_base'] = 'hog'



        except ValueError as e:
            raise Http404(e)
        return context


class HOGInfo(HOG_Base, TemplateView):
    template_name = "hog_info.html"

    def get_context_data(self, hog_id, **kwargs):
        context = super(HOGInfo, self).get_context_data(hog_id, **kwargs)


        sh = []


        all_levels = utils.db.hog_levels_of_fam(context['hog_fam'],deduplicate_and_decode=True)

        for l in all_levels:

            print(l)
            ids = utils.db.get_subhogids_at_level(context['hog_fam'],l)
            print(ids)

            for i in ids:
                sh.append([i, l])

        context.update({'tab': 'info', 'sub-hog':sh})
        return context


class HOGSimilarProfile(HOG_Base, TemplateView):
    template_name = "hog_similar_profile.html"

    def get_context_data(self, hog_id, idtype='OMA', **kwargs):
        context = super(HOGSimilarProfile, self).get_context_data(hog_id, **kwargs)

        class NumpyEncoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, numpy.ndarray):
                    return obj.tolist()
                return json.JSONEncoder.default(self, obj)


        results = utils.db.get_families_with_similar_hog_profile(context['hog_fam'])

        sim_hogs = results.similar
        top_10_keys = list(sim_hogs.keys())
        top_10_hogs = {k: sim_hogs[k] for k in top_10_keys }

        sim_json = json.dumps(top_10_hogs, cls=NumpyEncoder)

        ref_profile = {"Reference": results.query_profile}
        ref_json = json.dumps(ref_profile, cls=NumpyEncoder)

        taxon_region = results.tax_classes
        tax_json = json.dumps(taxon_region,  cls=NumpyEncoder)

        species = results.species_names
        sp_json = json.dumps(species, cls=NumpyEncoder)
        
        
        """

        sim_json = '{"511509": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 1, 1, 0, 1, 0, 1, 0, 1, 1, 1, 1, 0, 1, 1, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 1, 0, 1, 0, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 0, 1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1], "500596": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 0, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 0, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 0, 1, 0, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 1], "514319": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 0, 1, 1, 1, 1, 1, 0, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 0, 1, 1, 0, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 1, 1, 0, 1, 1, 0, 0, 0, 1], "504783": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 1, 1, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 0, 1, 1, 0, 1, 1, 1, 0, 1, 1, 1, 0, 1, 1, 0, 0, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 0, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0], "500089": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 0, 0, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 1, 0, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 1, 0, 1, 0, 1, 1, 1, 1, 0, 1, 0, 0, 1, 1, 0, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 0, 0, 0, 1]}'

        ref_json = '{"Reference":[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 0, 0, 1, 0, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 0, 1, 0, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 0, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 0, 0, 1, 0, 0, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 0, 0, 1]}'

        tax_json = '{ "50": {"Flavobacteriia": [0, 38], "Bacteroidia": [42, 66], "Cytophagia": [66, 78], "Chlorobi": [85, 96], "Nostocales": [96, 102], "Oscillatoriophycideae": [104, 118], "Synechococcales": [118, 148], "Thiotrichales": [149, 168], "Pseudomonadales": [168, 209], "Escherichia": [214, 258], "Klebsiella": [258, 264], "Salmonella": [264, 285], "Shigella": [285, 292], "Erwiniaceae": [303, 325], "Pectobacteriaceae": [325, 334], "Yersiniaceae": [334, 356], "Morganellaceae": [359, 366], "Legionellales": [369, 381], "Chromatiales": [381, 391], "Xanthomonadales": [391, 411], "Oceanospirillales": [418, 428], "Alteromonadales": [428, 464], "Vibrionales": [464, 483], "Pasteurellales": [488, 510], "Bartonellaceae": [514, 521], "Bradyrhizobiaceae": [522, 536], "Rhizobiaceae": [547, 564], "Brucellaceae": [564, 576], "Methylobacteriaceae": [577, 585], "Rickettsiales": [589, 628], "Rhodospirillales": [633, 645], "Rhodobacterales": [645, 665], "Sphingomonadales": [665, 674], "Caulobacterales": [674, 681], "Nitrosomonadales": [683, 694], "Alcaligenaceae": [694, 706], "Comamonadaceae": [711, 726], "Burkholderiaceae": [726, 764], "Neisseriales": [770, 789], "Deltaproteobacteria": [794, 843], "Helicobacteraceae": [845, 878], "Campylobacteraceae": [878, 896], "Staphylococcaceae": [903, 936], "Bacillaceae": [936, 982], "Listeriaceae": [983, 995], "Paenibacillaceae": [996, 1004], "Streptococcus suis": [1016, 1023], "Streptococcus pneumoniae": [1033, 1050], "Streptococcus pyogenes": [1050, 1062], "Lactococcus": [1079, 1087], "Lactobacillaceae": [1087, 1125], "Leuconostocaceae": [1125, 1134], "Enterococcaceae": [1134, 1141], "Thermoanaerobacterales": [1148, 1170], "Clostridiaceae": [1170, 1197], "Lachnospiraceae": [1200, 1206], "Peptococcaceae": [1213, 1228], "Deinococcus-Thermus": [1251, 1266], "Coriobacteriia": [1270, 1277], "Bifidobacteriales": [1277, 1299], "Micrococcales": [1299, 1327], "Corynebacteriaceae": [1327, 1354], "Mycobacteriaceae": [1354, 1391], "Nocardiaceae": [1391, 1397], "Micromonosporales": [1401, 1409], "Propionibacteriales": [1409, 1418], "Pseudonocardiales": [1418, 1426], "Streptomycetales": [1426, 1452], "Acidobacteria": [1481, 1489], "Aquificae": [1509, 1519], "Thermotogae": [1519, 1533], "Chloroflexi": [1533, 1549], "Planctomycetes": [1549, 1556], "Spirochaetes": [1556, 1597], "Chlamydiae": [1597, 1627], "Tenericutes": [1633, 1683], "Crenarchaeota": [1688, 1732], "Methanobacteria": [1732, 1740], "Methanococci": [1740, 1755], "Halobacteria": [1755, 1778], "Thermoplasmata": [1778, 1784], "Thermococci": [1784, 1796], "Methanomicrobia": [1801, 1823], "Chlorophyta": [1848, 1855], "Magnoliopsida": [1858, 1907], "Fungi incertae sedis": [1911, 1920], "Saccharomycotina": [1925, 1951], "Eurotiomycetes": [1954, 1971], "dothideomyceta": [1971, 1983], "sordariomyceta": [1983, 2010], "Basidiomycota": [2010, 2046], "Nematoda": [2054, 2067], "Hexapoda": [2073, 2122], "Lophotrochozoa": [2123, 2130], "Actinopterygii": [2135, 2160], "Sauropsida": [2163, 2177], "Laurasiatheria": [2187, 2206], "Euarchontoglires": [2206, 2245], "Alveolata": [2252, 2285], "Stramenopiles": [2285, 2301], "Euglenozoa": [2301, 2312], "Amoebozoa": [2318, 2325]}, "200": {"Bacteroidetes": [0, 85], "Cyanobacteria": [96, 149], "Pseudomonadales": [168, 209], "Enterobacterales": [209, 366], "Alteromonadales": [428, 464], "Pasteurellales": [488, 510], "Alphaproteobacteria": [514, 683], "Betaproteobacteria": [683, 794], "delta/epsilon subdivisions": [794, 898], "Bacillales": [903, 1010], "Lactobacillales": [1010, 1143], "Clostridia": [1143, 1242], "Bifidobacteriales": [1277, 1299], "Micrococcales": [1299, 1327], "Corynebacteriales": [1327, 1401], "Streptomycetales": [1426, 1452], "Spirochaetes": [1556, 1597], "Chlamydiae": [1597, 1627], "Tenericutes": [1633, 1683], "Archaea": [1688, 1841], "Viridiplantae": [1848, 1911], "Fungi": [1911, 2046], "Eumetazoa": [2048, 2247], "Alveolata": [2252, 2285]}, "root": {"Bacteria": [0, 1688], "Archaea": [1688, 1841], "Eukaryota": [1841, 2326]}}'

        sp_json = '["Flavobacteria bacterium (strain BBFL7)", "Blattabacterium sp. subsp. Periplaneta americana (strain BPLAN)", "Blattabacterium sp. subsp. Blattella germanica (strain Bge)", "Flavobacterium johnsoniae (strain ATCC 17061 / DSM 2064 / UW101)", "Flavobacterium columnare (strain ATCC 49512 / CIP 103533 / TG 44/87)", "Flavobacterium branchiophilum (strain FL-15)", "Flavobacterium psychrophilum (strain JIP02/86 / ATCC 49511)", "Flavobacterium frigoris (strain PS1)", "Flavobacterium indicum (strain DSM 17447 / CIP 109464 / GPTSA100-9)", "Flavobacterium sp. (strain CF136)", "Weeksella virosa (strain ATCC 43766 / DSM 16922 / JCM 21250 / NBRC 16016 / NCTC 11634 / CL345/78)", "Capnocytophaga gingivalis", "Capnocytophaga canimorsus (strain 5)", "Capnocytophaga ochracea (strain ATCC 27872 / DSM 7271 / JCM 12966 / NCTC 12371 / VPI 2845)", "Ornithobacterium rhinotracheale (strain ATCC 51463 / DSM 15997 / CCUG 23171 / CIP 104009 / LMG 9086)", "Riemerella anatipestifer (strain RA-GD)", "Psychroflexus torquis (strain ATCC 700755 / ACAM 623)", "Cellulophaga algicola (strain DSM 14237 / IC166 / ACAM 630)", "Cellulophaga lytica (strain ATCC 23178 / DSM 7489 / JCM 8516 / NBRC 14961 / NCIMB 1423 / VKM B-1433 / Cy l20)", "Muricauda ruestringensis (strain DSM 13258 / CIP 107369 / LMG 19739 / B1)", "Zobellia galactanivorans (strain DSM 12802 / CCUG 47099 / CIP 106680 / NCIMB 13871 / Dsij)", "Aequorivita sublithincola (strain DSM 14238 / LMG 21431 / ACAM 643 / 9-3)", "Croceibacter atlanticus (strain ATCC BAA-628 / HTCC2559 / KCTC 12090)", "Robiginitalea biformata (strain ATCC BAA-864 / HTCC2501 / KCTC 12146)", "Maribacter sp. (strain HTCC2170 / KCCM 42371)", "Leeuwenhoekiella blandensis (strain CECT 7118 / CCUG 51940 / MED217)", "Lacinutrix sp. (strain 5H-3-7-4)", "Gramella forsetii (strain KT0803)", "Dokdonia sp. (strain 4H-3-7-5)", "Nonlabens dokdonensis (strain DSM 17205 / KCTC 12402 / DSW-6)", "Zunongwangia profunda (strain DSM 18752 / CCTCC AB 206139 / SM-A87)", "Flavobacteriaceae bacterium (strain 3519-10)", "Owenweeksia hongkongensis (strain DSM 17368 / CIP 108786 / JCM 12287 / NRRL B-23963 / UST20020801)", "Sulcia muelleri (strain GWSS)", "Sulcia muelleri (strain SMDSEM)", "Sulcia muelleri (strain DMIN)", "Sulcia muelleri (strain CARI)", "Fluviicola taffensis (strain DSM 16823 / NCIMB 13979 / RW262)", "Pedobacter heparinus (strain ATCC 13125 / DSM 2366 / CIP 104194 / JCM 7457 / NBRC 12017 / NCIMB 9290 / NRRL B-14731 / HIM 762-3)", "Sphingobacterium sp. (strain 21)", "Solitalea canadensis (strain ATCC 29591 / DSM 3403 / NBRC 15130 / NCIMB 12057 / USAM 9D)", "Pseudopedobacter saltans (strain ATCC 51119 / DSM 12145 / JCM 21818 / LMG 10337 / NBRC 100064 / NCIMB 13643)", "Bacteroides fragilis (strain ATCC 25285 / DSM 2151 / JCM 11019 / NCTC 9343)", "Bacteroides fragilis (strain YCH46)", "Bacteroides fragilis (strain 638R)", "Bacteroides thetaiotaomicron (strain ATCC 29148 / DSM 2079 / NCTC 10582 / E50 / VPI-5482)", "Bacteroides stercoris", "Bacteroides helcogenes (strain ATCC 35417 / DSM 20613 / JCM 6297 / P 36-108)", "Bacteroides salanitronis (strain DSM 18170 / JCM 13567 / BL78)", "Bacteroides vulgatus (strain ATCC 8482 / DSM 1447 / JCM 5826 / NBRC 14291 / NCTC 11154)", "Alistipes finegoldii (strain DSM 17242 / JCM 16770 / AHN 2437 / CCUG 46020 / CIP 107999)", "Porphyromonas gingivalis (strain ATCC BAA-308 / W83)", "Porphyromonas gingivalis (strain ATCC 33277 / DSM 20709 / CIP 103683 / JCM 12257 / NCTC 11834 / 2561)", "Porphyromonas asaccharolytica (strain ATCC 25260 / DSM 20707 / BCRC 10618 / JCM 6326 / LMG 13178 / VPI 4198)", "Porphyromonas endodontalis (strain ATCC 35406 / BCRC 14492 / JCM 8526 / NCTC 13058 / HG 370)", "Porphyromonas cangingivalis", "Prevotella denticola (strain F0289)", "Prevotella intermedia (strain 17)", "Prevotella melaninogenica (strain ATCC 25845 / DSM 7089 / JCM 6325 / VPI 2381 / B282)", "Prevotella dentalis (strain ATCC 49559 / DSM 3688 / JCM 13448 / NCTC 12043 / ES 2772)", "Prevotella ruminicola (strain ATCC 19189 / JCM 8958 / 23)", "Azobacteroides pseudotrichonymphae genomovar. CFP2", "Odoribacter splanchnicus (strain ATCC 29572 / DSM 20712 / CIP 104287 / JCM 15291 / NCTC 10825 / 1651/6)", "Paludibacter propionicigenes (strain DSM 17365 / JCM 13257 / WB4)", "Tannerella forsythia (strain ATCC 43037 / JCM 10827 / FDC 338)", "Parabacteroides distasonis (strain ATCC 8503 / DSM 20701 / CIP 104284 / JCM 5825 / NCTC 11152)", "Runella slithyformis (strain ATCC 29530 / DSM 19594 / LMG 11500 / NCIMB 11436 / LSU 4)", "Cytophaga hutchinsonii (strain ATCC 33406 / NCIMB 9469)", "Dyadobacter fermentans (strain ATCC 700827 / DSM 18053 / NS114)", "Emticicia oligotrophica (strain DSM 17448 / GPTSA100-15)", "Leadbetterella byssophila (strain DSM 17132 / KACC 11308 / 4M15)", "Spirosoma linguale (strain ATCC 33905 / DSM 74 / LMG 10896)", "Cyclobacterium marinum (strain ATCC 25205 / DSM 745)", "Belliella baltica (strain DSM 15883 / CIP 108006 / LMG 21964 / BA134)", "Echinicola vietnamensis (strain DSM 17526 / LMG 23754 / KMM 6221)", "Marivirga tractuosa (strain ATCC 23168 / DSM 4126 / NBRC 15989 / NCIMB 1408 / VKM B-1430 / H-43)", "Amoebophilus asiaticus (strain 5a2)", "Bernardetia litoralis (strain ATCC 23117 / DSM 6794 / NBRC 15988 / NCIMB 1366 / Sio-4)", "Rhodothermus marinus (strain ATCC 43812 / DSM 4252 / R-10)", "Salinibacter ruber (strain DSM 13855 / M31)", "Salinibacter ruber (strain M8)", "Chitinophaga pinensis (strain ATCC 43595 / DSM 2588 / NCIB 11800 / UQM 2034)", "Niastella koreensis (strain DSM 17620 / KACC 11465 / GR20-10)", "Saprospira grandis (strain Lewin)", "Haliscomenobacter hydrossis (strain ATCC 27775 / DSM 1100 / LMG 10767 / O)", "Chlorobium limicola (strain DSM 245 / NBRC 103803 / 6330)", "Chlorobium phaeobacteroides (strain DSM 266)", "Chlorobium phaeobacteroides (strain BS1)", "Chlorobium phaeovibrioides (strain DSM 265 / 1930)", "Chlorobium chlorochromatii (strain CaD3)", "Pelodictyon luteolum (strain DSM 273 / 2530)", "Pelodictyon phaeoclathratiforme (strain DSM 5477 / BU-1)", "Chloroherpeton thalassium (strain ATCC 35110 / GB-78)", "Chlorobaculum tepidum (strain ATCC 49652 / DSM 12025 / NBRC 103806 / TLS)", "Chlorobaculum parvum (strain NCIB 8327)", "Prosthecochloris aestuarii (strain DSM 271 / SK 413)", "Anabaena cylindrica (strain ATCC 27899 / PCC 7122)", "Nostoc sp. (strain ATCC 29411 / PCC 7524)", "Nostoc sp. (strain PCC 7120 / SAG 25.82 / UTEX 2576)", "Nostoc punctiforme (strain ATCC 29133 / PCC 73102)", "Trichormus variabilis (strain ATCC 29413 / PCC 7937)", "Nostoc azollae (strain 0708)", "Stanieria cyanosphaera (strain ATCC 29371 / PCC 7437)", "Gloeobacter violaceus (strain ATCC 29082 / PCC 7421)", "Microcystis aeruginosa (strain NIES-843)", "Gloeothece verrucosa (strain PCC 7822)", "Gloeothece citriformis (strain PCC 7424)", "Halothece sp. (strain PCC 7418)", "Crocosphaera subtropica (strain ATCC 51142 / BH68)", "Atelocyanobacterium thalassa (isolate ALOHA)", "Rippkaea orientalis (strain PCC 8801)", "Rippkaea orientalis (strain PCC 8802)", "Cyanobacterium stanieri (strain ATCC 29140 / PCC 7202)", "Cyanobacterium aponinum (strain PCC 10605)", "Lyngbya sp. (strain PCC 8106)", "Cyanothece sp. (strain PCC 7425 / ATCC 29141)", "Arthrospira platensis (strain NIES-39 / IAM M-135)", "Trichodesmium erythraeum (strain IMS101)", "Prochlorococcus marinus subsp. pastoris (strain CCMP1986 / NIES-2087 / MED4)", "Prochlorococcus marinus (strain NATL2A)", "Prochlorococcus marinus (strain MIT 9303)", "Prochlorococcus marinus (strain MIT 9312)", "Prochlorococcus marinus (strain MIT 9313)", "Prochlorococcus marinus (strain MIT 9211)", "Prochlorococcus marinus (strain MIT 9215)", "Prochlorococcus marinus (strain SARG / CCMP1375 / SS120)", "Prochlorococcus marinus (strain AS9601)", "Prochlorococcus marinus (strain MIT 9515)", "Prochlorococcus marinus (strain MIT 9301)", "Prochlorococcus marinus (strain NATL1A)", "Synechococcus elongatus (strain PCC 7942)", "Synechococcus sp. (strain ATCC 27144 / PCC 6301 / SAUG 1402/1)", "Synechococcus sp. (strain ATCC 27264 / PCC 7002 / PR-6)", "Synechococcus sp. (strain WH7803)", "Synechococcus sp. (strain CC9311)", "Synechococcus sp. (strain WH8102)", "Synechococcus sp. (strain ATCC 29403 / PCC 7335)", "Synechococcus sp. (strain CC9605)", "Synechococcus sp. (strain ATCC 27167 / PCC 6312)", "Synechococcus sp. (strain RCC307)", "Synechococcus sp. (strain CC9902)", "Synechococcus sp. (strain JA-3-3Ab)", "Synechococcus sp. (strain JA-2-3a(2-13))", "Cyanobium gracile (strain ATCC 27147 / PCC 6307)", "Thermosynechococcus elongatus (strain BP-1)", "Synechocystis sp. (strain PCC 6803 / Kazusa)", "Acaryochloris marina (strain MBIC 11017)", "Chamaesiphon minutus (strain ATCC 27169 / PCC 6605)", "Chroococcidiopsis thermalis (strain PCC 7203)", "Francisella tularensis subsp. novicida (strain U112)", "Francisella cf. novicida (strain 3523)", "Francisella cf. novicida (strain Fx1)", "Francisella tularensis subsp. tularensis (strain SCHU S4 / Schu 4)", "Francisella tularensis subsp. tularensis (strain FSC 198)", "Francisella tularensis subsp. tularensis (strain WY96-3418)", "Francisella tularensis subsp. tularensis (strain NE061598)", "Francisella tularensis subsp. holarctica (strain LVS)", "Francisella tularensis subsp. holarctica (strain OSU18)", "Francisella tularensis subsp. holarctica (strain FTNF002-00 / FTA)", "Francisella tularensis subsp. mediasiatica (strain FSC147)", "Francisella philomiragia subsp. philomiragia (strain ATCC 25017)", "Francisella noatunensis subsp. orientalis (strain Toba 04)", "Hydrogenovibrio marinus", "Hydrogenovibrio crunogenus (strain XCL-2)", "Cycloclasticus sp. (strain P1)", "Methylophaga nitratireducenticrescens", "Methylophaga frappieri (strain ATCC BAA-2434 / DSM 25690 / JAM7)", "Thiomicrospira cyclica (strain DSM 14477 / JCM 11371 / ALM1)", "Acinetobacter baylyi (strain ATCC 33305 / BD413 / ADP1)", "Acinetobacter oleivorans (strain JCM 16667 / KCTC 23045 / DR1)", "Acinetobacter baumannii (strain ATCC 17978 / CIP 53.77 / LMG 1025 / NCDC KC755 / 5377)", "Acinetobacter baumannii (strain ACICU)", "Acinetobacter baumannii (strain AB0057)", "Acinetobacter baumannii (strain SDF)", "Acinetobacter baumannii (strain AYE)", "Acinetobacter baumannii (strain AB307-0294)", "Acinetobacter baumannii (strain 1656-2)", "Acinetobacter baumannii (strain TCDC-AB0715)", "Acinetobacter calcoaceticus (strain PHEA-2)", "Moraxella nonliquefaciens", "Moraxella catarrhalis (strain RH4)", "Psychrobacter cryohalolentis (strain K5)", "Psychrobacter arcticus (strain DSM 17307 / 273-4)", "Psychrobacter sp. (strain PRwf-1)", "Pseudomonas aeruginosa (strain UCBPP-PA14)", "Pseudomonas aeruginosa (strain ATCC 15692 / DSM 22644 / CIP 104116 / JCM 14847 / LMG 12228 / 1C / PRS 101 / PAO1)", "Pseudomonas aeruginosa (strain PA7)", "Pseudomonas aeruginosa (strain LESB58)", "Pseudomonas fluorescens (strain Pf0-1)", "Pseudomonas fluorescens (strain SBW25)", "Pseudomonas mendocina (strain ymp)", "Pseudomonas mendocina (strain NK-01)", "Pseudomonas putida (strain GB-1)", "Pseudomonas putida (strain ATCC 47054 / DSM 6125 / NCIMB 11950 / KT2440)", "Pseudomonas putida (strain ATCC 700007 / DSM 6899 / BCRC 17059 / F1)", "Pseudomonas putida (strain W619)", "Pseudomonas putida (strain BIRD-1)", "Pseudomonas stutzeri (strain ATCC 17588 / DSM 5190 / CCUG 11256 / JCM 5965 / LMG 11199 / NCIMB 11358 / Stanier 221)", "Pseudomonas stutzeri (strain A1501)", "Pseudomonas syringae pv. syringae (strain B728a)", "Pseudomonas savastanoi pv. phaseolicola (strain 1448A / Race 6)", "Pseudomonas agarici", "Pseudomonas fulva (strain 12-X)", "Pseudomonas knackmussii (strain DSM 6978 / LMG 23759 / B13)", "Pseudomonas brassicacearum (strain NFM421)", "Pseudomonas syringae pv. tomato (strain ATCC BAA-871 / DC3000)", "Pseudomonas entomophila (strain L48)", "Pseudomonas fluorescens (strain ATCC BAA-477 / NRRL B-23932 / Pf-5)", "Azotobacter vinelandii (strain DJ / ATCC BAA-1303)", "Citrobacter koseri (strain ATCC BAA-895 / CDC 4225-83 / SGSC4696)", "Citrobacter rodentium (strain ICC168)", "Enterobacter asburiae (strain LF7a)", "Enterobacter cloacae subsp. cloacae (strain ATCC 13047 / DSM 30054 / NBRC 13535 / NCDC 279-56)", "Enterobacter sp. (strain 638)", "Escherichia coli (strain B / REL606)", "Escherichia coli (strain K12 / DH10B)", "Escherichia coli str. K-12 substr. MG1655", "Escherichia coli (strain K12 / MC4100 / BW2952)", "Escherichia coli O157:H7 str. EDL933", "Escherichia coli O157:H7 (strain EC4115 / EHEC)", "Escherichia coli O157:H7 (strain TW14359 / EHEC)", "Escherichia coli O127:H6 (strain E2348/69 / EPEC)", "Escherichia coli O111:H- (strain 11128 / EHEC)", "Escherichia coli O6:H1 (strain CFT073 / ATCC 700928 / UPEC)", "Escherichia coli O26:H11 (strain 11368 / EHEC)", "Escherichia coli O55:H7 (strain CB9615 / EPEC)", "Escherichia coli O78:H11 (strain H10407 / ETEC)", "Escherichia coli O9:H4 (strain HS)", "Escherichia coli O6:K15:H31 (strain 536 / UPEC)", "Escherichia coli (strain UTI89 / UPEC)", "Escherichia coli O103:H2 (strain 12009 / EHEC)", "Escherichia coli O1:K1 / APEC", "Escherichia coli (strain SE11)", "Escherichia coli O150:H5 (strain SE15)", "Escherichia coli (strain SMS-3-5 / SECEC)", "Escherichia coli (strain B / BL21-DE3)", "Escherichia coli (strain ATCC 8739 / DSM 1576 / Crooks)", "Escherichia coli (strain B / BL21)", "Escherichia coli (strain ATCC 33849 / DSM 4235 / NCIB 12045 / K12 / DH1)", "Escherichia coli (strain ATCC 9637 / CCM 2024 / DSM 1116 / NCIMB 8666 / NRRL B-766 / W)", "Escherichia coli O8 (strain IAI1)", "Escherichia coli O45:K1 (strain S88 / ExPEC)", "Escherichia coli (strain 55989 / EAEC)", "Escherichia coli O17:K52:H18 (strain UMN026 / ExPEC)", "Escherichia coli O7:K1 (strain IAI39 / ExPEC)", "Escherichia coli O81 (strain ED1a)", "Escherichia coli (strain ATCC 55124 / KO11FL)", "Escherichia coli OR:K5:H- (strain ABU 83972)", "Escherichia coli O83:H1 (strain NRG 857C / AIEC)", "Escherichia coli O18:K1:H7 (strain IHE3034 / ExPEC)", "Escherichia coli O44:H18 (strain 042 / EAEC)", "Escherichia coli (strain UM146)", "Escherichia coli (strain clone D i14)", "Escherichia coli (strain lonei2)", "Escherichia coli O104:H4 (strain 2009EL-2071)", "Escherichia coli O104:H4 str. LB226692", "Escherichia coli O139:H28 (strain E24377A / ETEC)", "Escherichia fergusonii (strain ATCC 35469 / DSM 13698 / CDC 0568-73)", "Klebsiella aerogenes (strain ATCC 13048 / DSM 30053 / JCM 1235 / KCTC 2190 / NBRC 13534 / NCIMB 10102 / NCTC 10006)", "Klebsiella pneumoniae subsp. pneumoniae (strain ATCC 700721 / MGH 78578)", "Klebsiella pneumoniae subsp. pneumoniae (strain HS11286)", "Klebsiella pneumoniae (strain 342)", "Klebsiella variicola (strain At-22)", "Klebsiella oxytoca (strain ATCC 8724 / DSM 4798 / JCM 20051 / NBRC 3318 / NRRL B-199 / KCTC 1686)", "Salmonella arizonae (strain ATCC BAA-731 / CDC346-86 / RSK2980)", "Salmonella gallinarum (strain 287/91 / NCTC 13346)", "Salmonella pullorum (strain RKS5078 / SGSC2294)", "Salmonella heidelberg (strain SL476)", "Salmonella paratyphi A (strain ATCC 9150 / SARB42)", "Salmonella paratyphi A (strain AKU_12601)", "Salmonella paratyphi B (strain ATCC BAA-1250 / SPB7)", "Salmonella paratyphi C (strain RKS4594)", "Salmonella agona (strain SL483)", "Salmonella typhi", "Salmonella typhimurium (strain 14028s / SGSC 2262)", "Salmonella typhimurium (strain LT2 / SGSC1412 / ATCC 700720)", "Salmonella typhimurium (strain SL1344)", "Salmonella typhimurium (strain D23580)", "Salmonella typhimurium (strain 4/74)", "Salmonella dublin (strain CT_02021853)", "Salmonella newport (strain SL254)", "Salmonella choleraesuis (strain SC-B67)", "Salmonella enteritidis PT4 (strain P125109)", "Salmonella schwarzengrund (strain CVM19633)", "Salmonella bongori (strain ATCC 43975 / DSM 13772 / NCTC 12419)", "Shigella boydii serotype 4 (strain Sb227)", "Shigella boydii serotype 18 (strain CDC 3083-94 / BS512)", "Shigella dysenteriae serotype 1 (strain Sd197)", "Shigella flexneri serotype 5b (strain 8401)", "Shigella flexneri serotype X (strain 2002017)", "Shigella flexneri", "Shigella sonnei (strain Ss046)", "Blochmannia pennsylvanicus (strain BPEN)", "Blochmannia floridanus", "Blochmannia vafer (strain BVAF)", "Hamiltonella defensa subsp. Acyrthosiphon pisum (strain 5AT)", "Enterobacteriaceae bacterium (strain FGI 57)", "Riesia pediculicola (strain USDA)", "Cronobacter sakazakii (strain ATCC BAA-894)", "Cronobacter turicensis (strain DSM 18703 / LMG 23827 / z3032)", "Moranella endobia (strain PCIT)", "Enterobacter lignolyticus (strain SCF1)", "Shimwellia blattae (strain ATCC 29907 / DSM 4481 / JCM 1650 / NBRC 105725 / CDC 9005-74)", "Erwinia amylovora (strain CFBP1430)", "Erwinia amylovora (strain ATCC 49946 / CCPPB 0273 / Ea273 / 27-3)", "Erwinia pyrifoliae (strain Ep1/96)", "Erwinia pyrifoliae (strain DSM 12163 / CIP 106111 / Ep16/96)", "Erwinia billingiae (strain Eb661)", "Erwinia sp. (strain Ejp617)", "Erwinia tasmaniensis (strain DSM 17950 / CIP 109463 / Et1/99)", "Buchnera aphidicola subsp. Schizaphis graminum (strain Sg)", "Buchnera aphidicola subsp. Acyrthosiphon pisum (strain 5A)", "Buchnera aphidicola subsp. Acyrthosiphon pisum (strain APS)", "Buchnera aphidicola subsp. Acyrthosiphon pisum (strain Tuc7)", "Buchnera aphidicola subsp. Acyrthosiphon pisum (strain JF98)", "Buchnera aphidicola subsp. Acyrthosiphon pisum (strain JF99)", "Buchnera aphidicola subsp. Acyrthosiphon pisum (strain LL01)", "Buchnera aphidicola subsp. Schlechtendalia chinensis", "Buchnera aphidicola subsp. Baizongia pistaciae (strain Bp)", "Buchnera aphidicola subsp. Cinara cedri (strain Cc)", "Wigglesworthia glossinidia brevipalpis", "Pantoea ananatis (strain LMG 20103)", "Pantoea ananatis (strain AJ13355)", "Pantoea sp. (strain At-9b)", "Pantoea vagans (strain C9-1)", "Pectobacterium carotovorum subsp. carotovorum (strain PC1)", "Pectobacterium atrosepticum (strain SCRI 1043 / ATCC BAA-672)", "Pectobacterium parmentieri (strain WPP163)", "Pectobacterium parmentieri", "Dickeya chrysanthemi (strain Ech1591)", "Dickeya paradisiaca (strain Ech703)", "Dickeya dadantii (strain 3937)", "Dickeya zeae (strain Ech586)", "Sodalis glossinidius (strain morsitans)", "Serratia fonticola", "Serratia plymuthica (strain AS9)", "Serratia proteamaculans (strain 568)", "Yersinia enterocolitica serotype O:8 / biotype 1B (strain NCTC 13174 / 8081)", "Yersinia enterocolitica subsp. palearctica serotype O:3 (strain DSM 13030 / CIP 106945 / Y11)", "Yersinia enterocolitica subsp. palearctica serotype O:9 / biotype 3 (strain 105.5R(r))", "Yersinia ruckeri", "Yersinia pestis CO92", "Yersinia pestis bv. Antiqua (strain Angola)", "Yersinia pestis bv. Antiqua (strain Antiqua)", "Yersinia pestis bv. Antiqua (strain Nepal516)", "Yersinia pestis (strain Pestoides F)", "Yersinia pestis bv. Medievalis (strain Harbin 35)", "Yersinia pestis (strain D106004)", "Yersinia pestis (strain D182038)", "Yersinia pestis (strain Z176003)", "Yersinia pseudotuberculosis serotype I (strain IP32953)", "Yersinia pseudotuberculosis serotype O:1b (strain IP 31758)", "Yersinia pseudotuberculosis serotype O:3 (strain YPIII)", "Yersinia pseudotuberculosis serotype IB (strain PB1/+)", "Rahnella aquatilis (strain ATCC 33071 / DSM 4594 / JCM 1683 / NBRC 105701 / NCIMB 13365 / CIP 78.65)", "Rahnella sp. (strain Y9602)", "Edwardsiella tarda (strain EIB202)", "Edwardsiella tarda (strain FL6-60)", "Edwardsiella ictaluri (strain 93-146)", "Proteus mirabilis (strain HI4320)", "Providencia rettgeri (strain Dmel1)", "Providencia stuartii (strain MRSN 2154)", "Xenorhabdus bovienii (strain SS-2004)", "Xenorhabdus nematophila (strain ATCC 19061 / DSM 3370 / LMG 1036 / NCIB 9965 / AN6)", "Photorhabdus laumondii subsp. laumondii (strain DSM 15139 / CIP 105565 / TT01)", "Photorhabdus asymbiotica subsp. asymbiotica (strain ATCC 43949 / 3105-77)", "Vesicomyosocius okutanii subsp. Calyptogena okutanii (strain HA)", "Ruthia magnifica subsp. Calyptogena magnifica", "Baumannia cicadellinicola subsp. Homalodisca coagulata", "Legionella pneumophila serogroup 1 (strain 2300/99 Alcoy)", "Legionella pneumophila subsp. pneumophila (strain Philadelphia 1 / ATCC 33152 / DSM 7513)", "Legionella pneumophila (strain Lens)", "Legionella pneumophila (strain Paris)", "Legionella pneumophila (strain Corby)", "Legionella longbeachae serogroup 1 (strain NSW150)", "Tatlockia micdadei", "Coxiella burnetii (strain RSA 493 / Nine Mile phase I)", "Coxiella burnetii (strain RSA 331 / Henzerling II)", "Coxiella burnetii (strain Dugway 5J108-111)", "Coxiella burnetii (strain CbuG_Q212)", "Coxiella burnetii (strain CbuK_Q154)", "Nitrosococcus oceani (strain ATCC 19707 / BCRC 17464 / NCIMB 11848 / C-107)", "Nitrosococcus watsoni (strain C-113)", "Nitrosococcus halophilus (strain Nc4)", "Allochromatium vinosum (strain ATCC 17899 / DSM 180 / NBRC 103801 / NCIMB 10441 / D)", "Thiocystis violascens (strain ATCC 17096 / DSM 198 / 6111)", "Halorhodospira halophila (strain DSM 244 / SL1)", "Thioalkalivibrio sulfidiphilus (strain HL-EbGR7)", "Thioalkalivibrio sp. (strain K90mix)", "Alkalilimnicola ehrlichii (strain ATCC BAA-1101 / DSM 17681 / MLHE-1)", "Halothiobacillus neapolitanus (strain ATCC 23641 / c2)", "Lysobacter enzymogenes", "Xanthomonas campestris pv. campestris (strain ATCC 33913 / DSM 3586 / NCPPB 528 / LMG 568 / P 25)", "Xanthomonas campestris pv. campestris (strain 8004)", "Xanthomonas campestris pv. campestris (strain B100)", "Xanthomonas axonopodis pv. citri (strain 306)", "Xanthomonas oryzae pv. oryzae (strain KACC10331 / KXO85)", "Xanthomonas oryzae pv. oryzae (strain MAFF 311018)", "Xanthomonas oryzae pv. oryzae (strain PXO99A)", "Xanthomonas albilineans (strain GPE PC73 / CFBP 7063)", "Xanthomonas campestris pv. vesicatoria (strain 85-10)", "Xylella fastidiosa (strain 9a5c)", "Xylella fastidiosa (strain Temecula1 / ATCC 700964)", "Xylella fastidiosa (strain M12)", "Xylella fastidiosa (strain M23)", "Xylella fastidiosa (strain GB514)", "Stenotrophomonas maltophilia (strain R551-3)", "Stenotrophomonas maltophilia (strain K279a)", "Pseudoxanthomonas spadix (strain BD-a59)", "Pseudoxanthomonas suwonensis (strain 11-1)", "Frateuria aurantia (strain ATCC 33424 / DSM 6220 / NBRC 3245 / NCIMB 13370)", "Cardiobacterium hominis (strain ATCC 15826 / DSM 8339 / NCTC 10426 / 6573)", "Dichelobacter nodosus (strain VCS1703A)", "Methylococcus capsulatus (strain ATCC 33009 / NCIMB 11132 / Bath)", "Methylobacter tundripaludum (strain ATCC BAA-1195 / DSM 17260 / SV96)", "Methylomicrobium alcaliphilum (strain DSM 19304 / NCIMB 14124 / VKM B-2133 / 20Z)", "Methylomicrobium alcaliphilum", "Methylomonas methanica (strain MC09)", "Chromohalobacter salexigens (strain DSM 3043 / ATCC BAA-138 / NCIMB 13768)", "Carsonella ruddii (strain PV)", "Halomonas elongata (strain ATCC 33173 / DSM 2581 / NBRC 15536 / NCIMB 2198 / 1H9)", "Marinomonas mediterranea (strain ATCC 700492 / JCM 21426 / NBRC 103028 / MMB-1)", "Marinomonas sp. (strain MWYL1)", "Neptuniibacter caesariensis", "Alcanivorax borkumensis (strain ATCC 700651 / DSM 11573 / NCIMB 13689 / SK2)", "Alcanivorax dieselolei (strain DSM 16502 / CGMCC 1.3690 / B-5)", "Hahella chejuensis (strain KCTC 2396)", "Kangiella koreensis (strain DSM 16069 / KCTC 12182 / SW-125)", "Alteromonas macleodii (strain Black Sea 11)", "Alteromonas macleodii (strain Balearic Sea AD45)", "Alteromonas macleodii (strain English Channel 673)", "Alteromonas mediterranea (strain DSM 17117 / CIP 110805 / LMG 28347 / Deep ecotype)", "Alteromonas naphthalenivorans", "Marinobacter hydrocarbonoclasticus (strain ATCC 700491 / DSM 11845 / VT8)", "Marinobacter adhaerens (strain DSM 23420 / HP15)", "Pseudoalteromonas haloplanktis (strain TAC 125)", "Pseudoalteromonas atlantica (strain T6c / ATCC BAA-1087)", "Pseudoalteromonas sp. (strain SM9913)", "Colwellia psychrerythraea (strain 34H / ATCC BAA-681)", "Shewanella putrefaciens (strain CN-32 / ATCC BAA-453)", "Shewanella putrefaciens (strain 200)", "Shewanella frigidimarina (strain NCIMB 400)", "Shewanella violacea (strain JCM 10179 / CIP 106290 / LMG 19151 / DSS12)", "Shewanella amazonensis (strain ATCC BAA-1098 / SB2B)", "Shewanella sp. (strain MR-4)", "Shewanella sp. (strain MR-7)", "Shewanella baltica (strain OS155 / ATCC BAA-1091)", "Shewanella baltica (strain OS195)", "Shewanella baltica (strain OS185)", "Shewanella baltica (strain OS223)", "Shewanella baltica (strain OS678)", "Shewanella oneidensis (strain MR-1)", "Shewanella pealeana (strain ATCC 700345 / ANG-SQ1)", "Shewanella sp. (strain ANA-3)", "Shewanella denitrificans (strain OS217 / ATCC BAA-1090 / DSM 15013)", "Shewanella sediminis (strain HAW-EB3)", "Shewanella halifaxensis (strain HAW-EB4)", "Shewanella sp. (strain W3-18-1)", "Shewanella loihica (strain ATCC BAA-1088 / PV-4)", "Shewanella woodyi (strain ATCC 51908 / MS32)", "Shewanella piezotolerans (strain WP3 / JCM 13877)", "Ferrimonas balearica (strain DSM 9799 / CCM 4581 / PAT)", "Idiomarina loihiensis (strain ATCC BAA-735 / DSM 15497 / L2-TR)", "Psychromonas ingrahamii (strain 37)", "Photobacterium profundum (strain SS9)", "Vibrio cholerae serotype O1 (strain ATCC 39315 / El Tor Inaba N16961)", "Vibrio cholerae serotype O1 (strain MJ-1236)", "Vibrio cholerae serotype O1 (strain ATCC 39541 / Classical Ogawa 395 / O395)", "Vibrio cholerae serotype O1 (strain M66-2)", "Vibrio parahaemolyticus serotype O3:K6 (strain RIMD 2210633)", "Vibrio vulnificus (strain YJ016)", "Vibrio vulnificus (strain CMCP6)", "Vibrio vulnificus (strain MO6-24/O)", "Vibrio campbellii (strain ATCC BAA-1116 / BB120)", "Vibrio nereis", "Vibrio furnissii (strain DSM 14383 / NCTC 11218 / VL 6966)", "Vibrio anguillarum (strain ATCC 68554 / 775)", "Vibrio antiquarius (strain Ex25)", "Vibrio tasmaniensis (strain LGP32)", "Vibrio sp. (strain N418)", "Aliivibrio fischeri (strain ATCC 700601 / ES114)", "Aliivibrio fischeri (strain MJ11)", "Aliivibrio salmonicida (strain LFI1238)", "Aeromonas hydrophila subsp. hydrophila (strain ATCC 7966 / DSM 30187 / JCM 1027 / KCTC 2358 / NCIMB 9240)", "Aeromonas salmonicida (strain A449)", "Aeromonas veronii (strain B565)", "Oceanimonas sp. (strain GK1)", "Tolumonas auensis (strain DSM 9187 / TA4)", "Actinobacillus pleuropneumoniae serotype 5b (strain L20)", "Actinobacillus pleuropneumoniae serotype 3 (strain JL03)", "Actinobacillus pleuropneumoniae serotype 7 (strain AP76)", "Actinobacillus succinogenes (strain ATCC 55618 / DSM 22257 / 130Z)", "Haemophilus influenzae (strain ATCC 51907 / DSM 11121 / KW20 / Rd)", "Haemophilus influenzae (strain R2846 / 12)", "Haemophilus influenzae (strain R2866)", "Haemophilus influenzae (strain 86-028NP)", "Haemophilus influenzae (strain PittEE)", "Haemophilus influenzae (strain PittGG)", "Haemophilus influenzae (strain 10810)", "Haemophilus ducreyi (strain 35000HP / ATCC 700724)", "Haemophilus parainfluenzae (strain T3T1)", "Pasteurella multocida (strain Pm70)", "Pasteurella multocida (strain HN06)", "Gallibacterium anatis (strain UMN179)", "Haemophilus somnus (strain 129Pt)", "Histophilus somni (strain 2336)", "Aggregatibacter actinomycetemcomitans serotype C (strain D11S-1)", "Aggregatibacter aphrophilus (strain NJ8700)", "Mannheimia succiniciproducens (strain MBEL55E)", "Haemophilus parasuis serovar 5 (strain SH0165)", "Cellvibrio japonicus (strain Ueda107)", "Saccharophagus degradans (strain 2-40 / ATCC 43961 / DSM 17024)", "Teredinibacter turnerae (strain ATCC 39867 / T7901)", "Simiduia agarivorans (strain DSM 21679 / JCM 13881 / BCRC 17597 / SA1)", "Bartonella bacilliformis (strain ATCC 35685 / NCTC 12138 / KC583)", "Bartonella quintana (strain Toulouse)", "Bartonella grahamii (strain as4aup)", "Bartonella henselae (strain ATCC 49882 / DSM 28221 / Houston 1)", "Bartonella clarridgeiae (strain CIP 104772 / 73)", "Bartonella tribocorum (strain CIP 105476 / IBS 506)", "Bartonella vinsonii subsp. berkhoffii (strain Winnie)", "Methylocystis sp. (strain SC2)", "Bradyrhizobium sp. (strain ORS 278)", "Bradyrhizobium sp. (strain BTAi1 / ATCC BAA-1182)", "Bradyrhizobium diazoefficiens (strain JCM 10833 / IAM 13628 / NBRC 14792 / USDA 110)", "Nitrobacter hamburgensis (strain DSM 10229 / NCIMB 13809 / X14)", "Nitrobacter winogradskyi (strain ATCC 25391 / DSM 10237 / CIP 104748 / NCIMB 11846 / Nb-255)", "Rhodopseudomonas palustris (strain ATCC BAA-98 / CGA009)", "Rhodopseudomonas palustris (strain BisA53)", "Rhodopseudomonas palustris (strain BisB18)", "Rhodopseudomonas palustris (strain BisB5)", "Rhodopseudomonas palustris (strain HaA2)", "Rhodopseudomonas palustris (strain TIE-1)", "Rhodopseudomonas palustris (strain DX-1)", "Oligotropha carboxidovorans (strain ATCC 49405 / DSM 1227 / KCTC 32145 / OM5)", "Oligotropha carboxidovorans (strain OM4)", "Hyphomicrobium denitrificans (strain ATCC 51888 / DSM 1869 / NCIB 11706 / TK 0415)", "Hyphomicrobium sp. (strain MC1)", "Blastochloris viridis", "Rhodomicrobium vannielii (strain ATCC 17100 / ATH 3.1.1 / DSM 162 / LMG 4299)", "Pelagibacterium halotolerans (strain DSM 22347 / JCM 15775 / CGMCC 1.7692 / B2)", "Beijerinckia indica subsp. indica (strain ATCC 9039 / DSM 1715 / NCIB 8712)", "Methylocella silvestris (strain DSM 15510 / CIP 108128 / LMG 27833 / NCIMB 13906 / BL2)", "Mesorhizobium ciceri biovar biserrulae (strain HAMBI 2942 / LMG 23838 / WSM1271)", "Mesorhizobium japonicum (strain LMG 29417 / CECT 9101 / MAFF 303099)", "Mesorhizobium australicum (strain HAMBI 3006 / LMG 24608 / WSM2073)", "Chelativorans sp. (strain BNC1)", "Agrobacterium vitis (strain S4 / ATCC BAA-846)", "Agrobacterium sp. (strain H13-3)", "Agrobacterium radiobacter (strain K84 / ATCC BAA-868)", "Agrobacterium fabrum (strain C58 / ATCC 33970)", "Rhizobium leguminosarum bv. trifolii (strain WSM1325)", "Rhizobium leguminosarum bv. trifolii (strain WSM2304)", "Rhizobium leguminosarum bv. viciae (strain 3841)", "Rhizobium etli (strain CFN 42 / ATCC 51251)", "Rhizobium etli (strain CIAT 652)", "Sinorhizobium fredii (strain NBRC 101917 / NGR234)", "Rhizobium fredii (strain HH103)", "Rhizobium meliloti (strain 1021)", "Sinorhizobium meliloti (strain AK83)", "Sinorhizobium meliloti (strain BL225C)", "Sinorhizobium meliloti (strain SM11)", "Sinorhizobium medicae (strain WSM419)", "Liberibacter asiaticus (strain psy62)", "Brucella abortus biovar 1 (strain 9-941)", "Brucella abortus (strain 2308)", "Brucella abortus (strain S19)", "Brucella ovis (strain ATCC 25840 / 63/290 / NCTC 10512)", "Brucella melitensis biotype 2 (strain ATCC 23457)", "Brucella melitensis biotype 1 (strain 16M / ATCC 23456 / NCTC 10094)", "Brucella melitensis (strain M5-90)", "Brucella suis biovar 1 (strain 1330)", "Brucella suis (strain ATCC 23445 / NCTC 10510)", "Brucella canis (strain ATCC 23365 / NCTC 10854)", "Brucella microti (strain CCM 4915)", "Ochrobactrum anthropi (strain ATCC 49188 / DSM 6882 / JCM 21032 / NBRC 15819 / NCTC 12168)", "Parvibaculum lavamentivorans (strain DS-1 / DSM 13023 / NCIMB 13966)", "Methylobacterium radiotolerans (strain ATCC 27329 / DSM 1819 / JCM 2831 / NBRC 15690 / NCIMB 10815 / 0-1)", "Methylobacterium nodulans (strain LMG 21967 / CNCM I-2342 / ORS 2060)", "Methylobacterium sp. (strain 4-46)", "Methylorubrum extorquens (strain ATCC 14718 / DSM 1338 / JCM 2805 / NCIMB 9133 / AM1)", "Methylorubrum extorquens (strain PA1)", "Methylorubrum extorquens (strain CM4 / NCIMB 13688)", "Methylorubrum extorquens (strain DSM 6343 / CIP 106787 / DM4)", "Methylorubrum populi (strain ATCC BAA-705 / NCIMB 13946 / BJ001)", "Azorhizobium caulinodans (strain ATCC 43989 / DSM 5975 / JCM 20966 / NBRC 14845 / NCIMB 13405 / ORS 571)", "Xanthobacter autotrophicus (strain ATCC BAA-1158 / Py2)", "Starkeya novella (strain ATCC 8093 / DSM 506 / CCM 1077 / IAM 12100 / NBRC 12443 / NCIB 9113)", "Hodgkinia cicadicola (strain Dsem)", "Rickettsia conorii (strain ATCC VR-613 / Malish 7)", "Rickettsia prowazekii (strain Madrid E)", "Rickettsia prowazekii (strain Rp22)", "Rickettsia rickettsii (strain Sheila Smith)", "Rickettsia rickettsii (strain Iowa)", "Rickettsia akari (strain Hartford)", "Rickettsia australis (strain Cutlack)", "Rickettsia canadensis (strain McKiel)", "Rickettsia amblyommatis (strain GAT-30V)", "Rickettsia bellii (strain RML369-C)", "Rickettsia bellii (strain OSU 85-389)", "Rickettsia montanensis (strain OSU 85-930)", "Rickettsia rhipicephali (strain 3-7-female6-CWPP)", "Rickettsia africae (strain ESF-5)", "Rickettsia japonica (strain ATCC VR-1363 / YH)", "Rickettsia massiliae (strain Mtu5)", "Rickettsia parkeri (strain Portsmouth)", "Rickettsia slovaca (strain 13-B)", "Rickettsia felis (strain ATCC VR-1525 / URRWXCal2)", "Rickettsia peacockii (strain Rustic)", "Rickettsia typhi (strain ATCC VR-144 / Wilmington)", "Rickettsia philipii (strain 364D)", "Orientia tsutsugamushi (strain Ikeda)", "Orientia tsutsugamushi (strain Boryong)", "Anaplasma marginale (strain St. Maries)", "Anaplasma marginale (strain Florida)", "Anaplasma phagocytophilum (strain HZ)", "Ehrlichia ruminantium (strain Welgevonden)", "Ehrlichia ruminantium (strain Gardel)", "Ehrlichia canis (strain Jake)", "Ehrlichia chaffeensis (strain ATCC CRL-10679 / Arkansas)", "Wolbachia pipientis", "Wolbachia sp. subsp. Drosophila simulans (strain wRi)", "Wolbachia sp. subsp. Brugia malayi (strain TRS)", "Wolbachia pipientis wMel", "Wolbachia pipientis subsp. Culex pipiens (strain wPip)", "Neorickettsia risticii (strain Illinois)", "Neorickettsia sennetsu (strain ATCC VR-367 / Miyayama)", "Midichloria mitochondrii (strain IricVA)", "Pelagibacter ubique (strain HTCC1062)", "Pelagibacter sp. (strain IMCC9063)", "Micavibrio aeruginosavorus (strain ARL-13)", "Puniceispirillum marinum (strain IMCC1322)", "Polymorphum gilvum (strain LMG 25793 / CGMCC 1.9160 / SL003B-26A1)", "Acetobacter pasteurianus (strain NBRC 3283 / LMG 1513 / CCTM 1153)", "Gluconobacter oxydans (strain 621H)", "Acidiphilium cryptum (strain JF-5)", "Acidiphilium multivorum (strain DSM 11245 / JCM 8867 / NBRC 100883 / AIU301)", "Gluconacetobacter diazotrophicus (strain ATCC 49037 / DSM 5601 / PAl5)", "Granulibacter bethesdensis (strain ATCC BAA-1260 / CGDNIH1)", "Komagataeibacter medellinensis (strain NBRC 3288 / BCRC 11682 / LMG 1693 / Kondo 51)", "Azospirillum lipoferum (strain 4B)", "Rhodospirillum centenum (strain ATCC 51521 / SW)", "Rhodospirillum rubrum (strain ATCC 11170 / ATH 1.1.1 / DSM 467 / LMG 4362 / NCIB 8255 / S1)", "Magnetospirillum magneticum (strain AMB-1 / ATCC 700264)", "Tistrella mobilis (strain KA081020-065)", "Paracoccus denitrificans (strain Pd 1222)", "Rhodobacter capsulatus (strain ATCC BAA-309 / NBRC 16581 / SB1003)", "Rhodobacter sphaeroides (strain ATCC 17023 / 2.4.1 / NCIB 8253 / DSM 158)", "Rhodobacter sphaeroides (strain ATCC 17029 / ATH 2.4.9)", "Rhodobacter sphaeroides (strain ATCC 17025 / ATH 2.4.3)", "Rhodobacter sphaeroides (strain KD131 / KCTC 12085)", "Roseobacter denitrificans (strain ATCC 33942 / OCh 114)", "Roseobacter litoralis (strain ATCC 49566 / DSM 6996 / JCM 21268 / NBRC 15278 / OCh 149)", "Ketogulonicigenium vulgare (strain WSH-001)", "Ketogulonicigenium vulgare (strain Y25)", "Ruegeria pomeroyi (strain ATCC 700808 / DSM 15171 / DSS-3)", "Ruegeria sp. (strain TM1040)", "Jannaschia sp. (strain CCS1)", "Oceanicola granulosus (strain ATCC BAA-861 / DSM 15982 / KCTC 12143 / HTCC2516)", "Pseudovibrio sp. (strain FO-BEG1)", "Phaeobacter inhibens (strain ATCC 700781 / DSM 17395 / CIP 105210 / JCM 21319 / NBRC 16654 / NCIMB 13546 / BS107)", "Dinoroseobacter shibae (strain DSM 16493 / NCIMB 14021 / DFL 12)", "Hyphomonas neptunium (strain ATCC 15444)", "Hirschia baltica (strain ATCC 49814 / DSM 5838 / IFAM 1418)", "Maricaulis maris (strain MCS10)", "Zymomonas mobilis subsp. mobilis (strain ATCC 31821 / ZM4 / CP4)", "Zymomonas mobilis subsp. mobilis (strain ATCC 10988 / DSM 424 / LMG 404 / NCIMB 8938 / NRRL B-806 / ZM1)", "Zymomonas mobilis subsp. mobilis (strain NCIMB 11163 / B70)", "Zymomonas mobilis subsp. pomaceae (strain ATCC 29192 / JCM 10191 / NBRC 13757 / NCIMB 11200 / NRRL B-4491)", "Sphingomonas wittichii (strain RW1 / DSM 6014 / JCM 10273)", "Sphingobium japonicum (strain DSM 16413 / CCM 7287 / MTCC 6362 / UT26 / NBRC 101211 / UT26S)", "Novosphingobium aromaticivorans (strain ATCC 700278 / DSM 12444 / CIP 105152 / NBRC 16084 / F199)", "Sphingopyxis alaskensis (strain DSM 13593 / LMG 18877 / RB2256)", "Erythrobacter litoralis (strain HTCC2594)", "Caulobacter segnis (strain ATCC 21756 / DSM 7131 / JCM 7823 / NBRC 15250 / LMG 17158 / TK0059)", "Caulobacter vibrioides (strain NA1000 / CB15N)", "Caulobacter vibrioides (strain ATCC 19089 / CB15)", "Caulobacter sp. (strain K31)", "Brevundimonas subvibrioides (strain ATCC 15264 / DSM 4735 / LMG 14903 / NBRC 16000 / CB 81)", "Asticcacaulis excentricus (strain ATCC 15261 / DSM 4724 / VKM B-1370 / CB 48)", "Phenylobacterium zucineum (strain HLK1)", "Parvularcula bermudensis (strain ATCC BAA-594 / HTCC2503 / KCTC 12087)", "Magnetococcus marinus (strain ATCC BAA-1437 / JCM 17883 / MC-1)", "Methylobacillus flagellatus (strain KT / ATCC 51484 / DSM 6875)", "Methylovorus glucosetrophus (strain SIP3-4)", "Methylovorus sp. (strain MP688)", "Methylotenera mobilis (strain JLW8 / ATCC BAA-1282 / DSM 17540)", "Gallionella capsiferriformans (strain ES-2)", "Sideroxydans lithotrophicus (strain ES-1)", "Nitrosomonas europaea (strain ATCC 19718 / CIP 103999 / KCTC 2705 / NBRC 14298)", "Nitrosomonas eutropha (strain DSM 101675 / C91)", "Nitrosomonas sp. (strain Is79A3)", "Nitrosospira multiformis (strain ATCC 25196 / NCIMB 11849 / C 71)", "Thiobacillus denitrificans (strain ATCC 25259)", "Achromobacter xylosoxidans (strain A8)", "Bordetella bronchiseptica (strain ATCC BAA-588 / NCTC 13252 / RB50)", "Bordetella bronchiseptica (strain MO149)", "Bordetella parapertussis (strain 12822 / ATCC BAA-587 / NCTC 13253)", "Bordetella pertussis (strain Tohama I / ATCC BAA-589 / NCTC 13251)", "Bordetella pertussis (strain ATCC 9797 / DSM 5571 / NCTC 10739 / 18323)", "Bordetella pertussis (strain CS)", "Bordetella avium (strain 197N)", "Bordetella petrii (strain ATCC BAA-461 / DSM 12804 / CCUG 43448)", "Advenella kashmirensis (strain DSM 17095 / LMG 22695 / WT001)", "Pusillimonas sp. (strain T7-7)", "Taylorella equigenitalis (strain MCE9)", "Herbaspirillum seropedicae (strain SmR1)", "Collimonas fungivorans (strain Ter331)", "Herminiimonas arsenicoxydans", "Janthinobacterium sp. (strain Marseille)", "Zinderia insecticola (strain CARI)", "Comamonas testosteroni (strain CNB-2)", "Acidovorax avenae (strain ATCC 19860 / DSM 7227 / JCM 20985 / NCPPB 1011)", "Acidovorax citrulli (strain AAC00-1)", "Acidovorax sp. (strain JS42)", "Acidovorax ebreus (strain TPSY)", "Rhodoferax ferrireducens (strain ATCC BAA-621 / DSM 15236 / T118)", "Variovorax paradoxus (strain S110)", "Variovorax paradoxus (strain EPS)", "Polaromonas naphthalenivorans (strain CJ2)", "Polaromonas sp. (strain JS666 / ATCC BAA-500)", "Delftia acidovorans (strain DSM 14801 / SPH-1)", "Delftia sp. (strain Cs1-4)", "Ramlibacter tataouinensis (strain ATCC BAA-407 / DSM 14655 / LMG 21543 / TTB310)", "Alicycliphilus denitrificans (strain DSM 14773 / CIP 107495 / K601)", "Verminephrobacter eiseniae (strain EF01-2)", "Burkholderia glumae (strain BGR1)", "Burkholderia mallei (strain ATCC 23344)", "Burkholderia mallei (strain SAVP1)", "Burkholderia mallei (strain NCTC 10247)", "Burkholderia mallei (strain NCTC 10229)", "Burkholderia gladioli (strain BSR3)", "Burkholderia pseudomallei (strain K96243)", "Burkholderia pseudomallei (strain 1710b)", "Burkholderia pseudomallei (strain 668)", "Burkholderia pseudomallei (strain 1106a)", "Burkholderia multivorans (strain ATCC 17616 / 249)", "Burkholderia cenocepacia (strain ATCC BAA-245 / DSM 16553 / LMG 16656 / NCTC 13227 / J2315 / CF5610)", "Burkholderia cenocepacia (strain AU 1054)", "Burkholderia cenocepacia (strain HI2424)", "Burkholderia cenocepacia (strain MC0-3)", "Burkholderia ambifaria (strain ATCC BAA-244 / AMMD)", "Burkholderia ambifaria (strain MC40-6)", "Burkholderia vietnamiensis (strain G4 / LMG 22486)", "Burkholderia lata (strain ATCC 17760 / DSM 23089 / LMG 22485 / NCIMB 9086 / R18194 / 383)", "Burkholderia thailandensis (strain ATCC 700388 / DSM 13276 / CIP 106301 / E264)", "Burkholderia sp. (strain CCGE1003)", "Polynucleobacter necessarius subsp. necessarius (strain STIR1)", "Polynucleobacter asymbioticus (strain DSM 18221 / CIP 109841 / QLW-P1DMWA-1)", "Ralstonia solanacearum (strain GMI1000)", "Ralstonia solanacearum (strain Po82)", "Ralstonia solanacearum", "Ralstonia pickettii (strain 12J)", "Ralstonia pickettii (strain 12D)", "Cupriavidus necator (strain ATCC 17699 / H16 / DSM 428 / Stanier 337)", "Cupriavidus necator (strain ATCC 43291 / DSM 13513 / N-1)", "Cupriavidus metallidurans (strain ATCC 43123 / DSM 2839 / NBRC 102507 / CH34)", "Cupriavidus pinatubonensis (strain JMP 134 / LMG 1197)", "Cupriavidus taiwanensis (strain DSM 17343 / BCRC 17206 / CIP 107171 / LMG 19424 / R1)", "Paraburkholderia phymatum (strain DSM 17167 / CIP 108236 / LMG 21445 / STM815)", "Paraburkholderia phytofirmans (strain DSM 17436 / LMG 22146 / PsJN)", "Paraburkholderia xenovorans (strain LB400)", "Burkholderia sp. (strain CCGE1002)", "Paraburkholderia rhizoxinica (strain DSM 19002 / CIP 109453 / HKI 454)", "Leptothrix cholodnii (strain ATCC 51168 / LMG 8142 / SP-6)", "Rubrivivax gelatinosus (strain NBRC 100245 / IL144)", "Thiomonas intermedia (strain K12)", "Methylibium petroleiphilum (strain ATCC BAA-1232 / LMG 22953 / PM1)", "Accumulibacter phosphatis (strain UW-1)", "Tremblaya princeps (strain PCIT)", "Neisseria gonorrhoeae (strain ATCC 700825 / FA 1090)", "Neisseria gonorrhoeae (strain NCCP11945)", "Neisseria meningitidis serogroup B (strain MC58)", "Neisseria meningitidis serogroup B (strain alpha710)", "Neisseria meningitidis serogroup B / serotype 15 (strain H44/76)", "Neisseria meningitidis serogroup A / serotype 4A (strain Z2491)", "Neisseria meningitidis serogroup C / serotype 2a (strain ATCC 700532 / DSM 15464 / FAM18)", "Neisseria meningitidis serogroup C (strain 053442)", "Neisseria meningitidis serogroup C (strain 8013)", "Neisseria meningitidis (strain alpha14)", "Neisseria meningitidis serogroup B (strain M01-240355)", "Neisseria meningitidis serogroup B (strain NZ-05/33)", "Neisseria meningitidis serogroup B (strain M01-240149)", "Neisseria meningitidis serogroup B (strain M04-240196)", "Neisseria meningitidis serogroup B (strain G2136)", "Neisseria meningitidis serogroup A (strain WUE 2594)", "Chromobacterium violaceum (strain ATCC 12472 / DSM 30191 / JCM 1249 / NBRC 12614 / NCIMB 9131 / NCTC 9757)", "Laribacter hongkongensis (strain HLHK9)", "Pseudogulbenkiania sp. (strain NH8B)", "Aromatoleum aromaticum (strain EbN1)", "Azospira oryzae (strain ATCC BAA-33 / DSM 13638 / PS)", "Azoarcus sp. (strain BH72)", "Thauera sp. (strain MZ1T)", "Dechloromonas aromatica (strain RCB)", "Myxococcus fulvus (strain ATCC BAA-855 / HW-1)", "Myxococcus stipitatus (strain DSM 14675 / JCM 12634 / Mx s8)", "Myxococcus xanthus (strain DK 1622)", "Corallococcus coralloides (strain ATCC 25202 / DSM 2259 / NBRC 100086 / M2)", "Stigmatella aurantiaca (strain DW4/3-1)", "Anaeromyxobacter dehalogenans (strain 2CP-C)", "Anaeromyxobacter dehalogenans (strain 2CP-1 / ATCC BAA-258)", "Anaeromyxobacter sp. (strain Fw109-5)", "Anaeromyxobacter sp. (strain K)", "Haliangium ochraceum (strain DSM 14365 / JCM 11303 / SMP-2)", "Sorangium cellulosum (strain So ce56)", "Pelobacter carbinolicus (strain DSM 2380 / NBRC 103641 / GraBd1)", "Pelobacter propionicus (strain DSM 2379 / NBRC 103807 / OttBd1)", "Geobacter metallireducens (strain GS-15 / ATCC 53774 / DSM 7210)", "Geobacter sulfurreducens (strain ATCC 51573 / DSM 12127 / PCA)", "Geobacter sulfurreducens (strain DL-1 / KN400)", "Geobacter bemidjiensis (strain Bem / ATCC BAA-1014 / DSM 16622)", "Geobacter lovleyi (strain ATCC BAA-1151 / DSM 17278 / SZ)", "Geobacter uraniireducens (strain Rf4)", "Geobacter sp. (strain M18)", "Geobacter sp. (strain M21)", "Geobacter daltonii (strain DSM 22248 / JCM 15807 / FRC-32)", "Hippea maritima (strain ATCC 700847 / DSM 10411 / MH2)", "Desulfovibrio desulfuricans (strain ATCC 27774 / DSM 6949)", "Desulfovibrio salexigens (strain ATCC 14822 / DSM 2638 / NCIB 8403 / VKM B-1763)", "Desulfovibrio vulgaris (strain Hildenborough / ATCC 29579 / DSM 644 / NCIMB 8303)", "Desulfovibrio vulgaris (strain Miyazaki F / DSM 19637)", "Desulfovibrio vulgaris subsp. vulgaris (strain DP4)", "Desulfovibrio vulgaris (strain RCH1)", "Desulfovibrio alaskensis (strain G20)", "Desulfovibrio magneticus (strain ATCC 700980 / DSM 13731 / RS-1)", "Lawsonia intracellularis (strain PHE/MN1-00)", "Pseudodesulfovibrio aespoeensis (strain ATCC 700646 / DSM 10631 / Aspo-2)", "Pseudodesulfovibrio piezophilus (strain DSM 21447 / JCM 15486 / C1TLV30)", "Desulfomicrobium baculatum (strain DSM 4028 / VKM B-1378)", "Desulfohalobium retbaense (strain ATCC 49708 / DSM 5692 / JCM 16813 / HR100)", "Desulfobacterium autotrophicum (strain ATCC 43914 / DSM 3382 / HRM2)", "Desulfobacula toluolica (strain DSM 7467 / Tol2)", "Desulfococcus oleovorans (strain DSM 6200 / Hxd3)", "Desulfatibacillum alkenivorans (strain AK-01)", "Desulfobulbus propionicus (strain ATCC 33891 / DSM 2032 / 1pr3)", "Desulfocapsa sulfexigens (strain DSM 10523 / SB164P1)", "Desulfotalea psychrophila (strain LSv54 / DSM 12343)", "Desulfurivibrio alkaliphilus (strain DSM 19089 / UNIQEM U267 / AHT2)", "Desulfomonile tiedjei (strain ATCC 49306 / DSM 6799 / DCB-1)", "Syntrophus aciditrophicus (strain SB)", "Desulfobacca acetoxidans (strain ATCC 700848 / DSM 11109 / ASRB2)", "Syntrophobacter fumaroxidans (strain DSM 10017 / MPOB)", "Desulfarculus baarsii (strain ATCC 33931 / DSM 2075 / VKM B-1802 / 2st14)", "Nitratiruptor sp. (strain SB155-2)", "Sulfurovum sp. (strain NBC37-1)", "Helicobacter pylori (strain ATCC 700392 / 26695)", "Helicobacter pylori (strain J99 / ATCC 700824)", "Helicobacter pylori (strain F32)", "Helicobacter pylori (strain 51)", "Helicobacter pylori (strain HPAG1)", "Helicobacter pylori (strain Shi470)", "Helicobacter pylori (strain G27)", "Helicobacter pylori (strain P12)", "Helicobacter pylori (strain 35A)", "Helicobacter pylori (strain B38)", "Helicobacter pylori (strain v225d)", "Helicobacter pylori (strain 52)", "Helicobacter pylori (strain B8)", "Helicobacter pylori (strain SJM180)", "Helicobacter pylori (strain PeCan4)", "Helicobacter pylori (strain Cuz20)", "Helicobacter pylori (strain F16)", "Helicobacter pylori (strain F30)", "Helicobacter pylori (strain F57)", "Helicobacter pylori (strain 908)", "Helicobacter pylori (strain Lithuania75)", "Helicobacter pylori (strain India7)", "Helicobacter pylori (strain Gambia94/24)", "Helicobacter acinonychis (strain Sheeba)", "Helicobacter cinaedi (strain PAGU611)", "Helicobacter felis (strain ATCC 49179 / NCTC 12436 / CS1)", "Helicobacter mustelae (strain ATCC 43772 / LMG 18044 / NCTC 12198 / 12198)", "Helicobacter hepaticus (strain ATCC 51449 / 3B1)", "Helicobacter bizzozeronii (strain CIII-1)", "Sulfurimonas autotrophica (strain ATCC BAA-671 / DSM 16294 / JCM 11897 / OK10)", "Sulfurimonas denitrificans (strain ATCC 33889 / DSM 1251)", "Wolinella succinogenes (strain ATCC 29543 / DSM 1740 / LMG 7466 / NCTC 11488 / FDC 602W)", "Sulfuricurvum kujiense (strain ATCC BAA-921 / DSM 16994 / JCM 11577 / YK-1)", "Campylobacter fetus subsp. fetus (strain 82-40)", "Campylobacter jejuni subsp. doylei (strain ATCC BAA-1458 / RM4099 / 269.97)", "Campylobacter jejuni subsp. jejuni serotype O:2 (strain ATCC 700819 / NCTC 11168)", "Campylobacter jejuni subsp. jejuni serotype O:23/36 (strain 81-176)", "Campylobacter jejuni subsp. jejuni serotype O:6 (strain 81116 / NCTC 11828)", "Campylobacter jejuni subsp. jejuni (strain IA3902)", "Campylobacter jejuni subsp. jejuni serotype HS21 (strain M1 / 99/308)", "Campylobacter jejuni subsp. jejuni (strain S3)", "Campylobacter jejuni subsp. jejuni serotype HS:41 (strain ICDCCJ07001)", "Campylobacter jejuni (strain RM1221)", "Campylobacter concisus (strain 13826)", "Campylobacter curvus (strain 525.92)", "Campylobacter hominis (strain ATCC BAA-381 / LMG 19568 / NCTC 13146 / CH001A)", "Campylobacter lari (strain RM2100 / D67 / ATCC BAA-1060)", "Arcobacter butzleri (strain RM4018)", "Arcobacter nitrofigilis (strain ATCC 33309 / DSM 7299 / LMG 7604 / NCTC 12251 / CI)", "Sulfurospirillum barnesii (strain ATCC 700032 / DSM 10660 / SES-3)", "Sulfurospirillum deleyianum (strain ATCC 51133 / DSM 6946 / 5175)", "Nitratifractor salsuginis (strain DSM 16511 / JCM 12458 / E9I37-1)", "Nautilia profundicola (strain ATCC BAA-1463 / DSM 18972 / AmH)", "Bdellovibrio bacteriovorus (strain ATCC 15356 / DSM 50701 / NCIB 9529 / HD100)", "Halobacteriovorax marinus (strain ATCC BAA-682 / DSM 15412 / SJ)", "Acidithiobacillus ferrooxidans (strain ATCC 23270 / DSM 14882 / CIP 104768 / NCIMB 8455)", "Acidithiobacillus ferrooxidans (strain ATCC 53993)", "Acidithiobacillus caldus (strain SM-1)", "Staphylococcus aureus (strain NCTC 8325)", "Staphylococcus aureus (strain COL)", "Staphylococcus aureus (strain Mu50 / ATCC 700699)", "Staphylococcus aureus (strain N315)", "Staphylococcus aureus (strain MW2)", "Staphylococcus aureus (strain MRSA252)", "Staphylococcus aureus (strain MSSA476)", "Staphylococcus aureus (strain JH9)", "Staphylococcus aureus (strain JH1)", "Staphylococcus aureus (strain USA300 / TCH1516)", "Staphylococcus aureus (strain USA300)", "Staphylococcus aureus (strain Mu3 / ATCC 700698)", "Staphylococcus aureus (strain Newman)", "Staphylococcus aureus (strain MRSA ST398 / isolate S0385)", "Staphylococcus aureus (strain JKD6008)", "Staphylococcus aureus (strain TCH60)", "Staphylococcus aureus (strain TW20 / 0582)", "Staphylococcus aureus (strain ED98)", "Staphylococcus aureus subsp. aureus (strain ED133)", "Staphylococcus aureus (strain JKD6159)", "Staphylococcus aureus (strain ECT-R 2)", "Staphylococcus aureus (strain bovine RF122 / ET3-1)", "Staphylococcus aureus (strain 04-02981)", "Staphylococcus carnosus (strain TM300)", "Staphylococcus epidermidis (strain ATCC 35984 / RP62A)", "Staphylococcus epidermidis (strain ATCC 12228)", "Staphylococcus haemolyticus (strain JCSC1435)", "Staphylococcus hyicus", "Staphylococcus lugdunensis (strain HKU09-01)", "Staphylococcus pseudintermedius (strain HKU10-03)", "Staphylococcus pseudintermedius (strain ED99)", "Staphylococcus saprophyticus subsp. saprophyticus (strain ATCC 15305 / DSM 20229 / NCIMB 8711 / NCTC 7292 / S-41)", "Macrococcus caseolyticus (strain JCSC5402)", "Bacillus amyloliquefaciens (strain ATCC 23350 / DSM 7 / BCRC 11601 / NBRC 15535 / NRRL B-14393)", "Bacillus anthracis str. Ames Ancestor", "Bacillus anthracis (strain CDC 684 / NRRL 3495)", "Bacillus anthracis (strain A0248)", "Bacillus cereus (strain ATCC 10987 / NRS 248)", "Bacillus cereus (strain ATCC 14579 / DSM 31 / JCM 2152 / NBRC 15305 / NCIMB 9373 / NRRL B-3711)", "Bacillus cereus (strain ZK / E33L)", "Bacillus cereus (strain Q1)", "Bacillus cereus (strain G9842)", "Bacillus cereus (strain B4264)", "Bacillus cereus (strain AH187)", "Bacillus cereus (strain AH820)", "Bacillus cereus (strain 03BB102)", "Bacillus cereus var. anthracis (strain CI)", "Bacillus coagulans (strain 2-6)", "Bacillus licheniformis (strain ATCC 14580 / DSM 13 / JCM 2505 / NBRC 12200 / NCIMB 9375 / NRRL NRS-1264 / Gibson 46)", "Bacillus megaterium (strain ATCC 12872 / QMB1551)", "Bacillus megaterium (strain DSM 319)", "Bacillus mycoides (strain KBAB4)", "Bacillus pumilus (strain SAFR-032)", "Bacillus akibai (strain ATCC 43226 / DSM 21942 / JCM 9157 / 1139)", "Bacillus cellulosilyticus (strain ATCC 21833 / DSM 2522 / FERM P-1141 / JCM 9156 / N-4)", "Bacillus subtilis subsp. spizizenii (strain ATCC 23059 / NRRL B-14472 / W23)", "Bacillus subtilis subsp. spizizenii (strain TU-B-10)", "Bacillus subtilis (strain 168)", "Bacillus subtilis (strain BSn5)", "Bacillus thuringiensis subsp. finitimus (strain YBT-020)", "Bacillus thuringiensis subsp. konkukian (strain 97-27)", "Bacillus thuringiensis (strain Al Hakam)", "Bacillus thuringiensis (strain BMB171)", "Bacillus atrophaeus (strain 1942)", "Bacillus clausii (strain KSM-K16)", "Bacillus pseudofirmus (strain OF4)", "Bacillus halodurans (strain ATCC BAA-125 / DSM 18197 / FERM 7344 / JCM 9153 / C-125)", "Bacillus velezensis (strain DSM 23117 / BGSC 10A6 / FZB42)", "Bacillus cytotoxicus (strain DSM 22905 / CIP 110041 / 391-98 / NVH 391-98)", "Amphibacillus xylanus (strain ATCC 51415 / DSM 6626 / JCM 7361 / LMG 17667 / NBRC 15112 / Ep01)", "Geobacillus kaustophilus (strain HTA426)", "Geobacillus thermodenitrificans (strain NG80-2)", "Geobacillus sp. (strain WCH70)", "Geobacillus sp. (strain Y412MC61)", "Geobacillus sp. (strain Y4.1MC1)", "Anoxybacillus flavithermus (strain DSM 21510 / WK1)", "Oceanobacillus iheyensis (strain DSM 14371 / CIP 107618 / JCM 11309 / KCTC 3954 / HTE831)", "Lysinibacillus sphaericus (strain C3-41)", "Parageobacillus thermoglucosidasius (strain C56-YS93)", "Solibacillus silvestris (strain StLB046)", "Listeria ivanovii (strain ATCC BAA-678 / PAM 55)", "Listeria monocytogenes serovar 1/2a (strain ATCC BAA-679 / EGD-e)", "Listeria monocytogenes serotype 1/2a (strain 10403S)", "Listeria monocytogenes serotype 4a (strain HCC23)", "Listeria monocytogenes serotype 4a (strain L99)", "Listeria monocytogenes serotype 1/2a (strain 08-5923)", "Listeria monocytogenes serotype 4a (strain M7)", "Listeria monocytogenes serotype 4b (strain F2365)", "Listeria monocytogenes serotype 4b (strain CLIP80459)", "Listeria seeligeri serovar 1/2b (strain ATCC 35967 / DSM 20751 / CIP 100100 / SLCC 3954)", "Listeria innocua serovar 6a (strain ATCC BAA-680 / CLIP 11262)", "Listeria welshimeri serovar 6b (strain ATCC 35897 / DSM 20650 / SLCC5334)", "Bacillus selenitireducens (strain ATCC 700615 / DSM 15326 / MLS10)", "Paenibacillus polymyxa (strain E681)", "Paenibacillus polymyxa (strain SC2)", "Paenibacillus mucilaginosus (strain KNP414)", "Paenibacillus sp. (strain JDR-2)", "Geobacillus sp. (strain Y412MC10)", "Paenibacillus terrae (strain HPL-003)", "Brevibacillus brevis (strain 47 / JCM 6285 / NBRC 100599)", "Thermobacillus composti (strain DSM 18247 / JCM 13945 / KWC4)", "Alicyclobacillus acidocaldarius subsp. acidocaldarius (strain ATCC 27009 / DSM 446 / JCM 5260 / NBRC 15652 / NCIMB 11725 / NRRL B-14509 / 104-1A)", "Alicyclobacillus acidocaldarius (strain Tc-4-1)", "Kyrpidia tusciae (strain DSM 2912 / NBRC 15312 / T2)", "Exiguobacterium antarcticum (strain B7)", "Exiguobacterium sibiricum (strain DSM 17290 / JCM 13490 / 255-15)", "Exiguobacterium sp. (strain ATCC BAA-1283 / AT1b)", "Streptococcus gordonii (strain Challis / ATCC 35105 / BCRC 15272 / CH1 / DL1 / V288)", "Streptococcus oralis (strain Uo5)", "Streptococcus salivarius (strain JIM8777)", "Streptococcus salivarius (strain 57.I)", "Streptococcus salivarius (strain CCHSS3)", "Streptococcus sanguinis (strain SK36)", "Streptococcus suis (strain P1/7)", "Streptococcus suis (strain 05ZYH33)", "Streptococcus suis (strain 98HAH33)", "Streptococcus suis (strain GZ1)", "Streptococcus suis (strain SC84)", "Streptococcus suis (strain BM407)", "Streptococcus suis (strain JS14)", "Streptococcus thermophilus (strain ATCC BAA-250 / LMG 18311)", "Streptococcus thermophilus (strain CNRZ 1066)", "Streptococcus thermophilus (strain ATCC BAA-491 / LMD-9)", "Streptococcus thermophilus (strain ND03)", "Streptococcus mutans serotype c (strain ATCC 700610 / UA159)", "Streptococcus mutans serotype c (strain NN2025)", "Streptococcus agalactiae serotype V (strain ATCC BAA-611 / 2603 V/R)", "Streptococcus agalactiae serotype III (strain NEM316)", "Streptococcus agalactiae serotype Ia (strain ATCC 27591 / A909 / CDC SS700)", "Streptococcus agalactiae serotype Ia (strain GD201008-001)", "Streptococcus pneumoniae serotype 4 (strain ATCC BAA-334 / TIGR4)", "Streptococcus pneumoniae (strain ATCC BAA-255 / R6)", "Streptococcus pneumoniae (strain 670-6B)", "Streptococcus pneumoniae serotype 2 (strain D39 / NCTC 7466)", "Streptococcus pneumoniae (strain Taiwan19F-14)", "Streptococcus pneumoniae (strain Hungary19A-6)", "Streptococcus pneumoniae (strain 70585)", "Streptococcus pneumoniae (strain JJA)", "Streptococcus pneumoniae (strain P1031)", "Streptococcus pneumoniae serotype 19F (strain G54)", "Streptococcus pneumoniae (strain CGSP14)", "Streptococcus pneumoniae serotype A19 (strain TCH8431)", "Streptococcus pneumoniae (strain ATCC 700669 / Spain 23F-1)", "Streptococcus pneumoniae serotype 3 (strain OXC141)", "Streptococcus pneumoniae serotype 14 (strain INV200)", "Streptococcus pneumoniae serotype 1 (strain INV104)", "Streptococcus pneumoniae (strain ST556)", "Streptococcus pyogenes serotype M6 (strain ATCC BAA-946 / MGAS10394)", "Streptococcus pyogenes serotype M1", "Streptococcus pyogenes serotype M3 (strain SSI-1)", "Streptococcus pyogenes serotype M3 (strain ATCC BAA-595 / MGAS315)", "Streptococcus pyogenes serotype M5 (strain Manfredo)", "Streptococcus pyogenes serotype M18 (strain MGAS8232)", "Streptococcus pyogenes serotype M49 (strain NZ131)", "Streptococcus pyogenes serotype M28 (strain MGAS6180)", "Streptococcus pyogenes serotype M12 (strain MGAS9429)", "Streptococcus pyogenes serotype M12 (strain MGAS2096)", "Streptococcus pyogenes serotype M2 (strain MGAS10270)", "Streptococcus pyogenes serotype M4 (strain MGAS10750)", "Streptococcus dysgalactiae subsp. equisimilis (strain GGS_124)", "Streptococcus dysgalactiae subsp. equisimilis (strain ATCC 12394 / D166B)", "Streptococcus equi subsp. zooepidemicus (strain MGCS10565)", "Streptococcus equi subsp. zooepidemicus (strain H70)", "Streptococcus equi subsp. zooepidemicus (strain ATCC 35246 / C74-63)", "Streptococcus equi subsp. equi (strain 4047)", "Streptococcus intermedius (strain JTH08)", "Streptococcus parauberis (strain KCTC 11537)", "Streptococcus mitis (strain B6)", "Streptococcus gallolyticus (strain UCN34)", "Streptococcus gallolyticus (strain ATCC 43143 / F-1867)", "Streptococcus gallolyticus (strain ATCC BAA-2069)", "Streptococcus macedonicus (strain ACA-DC 198)", "Streptococcus infantarius (strain CJ18)", "Streptococcus pasteurianus (strain ATCC 43144 / JCM 5346 / CDC 1723-81)", "Streptococcus uberis (strain ATCC BAA-854 / 0140J)", "Streptococcus pseudopneumoniae (strain IS7493)", "Lactococcus lactis subsp. cremoris (strain SK11)", "Lactococcus lactis subsp. cremoris (strain MG1363)", "Lactococcus lactis subsp. cremoris (strain NZ9000)", "Lactococcus lactis subsp. lactis (strain IL1403)", "Lactococcus lactis subsp. lactis (strain KF147)", "Lactococcus lactis subsp. lactis (strain CV56)", "Lactococcus garvieae (strain ATCC 49156 / DSM 6783 / NCIMB 13208 / YT-3)", "Lactococcus garvieae (strain Lg2)", "Pediococcus claussenii (strain ATCC BAA-344 / DSM 14800 / JCM 18046 / KCTC 3811 / P06)", "Pediococcus pentosaceus (strain ATCC 25745 / CCUG 21536 / LMG 10740 / 183-1w)", "Lactobacillus acidophilus (strain ATCC 700396 / NCK56 / N2 / NCFM)", "Lactobacillus acidophilus (strain 30SC)", "Lactobacillus brevis (strain ATCC 367 / JCM 1170)", "Lactobacillus buchneri (strain NRRL B-30929)", "Lactobacillus casei (strain Zhang)", "Lactobacillus casei (strain BL23)", "Lactobacillus casei (strain BD-II)", "Lactobacillus casei (strain LC2W)", "Lactobacillus delbrueckii subsp. bulgaricus (strain ATCC BAA-365)", "Lactobacillus delbrueckii subsp. bulgaricus (strain 2038)", "Lactobacillus delbrueckii subsp. bulgaricus (strain ATCC 11842 / DSM 20081 / JCM 1002 / NBRC 13953 / NCIMB 11778)", "Lactobacillus delbrueckii subsp. bulgaricus (strain ND02)", "Lactobacillus helveticus (strain DPC 4571)", "Lactobacillus plantarum (strain ATCC BAA-793 / NCIMB 8826 / WCFS1)", "Lactobacillus plantarum (strain JDM1)", "Lactobacillus plantarum (strain ST-III)", "Lactobacillus gasseri (strain ATCC 33323 / DSM 20243 / JCM 1131 / NCIMB 11718 / AM63)", "Lactobacillus paracasei (strain ATCC 334 / BCRC 17002 / CIP 107868 / KCTC 3260 / NRRL B-441)", "Lactobacillus reuteri (strain ATCC 55730 / SD2112)", "Lactobacillus reuteri (strain JCM 1112)", "Lactobacillus reuteri (strain DSM 20016)", "Lactobacillus sakei subsp. sakei (strain 23K)", "Lactobacillus amylovorus (strain GRL 1112)", "Lactobacillus amylovorus (strain GRL 1118)", "Lactobacillus fermentum (strain NBRC 3956 / LMG 18251)", "Lactobacillus fermentum (strain CECT 5716)", "Lactobacillus ruminis (strain ATCC 27782 / RF3)", "Lactobacillus salivarius (strain UCC118)", "Lactobacillus salivarius (strain CECT 5713)", "Lactobacillus johnsonii (strain CNCM I-12250 / La1 / NCC 533)", "Lactobacillus johnsonii (strain FI9785)", "Lactobacillus rhamnosus (strain ATCC 53103 / GG)", "Lactobacillus rhamnosus (strain Lc 705)", "Lactobacillus crispatus (strain ST1)", "Lactobacillus kefiranofaciens (strain ZW3)", "Lactobacillus sanfranciscensis (strain TMW 1.1304)", "Leuconostoc gelidum subsp. gasicomitatum (strain DSM 15947 / CECT 5767 / JCM 12535 / LMG 18811 / TB1-10)", "Leuconostoc gelidum (strain JB7)", "Leuconostoc mesenteroides subsp. mesenteroides (strain ATCC 8293 / NCDO 523)", "Leuconostoc carnosum (strain JB16)", "Leuconostoc citreum (strain KM20)", "Leuconostoc sp. (strain C2)", "Oenococcus oeni (strain ATCC BAA-331 / PSU-1)", "Weissella viridescens", "Weissella koreensis (strain KACC 15510)", "Enterococcus faecalis (strain ATCC 700802 / V583)", "Enterococcus faecalis (strain ATCC 47077 / OG1RF)", "Enterococcus faecalis (strain 62)", "Enterococcus faecium (strain Aus0004)", "Melissococcus plutonius (strain ATCC 35311 / CIP 104052 / LMG 20360 / NCIMB 702443)", "Melissococcus plutonius (strain DAT561)", "Tetragenococcus halophilus (strain DSM 20338 / JCM 20259 / NCIMB 9735 / NBRC 12172)", "Aerococcus urinae (strain ACS-120-V-Col10a)", "Carnobacterium sp. (strain 17-4)", "Halanaerobium praevalens (strain ATCC 33744 / DSM 2228 / GSL)", "Halanaerobium hydrogeniformans", "Halothermothrix orenii (strain H 168 / OCM 544 / DSM 9562)", "Acetohalobium arabaticum (strain ATCC 49924 / DSM 5501 / Z-7288)", "Halobacteroides halobius (strain ATCC 35273 / DSM 5150 / MD-1)", "Thermoanaerobacter italicus (strain DSM 9252 / Ab9)", "Thermoanaerobacter sp. (strain X514)", "Thermoanaerobacter pseudethanolicus (strain ATCC 33223 / 39E)", "Thermoanaerobacter sp. (strain X513)", "Thermoanaerobacter mathranii subsp. mathranii (strain DSM 11426 / CIP 108742 / A3)", "Moorella thermoacetica (strain ATCC 39073 / JCM 9320)", "Carboxydothermus hydrogenoformans (strain ATCC BAA-161 / DSM 6008 / Z-2901)", "Thermacetogenium phaeum (strain ATCC BAA-254 / DSM 12270 / PB)", "Caldanaerobacter subterraneus subsp. tengcongensis (strain DSM 15242 / JCM 11007 / NBRC 100824 / MB4)", "Tepidanaerobacter acetatoxydans (strain DSM 21804 / JCM 16047 / Re1)", "Thermoanaerobacterium thermosaccharolyticum (strain ATCC 7956 / DSM 571 / NCIB 9385 / NCA 3814)", "Thermoanaerobacterium saccharolyticum (strain DSM 8691 / JW/SL-YS485)", "Thermoanaerobacterium xylanolyticum (strain ATCC 49914 / DSM 7097 / LX-11)", "Caldicellulosiruptor bescii (strain ATCC BAA-1888 / DSM 6725 / Z-1320)", "Caldicellulosiruptor kristjanssonii (strain ATCC 700853 / DSM 12137 / I77R1B)", "Caldicellulosiruptor owensensis (strain ATCC 700167 / DSM 13100 / OL)", "Caldicellulosiruptor saccharolyticus (strain ATCC 43494 / DSM 8903 / Tp8T 6331)", "Caldicellulosiruptor hydrothermalis (strain DSM 18901 / VKM B-2411 / 108)", "Caldicellulosiruptor kronotskyensis (strain DSM 18902 / VKM B-2412 / 2002)", "Caldicellulosiruptor obsidiansis (strain ATCC BAA-2073 / strain OB47)", "Thermosediminibacter oceani (strain ATCC BAA-1034 / DSM 16646 / JW/IW-1228P)", "Mahella australiensis (strain DSM 15567 / CIP 107919 / 50-1 BON)", "Clostridium acetobutylicum (strain ATCC 824 / DSM 792 / JCM 1419 / LMG 5710 / VKM B-1787)", "Clostridium acetobutylicum (strain EA 2018)", "Clostridium botulinum (strain ATCC 19397 / Type A)", "Clostridium botulinum (strain Hall / ATCC 3502 / NCTC 13319 / Type A)", "Clostridium botulinum (strain Loch Maree / Type A3)", "Clostridium botulinum (strain Kyoto / Type A2)", "Clostridium botulinum (strain Okra / Type B1)", "Clostridium botulinum (strain 657 / Type Ba4)", "Clostridium botulinum (strain Eklund 17B / Type B)", "Clostridium botulinum (strain Alaska E43 / Type E3)", "Clostridium botulinum (strain Langeland / NCTC 10281 / Type F)", "Clostridium botulinum (strain 230613 / Type F)", "Clostridium botulinum (strain H04402 065 / Type A5)", "Clostridium cellulovorans (strain ATCC 35296 / DSM 3052 / OCM 3 / 743B)", "Clostridium perfringens (strain 13 / Type A)", "Clostridium perfringens (strain ATCC 13124 / DSM 756 / JCM 1290 / NCIMB 6125 / NCTC 8237 / Type A)", "Clostridium perfringens (strain SM101 / Type A)", "Clostridium sp. (strain ATCC 29733 / VPI C48-50)", "Clostridium beijerinckii (strain ATCC 51743 / NCIMB 8052)", "Clostridium kluyveri (strain ATCC 8527 / DSM 555 / NCIMB 10680)", "Clostridium ljungdahlii (strain ATCC 55383 / DSM 13528 / PETC)", "Clostridium novyi (strain NT)", "Clostridium tetani (strain Massachusetts / E88)", "Clostridium sp. (strain SY8519)", "Arthromitus sp. (strain SFB-mouse-Japan)", "Alkaliphilus metalliredigens (strain QYMF)", "Alkaliphilus oremlandii (strain OhILAs)", "Heliobacterium modesticaldum (strain ATCC 51547 / Ice1)", "Syntrophomonas wolfei subsp. wolfei (strain DSM 2245B / Goettingen)", "Syntrophothermus lipocalidus (strain DSM 12680 / TGB-C1)", "Butyrivibrio proteoclasticus (strain ATCC 51982 / DSM 14932 / B316)", "Roseburia hominis (strain DSM 16839 / NCIMB 14029 / A2-183)", "Agathobacter rectalis (strain ATCC 33656 / DSM 3377 / JCM 17463 / KCTC 5835 / VPI 0990)", "Cellulosilyticum lentocellum (strain ATCC 49066 / DSM 5427 / NCIMB 11756 / RHM5)", "Clostridium saccharolyticum (strain ATCC 35040 / DSM 2544 / NRCC 2533 / WM1)", "Lachnoclostridium phytofermentans (strain ATCC 700394 / DSM 18823 / ISDg)", "Acetoanaerobium sticklandii (strain ATCC 12662 / DSM 519 / JCM 1433 / NCIMB 10654)", "Filifactor alocis (strain ATCC 35896 / D40 B5)", "Peptoclostridium difficile (strain R20291)", "Peptoclostridium difficile (strain 630)", "Eubacterium limosum (strain KIST612)", "Eubacterium eligens (strain ATCC 27750 / VPI C15-48)", "Acetobacterium woodii (strain ATCC 29683 / DSM 1030 / JCM 2381 / KCTC 1655 / WB1)", "Desulfotomaculum nigrificans (strain DSM 14880 / VKM B-2319 / CO-1-SRB)", "Desulfotomaculum reducens (strain MI-1)", "Desulfotomaculum ruminis (strain ATCC 23193 / DSM 2154 / NCIMB 8452 / DL)", "Desulfitobacterium hafniense (strain Y51)", "Desulfitobacterium hafniense (strain DCB-2 / DSM 10664)", "Desulfitobacterium dichloroeliminans (strain LMG P-21439 / DCA1)", "Syntrophobotulus glycolicus (strain DSM 8271 / FlGlyR)", "Desulfosporosinus meridiei (strain ATCC BAA-275 / DSM 13257 / NCIMB 13706 / S10)", "Desulfosporosinus orientis (strain ATCC 19365 / DSM 765 / NCIMB 8382 / VKM B-1628)", "Desulfosporosinus acidiphilus (strain DSM 22704 / JCM 16185 / SJ4)", "Pelotomaculum thermopropionicum (strain DSM 13744 / JCM 10971 / SI)", "Desulforudis audaxviator (strain MP104C)", "Thermincola potens (strain JR)", "Desulfofundulus kuznetsovii (strain DSM 6115 / VKM B-1805 / 17)", "Desulfofarcimen acetoxidans (strain ATCC 49208 / DSM 771 / VKM B-1644 / 5575)", "Oscillibacter valericigenes (strain DSM 18026 / NBRC 101213 / Sjm18-20)", "Sulfobacillus acidophilus (strain ATCC 700253 / DSM 10332 / NAL)", "Sulfobacillus acidophilus (strain TPY)", "Thermaerobacter marianensis (strain ATCC 700841 / DSM 12885 / JCM 10246 / 7p75a)", "Ruminococcus albus (strain ATCC 27210 / DSM 20455 / JCM 14654 / NCDO 2250 / 7)", "Ruminococcus champanellensis (strain DSM 18848 / JCM 17042 / KCTC 15320 / 18P13)", "Ethanoligenens harbinense (strain DSM 18485 / JCM 12961 / CGMCC 1.5033 / YUAN-3)", "Symbiobacterium thermophilum (strain T / IAM 14863)", "Ruminiclostridium cellulolyticum (strain ATCC 35319 / DSM 5812 / JCM 6584 / H10)", "Mageeibacillus indolicus (strain UPII9-5)", "Hungateiclostridium thermocellum (strain ATCC 27405 / DSM 1237 / JCM 9322 / NBRC 103400 / NCIMB 10682 / NRRL B-4536 / VPI 7372)", "Hungateiclostridium thermocellum (strain DSM 1313 / LMG 6656 / LQ8)", "Hungateiclostridium clariflavum (strain DSM 19732 / NBRC 101661 / EBR45)", "Natranaerobius thermophilus (strain ATCC BAA-1301 / DSM 18059 / JW/NM-WN-LF)", "Erysipelothrix rhusiopathiae (strain Fujisawa)", "Veillonella parvula (strain ATCC 10790 / DSM 2008 / JCM 12972 / Te3)", "Selenomonas ruminantium subsp. lactilytica (strain NBRC 103574 / TAM6421)", "Selenomonas sputigena (strain ATCC 35185 / DSM 20758 / VPI D19B-28)", "Acidaminococcus fermentans (strain ATCC 25085 / DSM 20731 / VR4)", "Acidaminococcus intestini (strain RyC-MR95)", "Anaerococcus prevotii (strain ATCC 9321 / DSM 20548 / JCM 6508 / PC1)", "Finegoldia magna (strain ATCC 29328)", "Gottschalkia acidurici (strain ATCC 7906 / DSM 604 / BCRC 14475 / CIP 104303 / NCIMB 10678 / 9a)", "Thermus thermophilus (strain HB27 / ATCC BAA-163 / DSM 7039)", "Thermus thermophilus (strain HB8 / ATCC 27634 / DSM 579)", "Thermus thermophilus (strain SG0.5JP17-16)", "Meiothermus ruber (strain ATCC 35948 / DSM 1279 / VKM B-1258 / 21)", "Meiothermus silvanus (strain ATCC 700542 / DSM 9946 / VI-R2)", "Marinithermus hydrothermalis (strain DSM 14884 / JCM 11576 / T1)", "Oceanithermus profundus (strain DSM 14977 / NBRC 100410 / VKM B-2274 / 506)", "Deinococcus proteolyticus (strain ATCC 35074 / DSM 20540 / JCM 6276 / NBRC 101906 / NCIMB 13154 / VKM Ac-1939 / CCM 2703 / MRP)", "Deinococcus geothermalis (strain DSM 11300)", "Deinococcus radiodurans (strain ATCC 13939 / DSM 20539 / JCM 16871 / LMG 4051 / NBRC 15346 / NCIMB 9279 / R1 / VKM B-1422)", "Deinococcus maricopensis (strain DSM 21211 / LMG 22137 / NRRL B-23946 / LB-34)", "Deinococcus deserti (strain VCD115 / DSM 17065 / LMG 22923)", "Deinococcus peraridilitoris (strain DSM 19664 / LMG 22246 / CIP 109416 / KR-200)", "Deinococcus gobiensis (strain DSM 21396 / JCM 16679 / CGMCC 1.7299 / I-0)", "Truepera radiovictrix (strain DSM 17093 / CIP 108686 / LMG 22925 / RQ-24)", "Arcanobacterium haemolyticum (strain ATCC 9345 / DSM 20595 / NBRC 15585 / NCTC 8452 / 11018)", "Mobiluncus curtisii (strain ATCC 43063 / DSM 2711 / V125)", "Acidimicrobium ferrooxidans (strain DSM 10331 / JCM 15462 / NBRC 103882 / ICP)", "Rubrobacter xylanophilus (strain DSM 9941 / NBRC 16129)", "Coriobacterium glomerans (strain ATCC 49209 / DSM 20642 / JCM 10262 / PW2)", "Atopobium parvulum (strain ATCC 33793 / DSM 20469 / JCM 10300 / VPI 0546)", "Olsenella uli (strain ATCC 49627 / DSM 7084 / CIP 109912 / JCM 12494 / NCIMB 702895 / VPI D76D-27C)", "Eggerthella lenta (strain ATCC 25559 / DSM 2243 / JCM 9979 / NCTC 11813 / VPI 0255)", "Eggerthella sp. (strain YY7918)", "Cryptobacterium curtum (strain ATCC 700683 / DSM 15641 / 12-3)", "Slackia heliotrinireducens (strain ATCC 29202 / DSM 20476 / NCTC 11029 / RHS 1)", "Bifidobacterium adolescentis (strain ATCC 15703 / DSM 20083 / NCTC 11814 / E194a)", "Bifidobacterium bifidum (strain PRL2010)", "Bifidobacterium bifidum (strain S17)", "Bifidobacterium asteroides (strain PRL2011)", "Bifidobacterium breve (strain ACS-071-V-Sch8b)", "Bifidobacterium dentium (strain ATCC 27534 / DSM 20436 / JCM 1195 / Bd1)", "Bifidobacterium animalis subsp. lactis (strain AD011)", "Bifidobacterium animalis subsp. lactis (strain BB-12)", "Bifidobacterium animalis subsp. lactis (strain DSM 10140 / JCM 10602 / LMG 18314)", "Bifidobacterium animalis subsp. lactis (strain V9)", "Bifidobacterium animalis subsp. lactis (strain Bl-04 / DGCC2908 / RB 4825 / SD5219)", "Bifidobacterium animalis subsp. animalis (strain ATCC 25527 / DSM 20104 / JCM 1190 / R101-8)", "Bifidobacterium longum subsp. longum (strain ATCC 15707 / DSM 20219 / JCM 1217 / NCTC 11818 / E194b)", "Bifidobacterium longum subsp. longum (strain JDM301)", "Bifidobacterium longum subsp. longum (strain BBMN68)", "Bifidobacterium longum subsp. infantis (strain ATCC 15697 / DSM 20088 / JCM 1222 / NCTC 11817 / S12)", "Bifidobacterium longum subsp. infantis (strain 157F)", "Bifidobacterium longum (strain DJO10A)", "Bifidobacterium longum (strain NCC 2705)", "Gardnerella vaginalis (strain ATCC 14019 / 317)", "Gardnerella vaginalis (strain 409-05)", "Gardnerella vaginalis (strain HMP9231)", "Micrococcus luteus (strain ATCC 4698 / DSM 20030 / JCM 1464 / NBRC 3333 / NCIMB 9278 / NCTC 2665 / VKM Ac-2230)", "Renibacterium salmoninarum (strain ATCC 33209 / DSM 20767 / JCM 11484 / NBRC 15589 / NCIMB 2235)", "Arthrobacter sp. (strain FB24)", "Rothia dentocariosa (strain ATCC 17931 / CDC X599 / XDIA)", "Rothia mucilaginosa (strain DY-18)", "Kocuria rhizophila (strain ATCC 9341 / DSM 348 / NBRC 103217 / DC2201)", "Glutamicibacter arilaitensis (strain DSM 16368 / CIP 108037 / IAM 15318 / JCM 13566 / Re117)", "Paenarthrobacter aurescens (strain TC1)", "Pseudarthrobacter chlorophenolicus (strain ATCC 700700 / DSM 12829 / CIP 107037 / JCM 12360 / KCTC 9906 / NCIMB 13794 / A6)", "Pseudarthrobacter phenanthrenivorans (strain DSM 18606 / JCM 16027 / LMG 23796 / Sphe3)", "Cellulomonas fimi (strain ATCC 484 / DSM 20113 / JCM 1341 / NBRC 15513 / NCIMB 8980 / NCTC 7547)", "Cellulomonas flavigena (strain ATCC 482 / DSM 20109 / NCIB 8073 / NRS 134)", "Cellulomonas gilvus (strain ATCC 13127 / NRRL B-14078)", "Isoptericola variabilis (strain 225)", "Xylanimonas cellulosilytica (strain DSM 15894 / CECT 5975 / LMG 20990 / XIL07)", "Brevibacterium linens", "Brachybacterium faecium (strain ATCC 43885 / DSM 4810 / NCIB 9860)", "Intrasporangium calvum (strain ATCC 23552 / DSM 43043 / JCM 3097 / NBRC 12989 / 7 KIP)", "Jonesia denitrificans (strain ATCC 14870 / DSM 20603 / CIP 55134)", "Clavibacter michiganensis subsp. sepedonicus (strain ATCC 33113 / DSM 20744 / JCM 9667 / LMG 2889 / C-1)", "Clavibacter michiganensis subsp. michiganensis (strain NCPPB 382)", "Leifsonia xyli subsp. xyli (strain CTCB07)", "Microbacterium testaceum (strain StLB037)", "Beutenbergia cavernae (strain ATCC BAA-8 / DSM 12333 / NBRC 16432)", "Kytococcus sedentarius (strain ATCC 14392 / DSM 20547 / CCM 314 / 541)", "Sanguibacter keddieii (strain ATCC 51767 / DSM 10542 / NCFB 3025 / ST-74)", "Tropheryma whipplei (strain Twist)", "Tropheryma whipplei (strain TW08/27)", "Corynebacterium diphtheriae (strain ATCC 700971 / NCTC 13129 / Biotype gravis)", "Corynebacterium diphtheriae (strain 31A)", "Corynebacterium diphtheriae (strain ATCC 27012 / C7 (beta))", "Corynebacterium diphtheriae (strain PW8)", "Corynebacterium diphtheriae (strain CDCE 8392)", "Corynebacterium diphtheriae (strain 241)", "Corynebacterium diphtheriae (strain HC01)", "Corynebacterium diphtheriae (strain HC02)", "Corynebacterium diphtheriae (strain HC03)", "Corynebacterium diphtheriae (strain HC04)", "Corynebacterium diphtheriae (strain VA01)", "Corynebacterium glutamicum (strain ATCC 13032 / K051)", "Corynebacterium glutamicum (strain ATCC 13032 / DSM 20300 / JCM 1318 / LMG 3730 / NCIMB 10025)", "Corynebacterium glutamicum (strain R)", "Corynebacterium pseudotuberculosis (strain 1002)", "Corynebacterium pseudotuberculosis (strain C231)", "Corynebacterium pseudotuberculosis (strain FRC41)", "Corynebacterium pseudotuberculosis (strain I19)", "Corynebacterium jeikeium (strain K411)", "Corynebacterium urealyticum (strain ATCC 43042 / DSM 7109)", "Corynebacterium ulcerans (strain BR-AD22)", "Corynebacterium efficiens (strain DSM 44549 / YS-314 / AJ 12310 / JCM 11189 / NBRC 100395)", "Corynebacterium kroppenstedtii (strain DSM 44385 / JCM 11950 / CIP 105744 / CCUG 35717)", "Corynebacterium lipophiloflavum (strain DSM 44291 / CCUG 37336)", "Corynebacterium aurimucosum (strain ATCC 700975 / DSM 44827 / CN-1)", "Corynebacterium resistens (strain DSM 45100 / JCM 12819 / GTC 2026)", "Corynebacterium variabile (strain DSM 44702 / JCM 12073 / NCIMB 30131)", "Mycobacterium kansasii", "Mycobacterium leprae (strain TN)", "Mycobacterium leprae (strain Br4923)", "Mycobacterium gordonae", "Mycobacterium marinum (strain ATCC BAA-535 / M)", "Mycobacterium asiaticum", "Mycobacterium shimoidei", "Mycobacterium bovis (strain BCG / Pasteur 1173P2)", "Mycobacterium bovis (strain BCG / Tokyo 172 / ATCC 35737 / TMC 1019)", "Mycobacterium bovis (strain ATCC BAA-935 / AF2122/97)", "Mycobacterium tuberculosis (strain ATCC 25618 / H37Rv)", "Mycobacterium tuberculosis (strain F11)", "Mycobacterium tuberculosis (strain ATCC 25177 / H37Ra)", "Mycobacterium tuberculosis (strain CCDC5079)", "Mycobacterium tuberculosis (strain CCDC5180)", "Mycobacterium tuberculosis (strain KZN 1435 / MDR)", "Mycobacterium africanum (strain GM041182)", "Mycobacterium canettii (strain CIPT 140010059)", "Mycobacterium avium (strain 104)", "Mycolicibacterium paratuberculosis (strain ATCC BAA-968 / K-10)", "Mycobacterium intracellulare (strain ATCC 13950 / DSM 43223 / JCM 6384 / NCTC 13025 / 3600)", "Mycobacterium sp. (strain MCS)", "Mycobacterium sp. (strain JLS)", "Mycobacterium sp. (strain KMS)", "Mycobacterium ulcerans (strain Agy99)", "Mycobacteroides chelonae", "Mycobacteroides abscessus (strain ATCC 19977 / DSM 44196 / CIP 104536 / JCM 13569 / NCTC 13031 / TMC 1543)", "Hoyosella subflava (strain DSM 45089 / JCM 17490 / NBRC 109087 / DQS3-9A1)", "Mycolicibacter sinensis (strain JDM601)", "Mycolicibacterium smegmatis (strain ATCC 700084 / mc(2)155)", "Mycolicibacterium thermoresistibile (strain ATCC 19527 / DSM 44167 / CIP 105390 / JCM 6362 / NCTC 10409 / 316)", "Mycobacterium chubuense (strain NBB4)", "Mycolicibacterium gilvum (strain DSM 45189 / LMG 24558 / Spyr1)", "Mycolicibacterium gilvum (strain PYR-GCK)", "Mycolicibacterium rhodesiae (strain NBB3)", "Mycolicibacterium hassiacum (strain DSM 44199 / CIP 105218 / JCM 12690 / 3849)", "Mycolicibacterium vanbaalenii (strain DSM 7251 / JCM 13017 / NRRL B-24157 / PYR-1)", "Nocardia cyriacigeorgica (strain GUH-2)", "Nocardia farcinica (strain IFM 10152)", "Rhodococcus erythropolis (strain PR4 / NBRC 100887)", "Rhodococcus hoagii (strain 103S)", "Rhodococcus jostii (strain RHA1)", "Rhodococcus opacus (strain B4)", "Gordonia bronchialis (strain ATCC 25592 / DSM 43247 / JCM 3198 / NCTC 10667)", "Gordonia polyisoprenivorans (strain DSM 44266 / VH2)", "Segniliparus rotundus (strain ATCC BAA-972 / CDC 1076 / CIP 108378 / DSM 44985 / JCM 13578)", "Tsukamurella paurometabola (strain ATCC 8368 / DSM 20162 / JCM 10117 / NBRC 16120 / NCTC 13040)", "Actinoplanes missouriensis (strain ATCC 14538 / DSM 43046 / CBS 188.64 / JCM 3121 / NCIMB 12654 / NBRC 102363 / 431)", "Actinoplanes utahensis", "Actinoplanes sp. (strain ATCC 31044 / CBS 674.73 / SE50/110)", "Micromonospora aurantiaca (strain ATCC 27029 / DSM 43813 / BCRC 12538 / CBS 129.76 / JCM 10878 / NBRC 16125 / NRRL B-16091 / INA 9442)", "Micromonospora sp. (strain L5)", "Salinispora arenicola (strain CNS-205)", "Salinispora tropica (strain ATCC BAA-916 / DSM 44818 / CNB-440)", "Verrucosispora maris (strain AB-18-032)", "Propionibacterium freudenreichii subsp. shermanii (strain ATCC 9614 / DSM 4902 / CIP 103027 / NCIMB 8099 / CIRM-BIA1)", "Microlunatus phosphovorus (strain ATCC 700054 / DSM 10555 / JCM 9379 / NBRC 101784 / NCIMB 13414 / VKM Ac-1990 / NM-1)", "Pseudopropionibacterium propionicum (strain F0230a)", "Acidipropionibacterium acidipropionici (strain ATCC 4875 / DSM 20272 / JCM 6432 / NBRC 12425 / NCIMB 8070)", "Cutibacterium acnes (strain DSM 16379 / KPA171202)", "Cutibacterium acnes (strain SK137)", "Nocardioides sp. (strain ATCC BAA-499 / JS614)", "Nocardioides simplex", "Kribbella flavida (strain DSM 17836 / JCM 10339 / NBRC 14399)", "Amycolatopsis mediterranei (strain S699)", "Amycolatopsis mediterranei (strain U-32)", "Saccharopolyspora erythraea (strain ATCC 11635 / DSM 40517 / JCM 4748 / NBRC 13426 / NCIMB 8594 / NRRL 2338)", "Pseudonocardia dioxanivorans (strain ATCC 55486 / DSM 44775 / JCM 13855 / CB1190)", "Saccharomonospora viridis (strain ATCC 15386 / DSM 43017 / JCM 3036 / NBRC 12207 / P101)", "Actinosynnema mirum (strain ATCC 29888 / DSM 43827 / NBRC 14064 / IMRU 3971)", "Lentzea aerocolonigenes", "Saccharothrix espanaensis (strain ATCC 51144 / DSM 44229 / JCM 9112 / NBRC 15066 / NRRL 15764)", "Streptomyces ambofaciens (strain ATCC 23877 / 3486 / DSM 40053 / JCM 4204 / NBRC 12836 / NRRL B-2516)", "Streptomyces clavuligerus (strain ATCC 27064 / DSM 738 / JCM 4710 / NBRC 13307 / NCIMB 12785 / NRRL 3585 / VKM Ac-602)", "Streptomyces coelicolor (strain ATCC BAA-471 / A3(2) / M145)", "Streptomyces fradiae", "Streptomyces griseus subsp. griseus (strain JCM 4626 / NBRC 13350)", "Streptomyces hygroscopicus subsp. jinggangensis (strain 5008)", "Streptomyces rimosus subsp. rimosus (strain ATCC 10970 / DSM 40260 / JCM 4667 / NRRL 2234)", "Streptomyces scabiei (strain 87.22)", "Streptomyces cattleya (strain ATCC 35852 / DSM 46488 / JCM 4925 / NBRC 14057 / NRRL 8057)", "Streptomyces avermitilis (strain ATCC 31267 / DSM 46492 / JCM 5070 / NBRC 14893 / NCIMB 12804 / NRRL 8165 / MA-4680)", "Streptomyces pristinaespiralis (strain ATCC 25486 / DSM 40338 / CBS 914.69 / JCM 4507 / NBRC 13074 / NRRL 2958 / 5647)", "Streptomyces collinus (strain DSM 40733 / Tu 365)", "Streptomyces venezuelae (strain ATCC 10712 / CBS 650.69 / DSM 40230 / JCM 4526 / NBRC 13096 / PD 04745)", "Streptomyces toyocaensis", "Streptomyces albulus", "Streptomyces tsukubensis (strain DSM 42081 / NBRC 108919 / NRRL 18488 / 9993)", "Streptomyces davaonensis (strain DSM 101723 / JCM 4913 / KCC S-0913 / 768)", "Streptomyces rubellomurinus (strain ATCC 31215)", "Streptomyces bingchenggensis (strain BCW-1)", "Streptomyces sp. (strain SPB074)", "Streptomyces viridosporus (strain ATCC 14672 / DSM 40746 / JCM 4963 / KCTC 9882 / NRRL B-12104 / FH 1290)", "Streptomyces sp. (strain SirexAA-E / ActE)", "Streptomyces pratensis (strain ATCC 33331 / IAF-45CD)", "Kitasatospora aureofaciens", "Kitasatospora griseola", "Kitasatospora setae (strain ATCC 33774 / DSM 43861 / JCM 3304 / KCC A-0304 / NBRC 14216 / KM-6054)", "Streptosporangium roseum (strain ATCC 12428 / DSM 43021 / JCM 3005 / NI 9100)", "Nocardiopsis alba (strain ATCC BAA-2165 / BE74)", "Nocardiopsis dassonvillei (strain ATCC 23218 / DSM 43111 / CIP 107115 / JCM 7437 / KCTC 9190 / NBRC 14626 / NCTC 10488 / NRRL B-5397 / IMRU 509)", "Thermobifida fusca (strain YX)", "Thermomonospora curvata (strain ATCC 19995 / DSM 43183 / JCM 3096 / NBRC 15933 / NCIMB 10081 / Henssen B9)", "Frankia alni (strain ACN14a)", "Frankia casuarinae (strain DSM 45818 / CECT 9043 / CcI3)", "Frankia sp. (strain EAN1pec)", "Frankia inefficax (strain DSM 45817 / CECT 9037 / EuI1c)", "Frankia symbiont subsp. Datisca glomerata", "Stackebrandtia nassauensis (strain DSM 44728 / NRRL B-16338 / NBRC 102104 / LLR-40K-21)", "Catenulispora acidiphila (strain DSM 44928 / NRRL B-24433 / NBRC 102108 / JCM 14897)", "Conexibacter woesei (strain DSM 14684 / JCM 11494 / NBRC 100937 / ID131577)", "Kineococcus radiotolerans (strain ATCC BAA-149 / DSM 14245 / SRS30216)", "Geodermatophilus obscurus (strain ATCC 25078 / DSM 43160 / JCM 3152 / G-20)", "Blastococcus saxobsidens (strain DD2)", "Modestobacter marinus (strain BC501)", "Acidothermus cellulolyticus (strain ATCC 43068 / 11B)", "Nakamurella multipartita (strain ATCC 700099 / DSM 44233 / CIP 104796 / JCM 9543 / NBRC 105858 / Y-104)", "Thermobispora bispora (strain ATCC 19993 / DSM 43833 / CBS 139.67 / JCM 10125 / NBRC 14880 / R51)", "Fusobacterium nucleatum subsp. nucleatum (strain ATCC 25586 / CIP 101130 / JCM 8532 / LMG 13131)", "Ilyobacter polytropus (strain DSM 2926 / CuHBu1)", "Leptotrichia buccalis (strain ATCC 14201 / DSM 1135 / JCM 12969 / NCTC 10249 / C-1013-b)", "Sebaldella termitidis (strain ATCC 33386 / NCTC 11300)", "Streptobacillus moniliformis (strain ATCC 14647 / DSM 12112 / NCTC 10651 / 9901)", "Leptospirillum ferrooxidans (strain C2-3)", "Leptospirillum ferriphilum (strain ML-04)", "Nitrospira moscoviensis", "Thermodesulfovibrio yellowstonii (strain ATCC 51303 / DSM 11347 / YP87)", "Acidobacterium capsulatum (strain ATCC 51196 / DSM 11244 / JCM 7670 / NBRC 15755 / NCIMB 13165 / 161)", "Terriglobus roseus (strain DSM 18391 / NRRL B-41598 / KBS 63)", "Terriglobus saanensis (strain ATCC BAA-1853 / DSM 23119 / SP1PR4)", "Koribacter versatilis (strain Ellin345)", "Granulicella mallensis (strain ATCC BAA-1857 / DSM 23137 / MP5ACTX8)", "Granulicella tundricola (strain ATCC BAA-1859 / DSM 23138 / MP5ACTX9)", "Solibacter usitatus (strain Ellin6076)", "Chloracidobacterium thermophilum (strain B)", "Fibrobacter succinogenes (strain ATCC 19169 / S85)", "Thermodesulfatator indicus (strain DSM 15286 / JCM 11887 / CIR29812)", "Thermodesulfobacterium geofontis (strain OPF15)", "Caldisericum exile (strain DSM 21853 / NBRC 104410 / AZM16c01)", "Chthonomonas calidirosea (strain DSM 23976 / ICMP 18418 / T49)", "Dictyoglomus thermophilum (strain ATCC 35947 / DSM 3960 / H-6-12)", "Dictyoglomus turgidum (strain Z-1310 / DSM 6724)", "Deferribacter desulfuricans (strain DSM 14783 / JCM 11476 / NBRC 101012 / SSM1)", "Denitrovibrio acetiphilus (strain DSM 12809 / N2460)", "Calditerrivibrio nitroreducens (strain DSM 19672 / NBRC 101217 / Yu37-1)", "Flexistipes sinusarabici (strain DSM 4947 / MAS 10)", "Uncultured termite group 1 bacterium phylotype Rs-D17", "Elusimicrobium minutum (strain Pei191)", "Pedosphaera parvula (strain Ellin514)", "Akkermansia muciniphila (strain ATCC BAA-835 / Muc)", "Opitutus terrae (strain DSM 11246 / JCM 15787 / PB90-1)", "Coraliomargarita akajimensis (strain DSM 45221 / IAM 15411 / JCM 23193 / KCTC 12865 / 04OKA010-24)", "Methylacidiphilum infernorum (isolate V4)", "Desulfurispirillum indicum (strain ATCC BAA-1389 / S5)", "Gemmatimonas aurantiaca (strain T-27 / DSM 14586 / JCM 11422 / NBRC 100505)", "Hydrogenobacter thermophilus (strain DSM 6534 / IAM 12695 / TK-6)", "Aquifex aeolicus (strain VF5)", "Hydrogenobaculum sp. (strain Y04AAS1)", "Thermocrinis albus (strain DSM 14484 / JCM 11386 / HI 11/12)", "Thermosulfidibacter takaii (strain DSM 17441 / JCM 13301 / NBRC 103674 / ABI70S6)", "Persephonella marina (strain DSM 14350 / EX-H1)", "Sulfurihydrogenibium azorense (strain Az-Fu1 / DSM 15241 / OCM 825)", "Sulfurihydrogenibium sp. (strain YO3AOP1)", "Desulfurobacterium thermolithotrophum (strain DSM 11699 / BSA)", "Thermovibrio ammonificans (strain DSM 15698 / JCM 12110 / HB-1)", "Thermotoga maritima (strain ATCC 43589 / MSB8 / DSM 3109 / JCM 10099)", "Thermotoga neapolitana (strain ATCC 49049 / DSM 4359 / NS-E)", "Thermotoga petrophila (strain RKU-1 / ATCC BAA-488 / DSM 13995)", "Thermotoga naphthophila (strain ATCC BAA-489 / DSM 13996 / JCM 10882 / RKU-10)", "Thermotoga sp. (strain RQ2)", "Pseudothermotoga lettingae (strain ATCC BAA-301 / DSM 14385 / NBRC 107922 / TMO)", "Thermosipho africanus (strain TCF52B)", "Thermosipho melanesiensis (strain DSM 12029 / CIP 104789 / BI429)", "Fervidobacterium nodosum (strain ATCC 35602 / DSM 5306 / Rt17-B1)", "Fervidobacterium pennivorans (strain DSM 9078 / Ven5)", "Kosmotoga olearia (strain ATCC BAA-1733 / DSM 21960 / TBF 19.5.1)", "Marinitoga piezophila (strain DSM 14283 / JCM 11233 / KA3)", "Petrotoga mobilis (strain DSM 10674 / SJ95)", "Defluviitoga tunisiensis", "Chloroflexus aurantiacus (strain ATCC 29366 / DSM 635 / J-10-fl)", "Chloroflexus aurantiacus (strain ATCC 29364 / DSM 637 / Y-400-fl)", "Chloroflexus aggregans (strain MD-66 / DSM 9485)", "Roseiflexus castenholzii (strain DSM 13941 / HLO8)", "Roseiflexus sp. (strain RS-1)", "Herpetosiphon aurantiacus (strain ATCC 23779 / DSM 785 / 114-95)", "Sphaerobacter thermophilus (strain DSM 20745 / S 6022)", "Thermomicrobium roseum (strain ATCC 27502 / DSM 5159 / P-2)", "Anaerolinea thermophila (strain DSM 14523 / JCM 11388 / NBRC 100420 / UNI-1)", "Dehalogenimonas lykanthroporepellens (strain ATCC BAA-1523 / JCM 15061 / BL-DC-9)", "Dehalococcoides mccartyi (strain ATCC BAA-2100 / JCM 16839 / KCTC 5957 / BAV1)", "Dehalococcoides mccartyi (strain ATCC BAA-2266 / KCTC 15142 / 195)", "Dehalococcoides mccartyi (strain CBDB1)", "Dehalococcoides mccartyi (strain VS)", "Dehalococcoides mccartyi (strain GT)", "Caldilinea aerophila (strain DSM 14535 / JCM 11387 / NBRC 104270 / STL-6-O1)", "Pirellula staleyi (strain ATCC 27377 / DSM 6068 / ICPB 4128)", "Rhodopirellula baltica (strain DSM 10527 / NCIMB 13988 / SH1)", "Rubinisphaera brasiliensis (strain ATCC 49424 / DSM 5305 / JCM 21570 / NBRC 103401 / IFAM 1448)", "Planctopirus limnophila (strain ATCC 43296 / DSM 3776 / IFAM 1008 / 290)", "Isosphaera pallida (strain ATCC 43644 / DSM 9630 / IS1B)", "Singulisphaera acidiphila (strain ATCC BAA-1392 / DSM 18658 / VKM B-2454 / MOB10)", "Phycisphaera mikurensis (strain NBRC 102666 / KCTC 22515 / FYK2301M01)", "Spirochaeta thermophila (strain ATCC 49972 / DSM 6192 / RI 19.B1)", "Spirochaeta thermophila (strain ATCC 700085 / DSM 6578 / Z-1203)", "Spirochaeta africana (strain ATCC 700263 / DSM 8902 / Z-7692)", "Treponema denticola (strain ATCC 35405 / CIP 103919 / DSM 14222)", "Treponema pallidum (strain Nichols)", "Treponema pallidum subsp. pallidum (strain SS14)", "Treponema pallidum subsp. pallidum (strain Chicago)", "Treponema pallidum subsp. pertenue (strain Samoa D)", "Treponema pallidum subsp. pertenue (strain CDC2)", "Treponema paraluiscuniculi (strain Cuniculi A)", "Treponema brennaborense (strain DSM 12168 / CIP 105900 / DD5/3)", "Treponema primitia (strain ATCC BAA-887 / DSM 12427 / ZAS-2)", "Treponema azotonutricium (strain ATCC BAA-888 / DSM 13862 / ZAS-9)", "Treponema caldarium (strain ATCC 51460 / DSM 7334 / H1)", "Treponema succinifaciens (strain ATCC 33096 / DSM 2489 / 6091)", "Sphaerochaeta pleomorpha (strain ATCC BAA-1885 / DSM 22778 / Grapes)", "Sphaerochaeta coccoides (strain ATCC BAA-1237 / DSM 17374 / SPN1)", "Sphaerochaeta globosa (strain ATCC BAA-1886 / DSM 22777 / Buddy)", "Sediminispirochaeta smaragdinae (strain DSM 11293 / JCM 15392 / SEBR 4228)", "Borrelia hermsii (strain HS1 / DAH)", "Borrelia crocidurae (strain Achema)", "Borrelia duttonii (strain Ly)", "Borrelia recurrentis (strain A1)", "Borrelia turicatae (strain 91E135)", "Borrelia burgdorferi (strain ATCC 35210 / B31 / CIP 102532 / DSM 4680)", "Borrelia burgdorferi (strain ZS7)", "Borrelia burgdorferi (strain N40)", "Borrelia afzelii (strain PKo)", "Borreliella bavariensis (strain ATCC BAA-2496 / DSM 23469 / PBi)", "Brachyspira hyodysenteriae (strain ATCC 49526 / WA1)", "Brachyspira intermedia (strain ATCC 51140 / PWS/A)", "Brachyspira murdochii (strain ATCC 51284 / DSM 12563 / 56-150)", "Brachyspira pilosicoli (strain ATCC BAA-1826 / 95/1000)", "Leptospira biflexa serovar Patoc (strain Patoc 1 / Ames)", "Leptospira biflexa serovar Patoc (strain Patoc 1 / ATCC 23582 / Paris)", "Leptospira interrogans serogroup Icterohaemorrhagiae serovar copenhageni (strain Fiocruz L1-130)", "Leptospira interrogans serogroup Icterohaemorrhagiae serovar Lai (strain 56601)", "Leptospira interrogans serogroup Icterohaemorrhagiae serovar Lai (strain IPAV)", "Leptospira borgpetersenii serovar Hardjo-bovis (strain L550)", "Leptospira borgpetersenii serovar Hardjo-bovis (strain JB197)", "Turneriella parva (strain ATCC BAA-1111 / DSM 21527 / NCTC 11395 / H)", "Chlamydia trachomatis (strain D/UW-3/Cx)", "Chlamydia trachomatis serovar A (strain ATCC VR-571B / DSM 19440 / HAR-13)", "Chlamydia trachomatis serovar L2 (strain 434/Bu / ATCC VR-902B)", "Chlamydia trachomatis serovar L2b (strain UCH-1/proctitis)", "Chlamydia trachomatis serovar A (strain A2497)", "Chlamydia trachomatis serovar B (strain Jali20/OT)", "Chlamydia trachomatis serovar E (strain Sweden2)", "Chlamydia trachomatis serovar B (strain TZ1A828/OT)", "Chlamydia trachomatis serovar E (strain E/11023)", "Chlamydia trachomatis serovar E (strain E/150)", "Chlamydia trachomatis serovar G (strain G/9768)", "Chlamydia trachomatis serovar G (strain G/11222)", "Chlamydia trachomatis serovar G (strain G/11074)", "Chlamydia trachomatis serovar G (strain G/9301)", "Chlamydia trachomatis serovar D (strain D-EC)", "Chlamydia trachomatis serovar D (strain D-LC)", "Chlamydia trachomatis (strain L2c)", "Chlamydophila psittaci (strain ATCC VR-125 / 6BC)", "Chlamydophila psittaci (strain RD1)", "Chlamydia abortus (strain DSM 27085 / S26/3)", "Chlamydia felis (strain Fe/C-56)", "Chlamydophila caviae (strain ATCC VR-813 / DSM 19441 / GPIC)", "Chlamydia pneumoniae CWL029", "Chlamydophila pneumoniae (strain LPCoLN)", "Chlamydia muridarum (strain MoPn / Nigg)", "Chlamydia pecorum (strain ATCC VR-628 / E58)", "Simkania negevensis (strain ATCC VR-1471 / Z)", "Protochlamydia amoebophila (strain UWE25)", "Parachlamydia acanthamoebae (strain UV7)", "Waddlia chondrophila (strain ATCC VR-1470 / WSU 86-1044)", "Thermobaculum terrenum (strain ATCC BAA-798 / YNP1)", "Cloacimonas acidaminovorans (strain Evry)", "Acetomicrobium mobile (strain ATCC BAA-54 / DSM 13181 / JCM 12221 / NGA)", "Thermanaerovibrio acidaminovorans (strain ATCC 49978 / DSM 6589 / Su883)", "Aminobacterium colombiense (strain DSM 12261 / ALA-1)", "Thermovirga lienii (strain ATCC BAA-1197 / DSM 17291 / Cas60314)", "Mycoplasma capricolum subsp. capricolum (strain California kid / ATCC 27343 / NCTC 10154)", "Mycoplasma gallisepticum (strain R(low / passage 15 / clone 2))", "Mycoplasma gallisepticum (strain R(high / passage 156))", "Mycoplasma gallisepticum (strain F)", "Mycoplasma genitalium (strain ATCC 33530 / G-37 / NCTC 10195)", "Mycoplasma hominis (strain ATCC 23114 / NBRC 14850 / NCTC 10111 / PG21)", "Mycoplasma hyopneumoniae (strain J / ATCC 25934 / NCTC 10110)", "Mycoplasma hyopneumoniae (strain 7448)", "Mycoplasma hyopneumoniae (strain 232)", "Mycoplasma hyopneumoniae (strain 168)", "Mycoplasma hyorhinis (strain HUB-1)", "Mycoplasma hyorhinis (strain MCLD)", "Mycoplasma mycoides subsp. mycoides SC (strain PG1)", "Mycoplasma mycoides subsp. mycoides SC (strain Gladysdale)", "Mycoplasma pneumoniae (strain ATCC 29342 / M129)", "Mycoplasma pneumoniae (strain ATCC 15531 / DSM 22911 / NBRC 14401 / NCTC 10119 / FH)", "Mycoplasma leachii (strain 99/014/6)", "Mycoplasma leachii (strain DSM 21131 / NCTC 10133 / N29 / PG50)", "Mycoplasma pulmonis (strain UAB CTIP)", "Mycoplasma synoviae (strain 53)", "Mycoplasma agalactiae (strain PG2)", "Mycoplasma agalactiae (strain 5632)", "Mycoplasma arthritidis (strain 158L3-1)", "Mycoplasma fermentans (strain ATCC 19989 / NBRC 14854 / NCTC 10117 / PG18)", "Mycoplasma fermentans (strain JER)", "Mycoplasma fermentans (strain M64)", "Mycoplasma mobile (strain ATCC 43663 / 163K / NCTC 11711)", "Mycoplasma putrefaciens (strain ATCC 15718 / NCTC 10155 / C30 KS-1 / KS-1)", "Mycoplasma penetrans (strain HF-2)", "Mycoplasma bovis (strain ATCC 25523 / DSM 22781 / NCTC 10131 / PG45)", "Mycoplasma bovis (strain Hubei-1)", "Mycoplasma haemofelis (strain Ohio2)", "Mycoplasma haemofelis (strain Langford 1)", "Mycoplasma conjunctivae (strain ATCC 25834 / HRC/581 / NCTC 10147)", "Mycoplasma crocodyli (strain ATCC 51981 / MP145)", "Mycoplasma suis (strain KI_3806)", "Mycoplasma suis (strain Illinois)", "Mycoplasma haemocanis (strain Illinois)", "Mycoplasma haemolamae (strain Purdue)", "Mycoplasma cynos (strain C142)", "Mycoplasma wenyonii (strain Massachusetts)", "Ureaplasma parvum serovar 3 (strain ATCC 700970)", "Ureaplasma parvum serovar 3 (strain ATCC 27815 / 27 / NCTC 11736)", "Ureaplasma urealyticum serovar 10 (strain ATCC 33699 / Western)", "Mesoplasma florum (strain ATCC 33453 / NBRC 100688 / NCTC 11704 / L1)", "Acholeplasma laidlawii (strain PG-8A)", "Phytoplasma mali (strain AT)", "Phytoplasma australiense", "Aster yellows witches-broom phytoplasma (strain AYWB)", "Onion yellows phytoplasma (strain OY-M)", "Ignavibacterium album (strain DSM 19864 / JCM 16511 / NBRC 101810 / Mat9-16)", "Melioribacter roseus (strain JCM 17771 / P3M-2)", "Nitrospina gracilis (strain 3/211)", "Yanofskybacteria sp. (strain GW2011_GWA1_39_13)", "Coprothermobacter proteolyticus (strain ATCC 35245 / DSM 5265 / BT)", "Thermoproteus tenax (strain ATCC 35583 / DSM 2078 / JCM 9277 / NBRC 100435 / Kra 1)", "Thermoproteus uzoniensis (strain 768-20)", "Pyrobaculum islandicum (strain DSM 4184 / JCM 9189 / GEO3)", "Pyrobaculum aerophilum (strain ATCC 51768 / IM2 / DSM 7523 / JCM 9630 / NBRC 100827)", "Pyrobaculum neutrophilum (strain DSM 2338 / JCM 9278 / V24Sta)", "Pyrobaculum arsenaticum (strain DSM 13514 / JCM 11321)", "Pyrobaculum calidifontis (strain JCM 11548 / VA1)", "Pyrobaculum oguniense (strain DSM 13380 / JCM 10595 / TE7)", "Caldivirga maquilingensis (strain ATCC 700844 / DSM 13496 / JCM 10307 / IC-167)", "Vulcanisaeta distributa (strain DSM 14429 / JCM 11212 / NBRC 100878 / IC-017)", "Vulcanisaeta moutnovskia (strain 768-28)", "Thermofilum pendens (strain DSM 2475 / Hrk 5)", "Sulfolobus acidocaldarius (strain ATCC 33909 / DSM 639 / JCM 8929 / NBRC 15157 / NCIMB 11770)", "Sulfolobus islandicus (strain Y.N.15.51 / Yellowstone #2)", "Sulfolobus islandicus (strain L.D.8.5 / Lassen #2)", "Sulfolobus islandicus (strain M.16.4 / Kamchatka #3)", "Sulfolobus islandicus (strain M.14.25 / Kamchatka #1)", "Sulfolobus islandicus (strain M.16.27)", "Sulfolobus islandicus (strain L.S.2.15 / Lassen #1)", "Sulfolobus islandicus (strain Y.G.57.14 / Yellowstone #1)", "Sulfolobus islandicus (strain HVE10/4)", "Sulfolobus islandicus (strain REY15A)", "Acidianus hospitalis (strain W1)", "Metallosphaera sedula (strain ATCC 51363 / DSM 5348 / JCM 9185 / NBRC 15509 / TH2)", "Metallosphaera cuprina (strain Ar-4)", "Sulfurisphaera tokodaii (strain DSM 16993 / JCM 10545 / NBRC 100140 / 7)", "Saccharolobus solfataricus (strain ATCC 35092 / DSM 1617 / JCM 11322 / P2)", "Saccharolobus solfataricus (strain 98/2)", "Desulfurococcus amylolyticus (strain DSM 18924 / JCM 16383 / VKM B-2413 / 1221n)", "Desulfurococcus mucosus (strain ATCC 35584 / DSM 2162 / JCM 9187 / O7/1)", "Staphylothermus hellenicus (strain DSM 12710 / JCM 10830 / BK20S6-10-b1 / P8)", "Staphylothermus marinus (strain ATCC 43588 / DSM 3639 / JCM 9404 / F1)", "Ignicoccus hospitalis (strain KIN4/I / DSM 18386 / JCM 14125)", "Aeropyrum pernix (strain ATCC 700893 / DSM 11879 / JCM 9820 / NBRC 100138 / K1)", "Ignisphaera aggregans (strain DSM 17230 / JCM 13409 / AQ1.S1)", "Thermogladius calderae (strain DSM 22663 / VKM B-2946 / 1633)", "Thermosphaera aggregans (strain DSM 11486 / M11TL)", "Pyrodictium occultum", "Hyperthermus butylicus (strain DSM 5456 / JCM 9403 / PLM1-5)", "Pyrolobus fumarii (strain DSM 11204 / 1A)", "Fervidicoccus fontis (strain DSM 19380 / JCM 18336 / VKM B-2539 / Kam940)", "Acidilobus saccharovorans (strain DSM 16705 / JCM 18335 / VKM B-2471 / 345-15)", "Caldisphaera lagunensis (strain DSM 15908 / JCM 11604 / IC-154)", "Crenarchaeota archaeon SCGC AAA471-B05", "Methanobacterium paludis (strain DSM 25820 / JCM 18151 / SWAN1)", "Methanobacterium lacus (strain AL-21)", "Methanobrevibacter ruminantium (strain ATCC 35063 / DSM 1093 / JCM 13430 / OCM 146 / M1)", "Methanobrevibacter smithii (strain ATCC 35061 / DSM 861 / OCM 144 / PS)", "Methanosphaera stadtmanae (strain ATCC 43021 / DSM 3091 / JCM 11832 / MCB-3)", "Methanothermobacter marburgensis (strain ATCC BAA-927 / DSM 2133 / JCM 14651 / NBRC 100331 / OCM 82 / Marburg)", "Methanothermobacter thermautotrophicus (strain ATCC 29096 / DSM 1053 / JCM 10044 / NBRC 100330 / Delta H)", "Methanothermus fervidus (strain ATCC 43054 / DSM 2088 / JCM 10308 / V24 S)", "Methanococcus vannielii (strain ATCC 35089 / DSM 1224 / JCM 13029 / OCM 148 / SB)", "Methanococcus maripaludis (strain S2 / LL)", "Methanococcus maripaludis (strain C5 / ATCC BAA-1333)", "Methanococcus maripaludis (strain C7 / ATCC BAA-1331)", "Methanococcus maripaludis (strain C6 / ATCC BAA-1332)", "Methanococcus maripaludis X1", "Methanococcus aeolicus (strain ATCC BAA-1280 / DSM 17508 / OCM 812 / Nankai-3)", "Methanococcus voltae (strain ATCC BAA-1334 / A3)", "Methanothermococcus okinawensis (strain DSM 14208 / JCM 11175 / IH1)", "Methanocaldococcus jannaschii (strain ATCC 43067 / DSM 2661 / JAL-1 / JCM 10045 / NBRC 100440)", "Methanocaldococcus infernus (strain DSM 11812 / JCM 15783 / ME)", "Methanocaldococcus fervens (strain DSM 4213 / JCM 15782 / AG86)", "Methanocaldococcus vulcanius (strain ATCC 700851 / DSM 12094 / M7)", "Methanocaldococcus sp. (strain FS406-22)", "Methanotorris igneus (strain DSM 5666 / JCM 11834 / Kol 5)", "Halobacterium salinarum (strain ATCC 700922 / JCM 11081 / NRC-1)", "Halobacterium salinarum (strain ATCC 29341 / DSM 671 / R1)", "Halalkalicoccus jeotgali (strain DSM 18796 / CECT 7217 / JCM 14584 / KCTC 4019 / B3)", "Haloarcula hispanica (strain ATCC 33960 / DSM 4426 / JCM 8911 / NBRC 102182 / NCIMB 2187 / VKM B-1755)", "Haloarcula marismortui (strain ATCC 43049 / DSM 3752 / JCM 8966 / VKM B-1809)", "Natronomonas pharaonis (strain ATCC 35678 / DSM 2160 / CIP 103997 / NBRC 14720 / NCIMB 2260 / Gabara)", "Natronomonas moolapensis (strain DSM 18674 / JCM 14361 / 8.8.11)", "Halorhabdus utahensis (strain DSM 12940 / JCM 11049 / AX-2)", "Halomicrobium mukohataei (strain ATCC 700874 / DSM 12286 / JCM 9738 / NCIMB 13541)", "Halorubrum lacusprofundi (strain ATCC 49239 / DSM 5036 / JCM 8891 / ACAM 34)", "Haloferax mediterranei (strain ATCC 33500 / DSM 1411 / JCM 8866 / NBRC 14739 / NCIMB 2177 / R-4)", "Haloferax volcanii (strain ATCC 29605 / DSM 3757 / JCM 8879 / NBRC 14742 / NCIMB 2012 / VKM B-1768 / DS2)", "Halogeometricum borinquense (strain ATCC 700274 / DSM 11551 / JCM 10706 / PR3)", "Haloquadratum walsbyi (strain DSM 16790 / HBSQ001)", "Haloquadratum walsbyi (strain DSM 16854 / JCM 12705 / C23)", "Natrialba asiatica (strain ATCC 700177 / DSM 12278 / JCM 9576 / FERM P-10747 / NBRC 102637 / 172P1)", "Natrialba magadii (strain ATCC 43099 / DSM 3394 / CIP 104546 / JCM 8861/ NBRC 102185 / NCIMB 2190 / MS3)", "Natrinema pellirubrum (strain DSM 15624 / CIP 106293 / JCM 10476 / NCIMB 786 / 157)", "Natrinema sp. (strain J7-2)", "Haloterrigena turkmenica (strain ATCC 51198 / DSM 5511 / NCIMB 13204 / VKM B-1734)", "Halovivax ruber (strain DSM 18193 / JCM 13892 / XH-70)", "Halopiger xanaduensis (strain DSM 18323 / JCM 14033 / SH-6)", "Natronobacterium gregoryi (strain ATCC 43098 / DSM 3393 / CCM 3738 / CIP 104747 / JCM 8860 / NBRC 102187 / NCIMB 2189 / SP2)", "Picrophilus torridus (strain ATCC 700027 / DSM 9790 / JCM 10055 / NBRC 100828)", "Thermoplasma acidophilum (strain ATCC 25905 / DSM 1728 / JCM 9062 / NBRC 15155 / AMRC-C165)", "Thermoplasma volcanium (strain ATCC 51530 / DSM 4299 / JCM 9571 / NBRC 15438 / GSS1)", "Thermoplasmatales archaeon (strain BRNA1)", "Methanomassiliicoccus intestinalis (strain Issoire-Mx1)", "Methanomethylophilus alvus (strain Mx1201)", "Pyrococcus furiosus (strain ATCC 43587 / DSM 3638 / JCM 8422 / Vc1)", "Pyrococcus abyssi (strain GE5 / Orsay)", "Pyrococcus horikoshii (strain ATCC 700860 / DSM 12428 / JCM 9974 / NBRC 100139 / OT-3)", "Pyrococcus sp. (strain NA2)", "Pyrococcus yayanosii (strain CH1 / JCM 16557)", "Thermococcus litoralis (strain ATCC 51850 / DSM 5473 / JCM 8560 / NS-C)", "Thermococcus barophilus (strain DSM 11836 / MP)", "Thermococcus sibiricus (strain DSM 12597 / MM 739)", "Thermococcus gammatolerans (strain DSM 15229 / JCM 11827 / EJ3)", "Thermococcus kodakarensis (strain ATCC BAA-918 / JCM 12380 / KOD1)", "Thermococcus onnurineus (strain NA1)", "Thermococcus sp. (strain CGMCC 1.5172 / 4557)", "Archaeoglobus fulgidus (strain ATCC 49558 / VC-16 / DSM 4304 / JCM 9628 / NBRC 100126)", "Archaeoglobus profundus (strain DSM 5631 / JCM 9629 / NBRC 100127 / Av18)", "Archaeoglobus veneficus (strain DSM 11195 / SNP6)", "Ferroglobus placidus (strain DSM 10642 / AEDII12DO)", "Methanopyrus kandleri (strain AV19 / DSM 6324 / JCM 9639 / NBRC 100938)", "Methanoculleus bourgensis (strain ATCC 43281 / DSM 3045 / OCM 15 / MS2)", "Methanoculleus marisnigri (strain ATCC 35101 / DSM 1498 / JR1)", "Methanolacinia petrolearia (strain DSM 11571 / OCM 486 / SEBR 4847)", "Methanocorpusculum labreanum (strain ATCC 43576 / DSM 4855 / Z)", "Methanospirillum hungatei JF-1 (strain ATCC 27890 / DSM 864 / NBRC 100397 / JF-1)", "Methanoregula boonei (strain DSM 21154 / JCM 14090 / 6A8)", "Methanoregula formicica (strain DSM 22288 / NBRC 105244 / SMSP)", "Methanosphaerula palustris (strain ATCC BAA-1556 / DSM 19958 / E1-9c)", "Methanohalophilus mahii (strain ATCC 35705 / DSM 5219 / SLP)", "Methanosarcina barkeri (strain Fusaro / DSM 804)", "Methanosarcina acetivorans (strain ATCC 35395 / DSM 2834 / JCM 12185 / C2A)", "Methanosarcina mazei (strain ATCC BAA-159 / DSM 3647 / Goe1 / Go1 / JCM 11833 / OCM 88)", "Methanococcoides burtonii (strain DSM 6242 / NBRC 107633 / OCM 468 / ACE-M)", "Methanohalobium evestigatum (strain ATCC BAA-1072 / DSM 3721 / NBRC 107634 / OCM 161 / Z-7303)", "Methanomethylovorans hollandica (strain DSM 15978 / NBRC 107637 / DMS1)", "Methanosalsum zhilinae (strain DSM 4017 / NBRC 107636 / OCM 62 / WeN5)", "Methanothrix soehngenii (strain ATCC 5969 / DSM 3671 / JCM 10134 / NBRC 103675 / OCM 69 / GP-6)", "Methanosaeta harundinacea (strain 6Ac)", "Methanothrix thermoacetophila (strain DSM 6194 / JCM 14653 / NBRC 101360 / PT)", "Methanocella paludicola (strain DSM 17711 / JCM 13418 / NBRC 101707 / SANAE)", "Methanocella conradii (strain DSM 24694 / JCM 17849 / CGMCC 1.5162 / HZ254)", "Methanocella arvoryzae (strain DSM 22066 / NBRC 105507 / MRE50)", "Aciduliprofundum boonei (strain DSM 19572 / T469)", "Aciduliprofundum sp. (strain MAR08-339)", "Nanosalinarum sp. (strain J07AB56)", "Nanosalina sp. (strain J07AB43)", "Haloredivivus sp. (strain G17)", "Archaeon GW2011_AR5", "Archaeon GW2011_AR10", "Archaeon GW2011_AR15", "Archaeon GW2011_AR20", "Korarchaeum cryptofilum (strain OPF8)", "Nanobsidianus stetteri", "Nanoarchaeum equitans (strain Kin4-M)", "Nitrosopumilus maritimus (strain SCM1)", "Cenarchaeum symbiosum (strain A)", "Nitrososphaera gargensis (strain Ga9.2)", "Lokiarchaeota archaeon (strain CR_4)", "Thorarchaeota archaeon (strain OWC)", "Heimdallarchaeota archaeon (strain B3-JM-08)", "Chondrus crispus", "Cyanidioschyzon merolae (strain 10D)", "Cyanidioschyzon merolae", "Galdieria sulphuraria", "Guillardia theta", "Trichomonas vaginalis", "Naegleria gruberi", "Chlamydomonas reinhardtii", "Volvox carteri", "Chlorella variabilis", "Micromonas commoda (strain RCC299 / NOUM17 / CCMP2709)", "Micromonas pusilla (strain CCMP1545)", "Ostreococcus tauri", "Ostreococcus lucimarinus (strain CCE9901)", "Klebsormidium flaccidum", "Marchantia polymorpha", "Physcomitrella patens subsp. patens", "Amborella trichopoda", "Zostera marina", "Setaria italica", "Zea mays", "Sorghum bicolor", "Eragrostis tef", "Oryza longistaminata", "Oryza rufipogon", "Oryza nivara", "Oryza sativa subsp. indica", "Oryza sativa subsp. japonica", "Oryza brachyantha", "Oryza punctata", "Oryza glaberrima", "Brachypodium distachyon", "Hordeum vulgare subsp. vulgare", "Aegilops tauschii", "Triticum aestivum", "Triticum urartu", "Musa acuminata subsp. malaccensis", "Chenopodium quinoa", "Daucus carota subsp. sativus", "Helianthus annuus", "Solanum tuberosum", "Solanum lycopersicum", "Nicotiana tabacum", "Nicotiana attenuata", "Vitis vinifera", "Populus trichocarpa", "Manihot esculenta", "Prunus persica", "Cucumis sativus", "Lupinus angustifolius", "Lotus japonicus", "Medicago truncatula", "Glycine max", "Phaseolus vulgaris", "Phaseolus angularis", "Arabidopsis thaliana", "Arabidopsis lyrata", "Arabis alpina", "Brassica napus", "Brassica rapa subsp. pekinensis", "Brassica oleracea", "Gossypium hirsutum", "Gossypium arboreum", "Gossypium raimondii", "Corchorus capsularis", "Theobroma cacao", "Picea glauca", "Picea sitchensis", "Pinus taeda", "Selaginella moellendorffii", "Spizellomyces punctatus", "Batrachochytrium dendrobatidis (strain JAM81 / FGSC 10211)", "Batrachochytrium dendrobatidis", "Nosema ceranae (strain BRL01)", "Encephalitozoon cuniculi (strain GB-M1)", "Vavraia culicis (isolate floridensis)", "Phycomyces blakesleeanus", "Mucor circinelloides", "Rhizopus oryzae", "Schizosaccharomyces japonicus (strain yFS275 / FY16936)", "Schizosaccharomyces octosporus (strain yFS286)", "Schizosaccharomyces pombe (strain 972 / ATCC 24843)", "Schizosaccharomyces cryophilus (strain OY26 / ATCC MYA-4695 / CBS 11777 / NBRC 106824 / NRRL Y48691)", "Saitoella complicata (strain BCRC 22490 / CBS 7301 / JCM 7358 / NBRC 10748 / NRRL Y-17804)", "Kluyveromyces lactis (strain ATCC 8585 / CBS 2359 / DSM 70799 / NBRC 1267 / NRRL Y-1140 / WM37)", "Saccharomyces cerevisiae (strain ATCC 204508 / S288c)", "Saccharomyces cerevisiae (strain AWRI796)", "Saccharomyces cerevisiae (strain VIN 13)", "Saccharomyces cerevisiae (strain FostersO)", "Zygosaccharomyces rouxii", "Ashbya gossypii (strain ATCC 10895 / CBS 109.51 / FGSC 9923 / NRRL Y-1056)", "Kazachstania naganishii (strain ATCC MYA-139 / BCRC 22969 / CBS 8797 / CCRC 22969 / KCTC 17520 / NBRC 10181 / NCYC 3082)", "Lachancea thermotolerans (strain ATCC 56472 / CBS 6340 / NRRL Y-8284)", "Candida glabrata (strain ATCC 2001 / CBS 138 / JCM 3761 / NBRC 0622 / NRRL Y-65)", "Vanderwaltozyma polyspora (strain ATCC 22028 / DSM 70294)", "Yarrowia lipolytica (strain CLIB 122 / E 150)", "Cyberlindnera fabianii", "Cyberlindnera jadinii (strain ATCC 18201 / CBS 1600 / CCRC 20928 / JCM 3617 / NBRC 0987 / NRRL Y-1542)", "Komagataella phaffii (strain GS115 / ATCC 20864)", "Debaryomyces hansenii (strain ATCC 36239 / CBS 767 / JCM 1990 / NBRC 0083 / IGC 2968)", "Spathaspora passalidarum (strain NRRL Y-27907 / 11-Y1)", "Pichia sorbitophila (strain ATCC MYA-4447 / BCRC 22081 / CBS 7064 / NBRC 10061 / NRRL Y-12695)", "Meyerozyma guilliermondii (strain ATCC 6260 / CBS 566 / DSM 6381 / JCM 1539 / NBRC 10279 / NRRL Y-324)", "Scheffersomyces stipitis (strain ATCC 58785 / CBS 6054 / NBRC 10063 / NRRL Y-11545)", "Candida albicans (strain SC5314 / ATCC MYA-2876)", "Candida albicans (strain WO-1)", "Lodderomyces elongisporus (strain ATCC 11503 / CBS 2605 / JCM 1781 / NBRC 1676 / NRRL YB-4239)", "Candida tenuis", "Dekkera bruxellensis", "Ogataea parapolymorpha (strain ATCC 26012 / BCRC 20466 / JCM 22074 / NRRL Y-7560 / DL-1)", "Pyronema omphalodes (strain CBS 100304)", "Tuber melanosporum (strain Mel28)", "Arthrobotrys oligospora (strain ATCC 24927 / CBS 115.81 / DSM 1491)", "Talaromyces stipitatus (strain ATCC 10500 / CBS 375.48 / QM 6759 / NRRL 1006)", "Aspergillus aculeatus", "Aspergillus clavatus (strain ATCC 1007 / CBS 513.65 / DSM 816 / NCTC 3887 / NRRL 1)", "Aspergillus flavus (strain ATCC 200026 / FGSC A1120 / NRRL 3357 / JCM 12722 / SRRC 167)", "Aspergillus oryzae (strain ATCC 42149 / RIB 40)", "Aspergillus terreus (strain NIH 2624 / FGSC A1156)", "Neosartorya fischeri (strain ATCC 1020 / DSM 3700 / CBS 544.65 / FGSC A1164 / JCM 1740 / NRRL 181 / WB 181)", "Aspergillus glaucus", "Emericella nidulans (strain FGSC A4 / ATCC 38163 / CBS 112.46 / NRRL 194 / M139)", "Emericella nidulans", "Neosartorya fumigata (strain ATCC MYA-4609 / Af293 / CBS 101355 / FGSC A1100)", "Penicillium italicum", "Penicillium chrysogenum", "Penicillium rubens (strain ATCC 28089 / DSM 1075 / NRRL 1951 / Wisconsin 54-1255)", "Arthroderma benhamiae (strain ATCC MYA-4681 / CBS 112371)", "Coccidioides immitis (strain RS)", "Paracoccidioides lutzii (strain ATCC MYA-826 / Pb01)", "Coniosporium apollinis (strain CBS 100218)", "Aureobasidium pullulans", "Passalora fulva", "Sphaerulina musiva (strain SO2202)", "Dothistroma septosporum (strain NZE10 / CBS 128990)", "Zymoseptoria tritici", "Phaeosphaeria nodorum (strain SN15 / ATCC MYA-4574 / FGSC 10173)", "Phaeosphaeria nodorum", "Cochliobolus lunatus", "Cochliobolus sativus (strain ND90Pr / ATCC 201652)", "Pyrenophora tritici-repentis (strain Pt-1C-BFP)", "Leptosphaeria maculans (strain JN3 / isolate v23.1.3 / race Av1-4-5-6-7-8)", "Blumeria graminis", "Botryotinia fuckeliana (strain B05.10)", "Sclerotinia sclerotiorum (strain ATCC 18683 / 1980 / Ss-1)", "Trichoderma harzianum", "Hypocrea virens (strain Gv29-8 / FGSC 10586)", "Hypocrea jecorina", "Hypocrea atroviridis (strain ATCC 20476 / IMI 206040)", "Nectria haematococca", "Gibberella moniliformis (strain M3125 / FGSC 7600)", "Fusarium oxysporum f. sp. cubense (strain race 1)", "Fusarium oxysporum f. sp. lycopersici (strain 4287 / CBS 123668 / FGSC 9935 / NRRL 34936)", "Gibberella zeae", "Beauveria bassiana", "Cordyceps militaris (strain CM01)", "Colletotrichum graminicola", "Colletotrichum sublineola", "Verticillium dahliae (strain VdLs.17 / ATCC MYA-4575 / FGSC 10137)", "Verticillium dahliae", "Cryphonectria parasitica", "Neurospora crassa (strain ATCC 24698 / 74-OR23-1A / CBS 708.71 / DSM 1257 / FGSC 987)", "Neurospora tetrasperma (strain FGSC 2509 / P0656)", "Thielavia heterothallica", "Magnaporthiopsis poae (strain ATCC 64411 / 73-15)", "Magnaporthe grisea", "Magnaporthe oryzae (strain 70-15 / ATCC MYA-4617 / FGSC 8958)", "Eutypa lata (strain UCR-EL1)", "Pestalotiopsis fici (strain W106-1 / CGMCC3.15140)", "Tremella mesenterica", "Cryptococcus neoformans var. neoformans serotype D (strain JEC21 / ATCC MYA-565)", "Cryptococcus gattii serotype B (strain R265)", "Cryptococcus gattii", "Auricularia subglabra (strain TFB-10046 / SS5)", "Dichomitus squalens (strain LYAD-421)", "Trametes versicolor (strain FP-101664)", "Phanerochaete chrysosporium", "Phlebiopsis gigantea", "Fomitopsis pinicola (strain FP-58527)", "Wolfiporia cocos (strain MD-104)", "Postia placenta (strain ATCC 44394 / Madison 698-R)", "Grifola frondosa", "Fomitiporia mediterranea (strain MF3/22)", "Punctularia strigosozonata (strain HHB-11173)", "Gloeophyllum trabeum", "Heterobasidion annosum", "Stereum hirsutum (strain FP-91666)", "Serendipita indica (strain DSM 11827)", "Schizophyllum commune", "Agaricus bisporus", "Laccaria bicolor", "Coprinopsis cinerea (strain Okayama-7 / 130 / ATCC MYA-4618 / FGSC 9003)", "Coprinopsis cinerea", "Moniliophthora perniciosa (strain FA553 / isolate CP02)", "Coniophora puteana (strain RWD-64-598)", "Microbotryum lychnidis-dioicae (strain p1A1 Lamole / MvSl-1064)", "Rhodotorula graminis (strain WP1)", "Puccinia graminis f. sp. tritici (strain CRL 75-36-700-3 / race SCCL)", "Puccinia graminis", "Mixia osmundae (strain CBS 9802 / IAM 14324 / JCM 22182 / KY 12970)", "Ustilago hordei", "Ustilago maydis (strain 521 / FGSC 9021)", "Malassezia globosa (strain ATCC MYA-4612 / CBS 7966)", "Wallemia sebi", "Wallemia ichthyophaga (strain EXF-994 / CBS 113033)", "Monosiga brevicollis", "Salpingoeca rosetta (strain ATCC 50818 / BSB-021)", "Hydra vulgaris", "Nematostella vectensis", "Thelohanellus kitauei", "Mnemiopsis leidyi", "Schistosoma mansoni", "Schmidtea mediterranea", "Trichinella spiralis", "Brugia malayi", "Onchocerca volvulus", "Loa loa", "Thelazia callipaeda", "Meloidogyne hapla", "Strongyloides ratti", "Pristionchus pacificus", "Caenorhabditis briggsae", "Caenorhabditis elegans", "Caenorhabditis remanei", "Caenorhabditis brenneri", "Caenorhabditis japonica", "Ixodes scapularis", "Tetranychus urticae", "Sarcoptes scabiei", "Strigamia maritima", "Daphnia pulex", "Lepeophtheirus salmonis", "Orchesella cincta", "Folsomia candida", "Rhodnius prolixus", "Acyrthosiphon pisum", "Diaphorina citri", "Pediculus humanus subsp. corporis", "Tribolium castaneum", "Dendroctonus ponderosae", "Anopheles darlingi", "Anopheles gambiae", "Culex quinquefasciatus", "Aedes aegypti", "Culicoides sonorensis", "Megaselia scalaris", "Lucilia cuprina", "Drosophila virilis", "Drosophila mojavensis", "Drosophila willistoni", "Drosophila takahashii", "Drosophila bipectinata", "Drosophila ananassae", "Drosophila elegans", "Drosophila eugracilis", "Drosophila ficusphila", "Drosophila erecta", "Drosophila melanogaster", "Drosophila sechellia", "Drosophila simulans", "Drosophila yakuba", "Drosophila kikkawai", "Drosophila biarmipes", "Drosophila rhopaloa", "Drosophila persimilis", "Drosophila pseudoobscura pseudoobscura", "Drosophila grimshawi", "Nasonia vitripennis", "Apis mellifera", "Bombus impatiens", "Camponotus floridanus", "Solenopsis invicta", "Atta cephalotes", "Linepithema humile", "Ooceraea biroi", "Harpegnathos saltator", "Bombyx mori", "Heliconius melpomene", "Melitaea cinxia", "Danaus plexippus", "Zootermopsis nevadensis", "Hypsibius dujardini", "Capitella sp. 1", "Capitella teleta", "Helobdella robusta", "Crassostrea gigas", "Octopus bimaculoides", "Lottia gigantea", "Lingula unguis", "Strongylocentrotus purpuratus", "Ciona intestinalis", "Ciona savignyi", "Branchiostoma floridae", "Branchiostoma lanceolatum", "Danio rerio", "Astyanax mexicanus", "Pygocentrus nattereri", "Ictalurus punctatus", "Esox lucius", "Gadus morhua", "Hippocampus comes", "Anabas testudineus", "Cynoglossus semilaevis", "Scophthalmus maximus", "Seriola dumerili", "Amphiprion ocellaris", "Oreochromis niloticus", "Haplochromis burtoni", "Neolamprologus brichardi", "Cyprinodon variegatus", "Poecilia formosa", "Xiphophorus maculatus", "Nothobranchius furzeri", "Oryzias latipes", "Oryzias melastigma", "Gasterosteus aculeatus", "Takifugu rubripes", "Tetraodon nigroviridis", "Lepisosteus oculatus", "Latimeria chalumnae", "Xenopus laevis", "Xenopus tropicalis", "Sphenodon punctatus", "Anolis carolinensis", "Pelodiscus sinensis", "Chrysemys picta bellii", "Chelonoidis abingdonii", "Parus major", "Ficedula albicollis", "Serinus canaria", "Taeniopygia guttata", "Junco hyemalis", "Melopsittacus undulatus", "Anas platyrhynchos", "Gallus gallus", "Meleagris gallopavo", "Ornithorhynchus anatinus", "Monodelphis domestica", "Sarcophilus harrisii", "Macropus eugenii", "Phascolarctos cinereus", "Choloepus hoffmanni", "Dasypus novemcinctus", "Echinops telfairi", "Loxodonta africana", "Procavia capensis", "Erinaceus europaeus", "Sorex araneus", "Pteropus vampyrus", "Myotis lucifugus", "Equus caballus", "Equus asinus", "Felis catus", "Canis lupus familiaris", "Vulpes vulpes", "Ursus americanus", "Ursus maritimus", "Ailuropoda melanoleuca", "Mustela putorius furo", "Tursiops truncatus", "Capra hircus", "Ovis aries", "Bos taurus", "Vicugna pacos", "Sus scrofa", "Otolemur garnettii", "Microcebus murinus", "Propithecus coquereli", "Callithrix jacchus", "Saimiri boliviensis boliviensis", "Aotus nancymaae", "Cercocebus atys", "Macaca fascicularis", "Macaca mulatta", "Macaca nemestrina", "Papio anubis", "Mandrillus leucophaeus", "Chlorocebus sabaeus", "Colobus angolensis palliatus", "Rhinopithecus bieti", "Rhinopithecus roxellana", "Pongo abelii", "Gorilla gorilla gorilla", "Pan paniscus", "Pan troglodytes", "Homo sapiens", "Nomascus leucogenys", "Tarsius syrichta", "Tupaia belangeri", "Ochotona princeps", "Oryctolagus cuniculus", "Cavia porcellus", "Cavia aperea", "Chinchilla lanigera", "Octodon degus", "Heterocephalus glaber", "Fukomys damarensis", "Ictidomys tridecemlineatus", "Dipodomys ordii", "Mus musculus", "Rattus norvegicus", "Cricetulus griseus", "Nannospalax galili", "Jaculus jaculus", "Eptatretus burgeri", "Petromyzon marinus", "Trichoplax adhaerens", "Amphimedon queenslandica", "Capsaspora owczarzaki (strain ATCC 30864)", "Creolimax fragrantissima", "Fonticula alba", "Plasmodium berghei (strain Anka)", "Plasmodium yoelii yoelii", "Plasmodium knowlesi (strain H)", "Plasmodium fragile", "Plasmodium malariae", "Plasmodium vivax (strain Salvador I)", "Plasmodium falciparum (isolate NF54)", "Plasmodium falciparum (isolate 3D7)", "Plasmodium falciparum (isolate Dd2)", "Plasmodium falciparum (isolate Palo Alto / Uganda)", "Theileria annulata", "Theileria parva", "Babesia bovis", "Babesia bigemina", "Babesia microti (strain RI)", "Eimeria acervulina", "Eimeria tenella", "Eimeria maxima", "Toxoplasma gondii (strain ATCC 50861 / VEG)", "Toxoplasma gondii", "Hammondia hammondi", "Cryptosporidium parvum (strain Iowa II)", "Cryptosporidium parvum", "Cryptosporidium muris (strain RN66)", "Gregarina niphandrodes", "Stylonychia lemnae", "Ichthyophthirius multifiliis (strain G5)", "Ichthyophthirius multifiliis", "Tetrahymena thermophila (strain SB210)", "Paramecium tetraurelia", "Pseudocohnilembus persalinus", "Perkinsus marinus (strain ATCC 50983 / TXsc)", "Vitrella brassicaformis (strain CCMP3155)", "Thalassiosira oceanica", "Thalassiosira pseudonana", "Phaeodactylum tricornutum (strain CCAP 1055/1)", "Plasmopara halstedii", "Phytophthora infestans (strain T30-4)", "Phytophthora nicotianae", "Phytophthora parasitica (strain INRA-310)", "Phytophthora parasitica", "Phytophthora ramorum", "Phytophthora sojae (strain P6497)", "Hyaloperonospora arabidopsidis (strain Emoy2)", "Saprolegnia parasitica (strain CBS 223.65)", "Nannochloropsis gaditana (strain CCMP526)", "Aureococcus anophagefferens", "Ectocarpus siliculosus", "Blastocystis hominis", "Trypanosoma congolense (strain IL3000)", "Trypanosoma cruzi (strain CL Brener)", "Trypanosoma vivax (strain Y486)", "Trypanosoma brucei brucei (strain 927/4 GUTat10.1)", "Leishmania braziliensis", "Leishmania donovani (strain BPK282A1)", "Leishmania infantum", "Leishmania major", "Leishmania mexicana (strain MHOM/GT/2001/U1103)", "Leptomonas seymouri", "Bodo saltans", "Giardia intestinalis (strain ATCC 50803 / WB clone C6)", "Giardia intestinalis (strain ATCC 50581 / GS clone H7)", "Giardia intestinalis (strain P15)", "Reticulomyxa filosa", "Bigelowiella natans (strain CCMP2755)", "Plasmodiophora brassicae", "Cavenderia fasciculata (strain SH3)", "Polysphondylium pallidum (strain ATCC 26659 / Pp 5 / PN500)", "Dictyostelium purpureum", "Dictyostelium discoideum", "Entamoeba histolytica", "Entamoeba dispar (strain ATCC PRA-260 / SAW760)", "Entamoeba nuttalli (strain P19)", "Emiliania huxleyi"]'

"""
        context.update({ 'tab': 'similar', 'subtab': 'profile', 'sim_data': json.loads(sim_json),'reference': ref_json,  'taxon_region': tax_json, "species": sp_json})

        return context


class HOGSimilarDomain(HOG_Base, TemplateView):
    template_name = "hog_similar_domain.html"

    def get_context_data(self, hog_id, idtype='OMA', **kwargs):
        context = super(HOGSimilarDomain, self).get_context_data(hog_id, **kwargs)


        (fam_row, sim_fams) = utils.db.get_prevalent_domains(context["hog_fam"])

        longest_seq = fam_row['repr_entry_length'] if fam_row is not None else -1
        if fam_row is not None:
            fam_row['repr_entry_omaid'] = utils.db.id_mapper['Oma'].map_entry_nr(fam_row['repr_entry_nr'])

        if sim_fams is not None:
            longest_seq = max(longest_seq, max(sim_fams['ReprEntryLength']))

            # Map entry numbers
            sim_fams['ReprEntryNr'] = sim_fams['ReprEntryNr'].apply(
                utils.db.id_mapper['Oma'].map_entry_nr)

        context.update({#'hog': 'HOG:{:07d}'.format(fam),
                        #'fam_nr': fam,
                        'hog_row': fam_row,
                        'sim_hogs': sim_fams,
                        'longest_seq': longest_seq,
            'tab': 'similar',
            'subtab': 'domain'})
        return context


class HOGSimilarPairwise(HOG_Base, TemplateView):
    template_name = "hog_similar_pairwise.html"

    def get_context_data(self, hog_id, idtype='OMA', **kwargs):
        context = super(HOGSimilarPairwise, self).get_context_data(hog_id, **kwargs)

        members_models = [models.ProteinEntry.from_entry_nr(utils.db, e[0]) for e in context['members']]
        gene_ids = [en.entry_nr for en in members_models]

        # get orthologs of the HOGs members
        gene_outside = []

        for m in members_models:
            vps_raw = sorted(utils.db.get_vpairs(m.entry_nr), key=lambda x: x['RelType'])
            gene_outside += [models.ProteinEntry.from_entry_nr(utils.db, rel[1]) for rel in vps_raw if
                             rel[1] not in gene_ids]


        # count for each HOG orthologs the numbers of relations
        count_HOGs = defaultdict(int)

        for gene in gene_outside:
            if gene.oma_hog != "":
                count_HOGs[gene.oma_hog] += 1

        # sorted the groups by number of orthologous relations
        sorted_HOGs = sorted([(value, key) for (key, value) in count_HOGs.items()], reverse=True)



        context.update({
            'tab': 'similar',
            'subtab': 'pairwise', 'similar_hogs': sorted_HOGs})
        return context


class HOGDomainsJson(HOGSimilarDomain, View):

    json_fields = {'Fam': 'Fam', 'ReprEntryNr': 'ReprEntryNr',
                   'PrevCount': 'PrevCount', 'FamSize': 'FamSize',
                   'sim': 'Similarity', 'TopLevel': 'TopLevel',
                   'Prev': 'PrevFrac'}

    def get(self, request, hog_id, *args, **kwargs):
        context = self.get_context_data(hog_id, **kwargs)
        df = context['sim_hogs']
        df = df[df.Fam != context['hog_row']['fam']]
        if len(df) == 0:  #len(context['sim_hogs']) == 0:
            data = ''
        else:
            data = df[list(self.json_fields.keys())] \
                .rename(columns=self.json_fields) \
                .to_json(orient='records')
        return HttpResponse(data, content_type='application/json')


class HOGviewer(HOG_Base, TemplateView):
    template_name = "hog_ihamviewer.html"
    show_internal_labels = True

    def get_context_data(self, hog_id, idtype='OMA', **kwargs):
        context = super(HOGviewer, self).get_context_data(hog_id,**kwargs)

        entry = models.ProteinEntry(utils.db, utils.db.entry_by_entry_nr(context['members'][0][0]))

        context.update({'tab': 'iham',
                        'entry': entry,
                        })
        try:
            fam_nr = entry.hog_family_nr
            context.update({'fam': {'id': 'HOG:{:07d}'.format(fam_nr)},
                            'show_internal_labels': self.show_internal_labels,
                            })
            if fam_nr == 0:
                context['isSingleton'] = True
        except db.Singleton:
            context['isSingleton'] = True
        return context


class HOGtable(HOG_Base, TemplateView):
    template_name = "hog_table.html"

    def get_context_data(self, hog_id, **kwargs):
        context = super(HOGtable, self).get_context_data(hog_id, **kwargs)
        context.update({'tab': 'table', 'api_base': 'hog', 'api_url': '/api/hog/{}/members/'.format(hog_id)})
        return context


#  OLD STUFF

class HOGsBase(ContextMixin, EntryCentricMixin):

    def get_context_data(self, entry_id, level=None, idtype='OMA', **kwargs):
        context = super(HOGsBase, self).get_context_data(**kwargs)
        entry = self.get_entry(entry_id)
        hog_member_entries = []
        hog = None
        levels = []
        try:
            levs_of_fam = frozenset([z.decode() for z in utils.db.hog_levels_of_fam(entry.hog_family_nr)])
            levels = [l for l in itertools.chain(entry.genome.lineage, ('LUCA',))
                      if l.encode('ascii') in utils.tax.all_hog_levels and l in levs_of_fam]
            hog = {'id': entry.oma_hog, 'fam': entry.hog_family_nr}
            if not level is None:
                hog_member_entries = utils.db.hog_members(entry.entry_nr, level)
        except db.Singleton:
            pass
        except ValueError as e:
            raise Http404(str(e))
        except db.InvalidTaxonId:
            logger.error("cannot get NCBI Taxonomy for {} ({})".format(
                entry.genome.uniprot_species_code,
                entry.genome.ncbi_taxon_id))

        hog_members = [models.ProteinEntry(utils.db, e) for e in hog_member_entries]
        nr_vps = utils.db.count_vpairs(entry.entry_nr)
        longest_seq = 0
        if len(hog_member_entries) > 0:
            longest_seq = max(e['SeqBufferLength'] for e in hog_member_entries)
        context.update(
            {'entry': entry,
             'level': level, 'hog_members': hog_members,
             'nr_vps': nr_vps, 'tab': 'hogs', 'levels': levels[::-1],
             'longest_seq': longest_seq,
             'table_data_url': reverse('hog_json', args=(entry.omaid, level)),
             })
        if hog is not None:
            context['hog'] = hog
        return context


class HOGsView(HOGsBase, TemplateView):
    template_name = "hogs.html"


class HOGsJson(HOGsBase, JsonModelMixin, View):
    json_fields = {'omaid': 'protid', 'genome.kingdom': 'kingdom',
                   'genome.species_and_strain_as_dict': 'taxon',
                   'canonicalid': 'xrefid'}

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        data = list(self.to_json_dict(context['hog_members']))
        return JsonResponse(data, safe=False)


class HOGsFastaView(FastaView, HOGsBase):
    def get_fastaheader(self, memb):
        return ' | '.join([memb.omaid, memb.canonicalid, memb.oma_hog, '[{}]'.format(memb.genome.sciname)])

    def render_to_response(self, context, **response_kwargs):
        return self.render_to_fasta_response(context['hog_members'])


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
        response['Access-Control-Allow-Origin'] = '*'
        return response

@method_decorator(never_cache, name='dispatch')
class HOGsMSA(AsyncMsaMixin, HOGsBase, TemplateView):
    template_name = "hog_msa.html"

    def get_context_data(self, entry_id, level, **kwargs):
        context = super(HOGsMSA, self).get_context_data(entry_id, level)
        context.update(self.get_msa_results('hog', context['entry'].entry_nr, level))
        return context


class HOGiHam(EntryCentricMixin, TemplateView):
    template_name = "hog_vis.html"
    show_internal_labels = True

    def get_context_data(self, entry_id, idtype='OMA', **kwargs):
        context = super(HOGiHam, self).get_context_data(**kwargs)
        entry = self.get_entry(entry_id)
        context.update({'tab': 'hogs',
                        'entry': entry,
                        })
        try:
            fam_nr = entry.hog_family_nr
            context.update({'fam': {'id': 'HOG:{:07d}'.format(fam_nr)},
                            'show_internal_labels': self.show_internal_labels,
                            })
            if fam_nr == 0:
                context['isSingleton'] = True
        except db.Singleton:
            context['isSingleton'] = True
        return context


class HogVisWithoutInternalLabels(HOGiHam):
    show_internal_labels = False


class HOGDomainsBase(ContextMixin, EntryCentricMixin):
    def get_context_data(self, entry_id, idtype='OMA', **kwargs):
        # TODO: move some of this to misc / a model.
        context = super(HOGDomainsBase, self).get_context_data(**kwargs)
        entry = self.get_entry(entry_id)
        fam = entry.hog_family_nr

        (fam_row, sim_fams) = utils.db.get_prevalent_domains(fam)

        longest_seq = fam_row['repr_entry_length'] if fam_row is not None else -1
        if fam_row is not None:
            fam_row['repr_entry_omaid'] = utils.db.id_mapper['Oma'].map_entry_nr(fam_row['repr_entry_nr'])

        if sim_fams is not None:
            longest_seq = max(longest_seq, max(sim_fams['ReprEntryLength']))

            # Map entry numbers
            sim_fams['ReprEntryNr'] = sim_fams['ReprEntryNr'].apply(
                utils.db.id_mapper['Oma'].map_entry_nr)

        context.update({'entry': entry,
                        'hog': 'HOG:{:07d}'.format(fam),
                        'fam_nr': fam,
                        'hog_row': fam_row,
                        'sim_hogs': sim_fams,
                        'tab': 'hogs',
                        'longest_seq': longest_seq})
        return context


class HOGDomainsView(HOGDomainsBase, TemplateView):
    template_name = "hog-domains.html"


class HOGDomainsJson_old(HOGDomainsBase, View):
    json_fields = {'Fam': 'Fam', 'ReprEntryNr': 'ReprEntryNr',
                   'PrevCount': 'PrevCount', 'FamSize': 'FamSize',
                   'sim': 'Similarity', 'TopLevel': 'TopLevel',
                   'Prev': 'PrevFrac'}

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        df = context['sim_hogs']
        df = df[df.Fam != context['hog_row']['fam']]
        if len(df) == 0:  #len(context['sim_hogs']) == 0:
            data = ''
        else:
            data = df[list(self.json_fields.keys())] \
                .rename(columns=self.json_fields) \
                .to_json(orient='records')
        return HttpResponse(data, content_type='application/json')


def domains_json(request, entry_id):
    # Load the entry and its domains, before forming the JSON to draw client-side.
    entry_nr = utils.id_resolver.resolve(entry_id)
    entry = utils.db.entry_by_entry_nr(int(entry_nr))
    domains = utils.db.get_domains(entry['EntryNr'])
    response = misc.encode_domains_to_dict(entry, domains, utils.domain_source)
    return JsonResponse(response)

# //</editor-fold>

#<editor-fold desc="Static">
@cache_control(max_age=1800)
def home(request):
    n_latest_tweets = 3
    try:
        auth = tweepy.OAuthHandler(settings.TWITTER_CONSUMER_KEY, settings.TWITTER_CONSUMER_SECRET)
        auth.set_access_token(settings.TWITTER_ACCESS_TOKEN, settings.TWITTER_ACCESS_TOKEN_SECRET)

        api = tweepy.API(auth)

        public_tweets = api.user_timeline('@OMABrowser', exclude_replies=True,
                                          trim_user=True, include_rts=False, include_entities=True)
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

    context = {'tweets': tweets,
               'nr_genomes':len(utils.id_mapper['OMA']._genome_keys),
               'nr_proteins':utils.id_resolver.max_entry_nr,
               'nr_groups': utils.db.get_nr_oma_groups(),
               'nr_hogs':utils.db.get_nr_toplevel_hogs(),
               'release': "Oct 2019"
               }
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


def genome_suggestion(request):
    if request.method == 'POST':
        form = forms.GenomeSuggestionFrom(request.POST)
        if form.is_valid():
            logger.info("received valid genome suggestion form")
            data = form.cleaned_data
            subj = "Genome Suggestion {taxon_id} ({name})".format(**data)
            try:
                data.update(misc.genome_info_from_uniprot_rest(data['taxon_id']))
            except Exception:
                logger.warning('Cannot find information about {} at uniprot'.format(data['taxon_id']))
            message = get_template('email_genome_suggestion.html').render(form.cleaned_data)
            for recepient in (data['suggested_from_email'], "contact@omabrowser.org",
                              "alpae+gqwmhtm2ep3kmeqmmrlp@boards.trello.com"):
                sender = data['suggested_from_email'] if recepient != data['suggested_from_email'] else "contact@omabrowser.org"
                msg = EmailMessage(subj, message, to=[recepient], from_email=sender)
                msg.content_subtype = "html"
                msg.send()
            return HttpResponseRedirect(reverse('genome_suggestion_thanks'))
    else:
        form = forms.GenomeSuggestionFrom()
    return render(request, "help_genome_suggestion.html", {'form': form})


class Release(TemplateView):
    template_name = 'explore_release.html'

    def get_context_data(self, **kwargs):
        ctx = super(Release, self).get_context_data(**kwargs)
        ctx.update({'rel_name': utils.db.get_release_name(),
                    'nr_genome': len(utils.id_mapper['OMA']._genome_keys),
                    'nr_proteins': utils.id_resolver.max_entry_nr,
                    'nr_oma_groups': utils.db.get_nr_oma_groups(),
                    'nr_roothogs': utils.db.get_nr_toplevel_hogs(),
                    })
        for grp in ('oma', 'hog'):
            hist = utils.db.group_size_histogram(grp)
            proteins = (hist['Count'] * hist['Size']).sum()
            ctx['nr_protein_in_{}'.format(grp)] = proteins
            ctx['percent_in_{}'.format(grp)] = 100*proteins / ctx['nr_proteins']
        return ctx





def export_marker_genes(request):
    if request.method == 'GET' and 'genomes' in request.GET:
        genomes = request.GET.getlist('genomes')
        min_species_coverage = float(request.GET.get('min_species_coverage', 0.5))
        top_N_genomes = int(request.GET.get('max_nr_markers', 200))
        if top_N_genomes < 0:
            top_N_genomes = None
        if len(genomes) >= 2 and 0 < min_species_coverage <= 1:
            data_id = hashlib.md5(
                    (str(genomes) + str(min_species_coverage) + str(top_N_genomes)).encode('utf-8')
                ).hexdigest()
            try:
                r = FileResult.objects.get(data_hash=data_id)
                do_compute = r.remove_erroneous_or_long_pending()
            except FileResult.DoesNotExist:
                do_compute = True

            if do_compute:
                r = FileResult(data_hash=data_id, result_type='markers', state="pending")
                r.save()
                tasks.export_marker_genes.delay(genomes, data_id, min_species_coverage, top_N_genomes)
            return HttpResponseRedirect(reverse('marker_genes', args=(data_id,)))
    return render(request, "dlOMA_exportMarker.html", context={'max_nr_genomes': 200})


def function_projection(request):
    if request.method == 'POST':
        form = forms.FunctionProjectionUploadForm(request.POST, request.FILES)
        if form.is_valid():
            logger.info("received valid function projection form")
            user_file_info = misc.handle_uploaded_file(request.FILES['file'])
            data_id = hashlib.md5(user_file_info['md5'].encode('utf-8')).hexdigest()
            try:
                r = FileResult.objects.get(data_hash=data_id)
                do_compute = r.remove_erroneous_or_long_pending()
            except FileResult.DoesNotExist:
                do_compute = True

            result_page = reverse('function-projection', args=(data_id,))
            if do_compute:
                r = FileResult(data_hash=data_id, result_type='function_projection', state="pending",
                               name=form.cleaned_data['name'], email=form.cleaned_data['email'])
                r.save()
                tasks.assign_go_function_to_user_sequences.delay(
                    data_id, user_file_info['fname'], tax_limit=None,
                    result_url=request.build_absolute_uri(result_page))
            else:
                os.remove(user_file_info['fname'])

            return HttpResponseRedirect(result_page)
    else:
        form = forms.FunctionProjectionUploadForm()
    return render(request, "tool_function_prediction_upload.html",
                  {'form': form, 'max_upload_size': form.fields['file'].max_upload_size / (2**20)})

@method_decorator(never_cache, name='dispatch')
class AbstractFileResultDownloader(TemplateView):
    reload_frequency = 20

    def get_context_data(self, data_id, **kwargs):
        context = super(AbstractFileResultDownloader, self).get_context_data(**kwargs)
        try:
            result = FileResult.objects.get(data_hash=data_id)
        except FileResult.DoesNotExist:
            raise Http404('Invalid dataset')
        context['file_result'] = result
        context['reload_every_x_sec'] = self.reload_frequency
        return context


class FunctionProjectionResults(AbstractFileResultDownloader):
    template_name = "function_projection_download.html"


class MarkerGenesResults(AbstractFileResultDownloader):
    template_name = "marker_download.html"


class CurrentView(TemplateView):
    template_name = "dlOMA_current.html"
    _re_rel2name = re.compile(r'(?:(?P<scope>[A-Za-z]+).)?(?P<month>[A-Za-z]{3})(?P<year>\d{4})')

    def _get_all_releases_with_downloads(self, prefix_filter='All.'):
        try:
            root = os.environ['DARWIN_BROWSER_SHARE']
        except KeyError:
            logger.warning('Cannot determine root dir for downloads.')
            root = ""
        logger.debug('params for archive search: root={}, prefix_filter={}'.format(root, prefix_filter))
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

    def existing_download_files(self, release):
        root = os.getenv('DARWIN_BROWSER_SHARE', '')
        try:
            download_dir = os.path.join(root, release['id'], "downloads")
        except KeyError:
            # expected to happen if no archive release has been selected yet.
            return []

        if not os.path.isdir(download_dir):
            logger.warning("Download folder for release {} does not exists ({})".format(release, download_dir))
            return []
        return [f for f in os.listdir(download_dir) if os.path.exists(os.path.join(download_dir, f))]

    def get_release_data(self, release):
        relname = utils.db.get_release_name()
        m = self._re_rel2name.match(relname)
        if m is not None:
            res = {'name': "{} {}".format(m.group('month'), m.group('year')),
                   'date': "{}{}".format(m.group('month'), m.group('year')),
                   'id': relname}
        else:
            res = {'id': 'All.' + relname.replace(' ', ''),
                   'date': relname.replace(' ', ''), 'name': relname}
        return res

    def get_context_data(self, release=None, **kwargs):
        context = super(CurrentView, self).get_context_data(**kwargs)
        context['release'] = self.get_release_data(release)
        context['all_releases'] = self._get_all_releases_with_downloads()
        context['release_with_backlinks'] = self._get_previous_releases(context['release'], context['all_releases'])
        context['download_root'] = self.download_root(context)
        context['existing_download_files'] = self.existing_download_files(context['release'])
        return context


class ArchiveView(CurrentView):
    template_name = "dlOMA_archives.html"

    def get_release_data(self, release):
        res = {}
        if release is not None:
            res['id'] = release
            res['name'] = self._name_from_release(release)
            res['date'] = res['name'].replace(' ', '')
        return res

    def download_root(self, context):
        return "/" + context['release'].get('id', '')

# //</editor-fold>

# <editor-fold desc="Dot plot">

# synteny viewer DotPlot
def DotplotViewer(request, g1, g2, chr1, chr2):
    return render(request, 'dotplot_viewer.html', {'genome1': g1, 'genome2': g2, 'chromosome1': chr1, 'chromosome2': chr2})


class ChromosomeJson(JsonModelMixin, View):

    '''
    This json aim to get from a genome the list of chromosome associated to him with their genes
    '''
    json_fields = {'sciname': None}

    def get(self, request, genome, *args, **kwargs):

        genome_obj = models.Genome(utils.db, utils.db.id_mapper['OMA'].genome_from_UniProtCode(genome))
        genomerange = utils.db.id_mapper['OMA'].genome_range(genome)

        data = {'entryoff': genome_obj.entry_nr_offset, 'number_entry': genome_obj.nr_entries,
                'range_start': int(genomerange[0]), 'range_end': int(genomerange[1])}

        chr_with_genes = collections.defaultdict(list)

        for entry_number in range(genomerange[0], genomerange[1]):
            entry = utils.db.entry_by_entry_nr(entry_number)
            chr_with_genes[entry["Chromosome"].decode()].append(entry_number)

        # if all genes from a same chromosome make a continuous range of entry number we could just store for each chr the range index !
        data['list_chr'] = chr_with_genes

        return JsonResponse(data, safe=False)


class HomologsBetweenChromosomePairJson(JsonModelMixin, View):
    '''
    This json aim to contain the list of orthologous pairs between two genomes
    '''

    def get(self, request, org1, org2, chr1, chr2, *args, **kwargs):

        genome1 = models.Genome(utils.db, utils.db.id_mapper['OMA'].identify_genome(org1))
        genome2 = models.Genome(utils.db, utils.db.id_mapper['OMA'].identify_genome(org2))
        tab_name = 'VPairs' if genome1.uniprot_species_code != genome2.uniprot_species_code else 'within'
        rel_tab = utils.db.get_hdf5_handle().get_node('/PairwiseRelation/{}/{}'.format(
            genome1.uniprot_species_code, tab_name))

        data = []
        cpt = 0

        e1, e2 = genome1.chromosomes[chr1][0], genome1.chromosomes[chr1][-1]
        t1, t2 = genome2.chromosomes[chr2][0], genome2.chromosomes[chr2][-1]

        logger.debug("EntryRanges: ({},{}), ({},{})".format(e1, e2, t1, t2))
        for e in rel_tab.where(
                    '(EntryNr1 >= {:d}) & (EntryNr1 <= {:d}) & (EntryNr2 >= {:d}) & (EntryNr2 <= {:d})'
                    .format(e1, e2, t1, t2)):
            rel = models.PairwiseRelation(utils.db, e.fetch_all_fields())

            if rel.entry_1.chromosome == chr1 and rel.entry_2.chromosome == chr2:
                data.append(rel)
                cpt += 1
                if cpt % 100 == 0:
                    logger.debug('processed {} relations'.format(cpt))

        return JsonResponse(data, safe=False)

# //</editor-fold>

#<editor-fold desc="Group Centric">


class OgCentricMixin(object):
    def get_og(self, group_id):
        try:
            og = utils.db.oma_group_metadata(int(group_id))
        except db.InvalidId as e:
            raise Http404(e)
        return models.OmaGroup(utils.db, og)


class GroupBase(ContextMixin, OgCentricMixin):
    def get_context_data(self, group_id, **kwargs):

        context = super(GroupBase, self).get_context_data(**kwargs)
        try:
            og = self.get_og(group_id)
            context['members'] = [utils.ProteinEntry(e) for e in utils.db.oma_group_members(group_id)]
            context.update({'omagroup': og,
                            'nr_member': len(context['members'])})

        except db.InvalidId as e:
            raise Http404(e)
        return context


class OMAGroup_members(TemplateView, GroupBase):
    template_name = "omagroup_members.html"

    def get_context_data(self, group_id, **kwargs):
        context = super(OMAGroup_members, self).get_context_data(group_id, **kwargs)

        context.update(
            {'tab': 'members',
             'table_data_url': reverse('omagroup-json', args=(group_id,)),
            'longest_seq': max([len(z.sequence) for z in context['members']])
        })


        return context


class OMAGroup_similar_profile(TemplateView, GroupBase):
    template_name = "omagroup_similar_profile.html"

    def get_context_data(self, group_id, **kwargs):
        context = super(OMAGroup_similar_profile, self).get_context_data(group_id, **kwargs)

        context.update(
            {'tab': 'similar', 'subtab': 'profile'})

        return context


class OMAGroup_similar_pairwise(TemplateView, GroupBase):
    template_name = "omagroup_similar_pairwise.html"

    def get_context_data(self, group_id, **kwargs):
        context = super(OMAGroup_similar_pairwise, self).get_context_data(group_id, **kwargs)
        gene_ids = [e.entry_nr for e in context['members']]

        # get orthologs of the group members
        gene_outside = []

        for m in context['members']:
            vps_raw = sorted(utils.db.get_vpairs(m.entry_nr), key=lambda x: x['RelType'])
            gene_outside += [models.ProteinEntry.from_entry_nr(utils.db, rel[1]) for rel in vps_raw if rel[1] not in gene_ids ]


        # count for each group orthologs the numbers of relations
        count_groups = defaultdict(int)

        for gene in gene_outside:
            if gene.oma_group > 0 :
                count_groups[gene.oma_group] +=1


        # sorted the groups by number of orthologous relations
        sorted_groups = sorted([(value, key) for (key, value) in count_groups.items()],reverse=True)

        context.update(
            {'tab': 'similar', 'subtab': 'pairwise', 'similar_groups': sorted_groups })

        return context


class OMAGroup_ontology(TemplateView, GroupBase):
    template_name = "omagroup_ontology.html"

    def get_context_data(self, group_id, **kwargs):
        context = super(OMAGroup_ontology, self).get_context_data(group_id, **kwargs)

        context.update(
            {'tab': 'ontology'})

        return context


class OMAGroup_info(TemplateView, GroupBase):
    template_name = "omagroup_info.html"

    def get_context_data(self, group_id, **kwargs):
        context = super(OMAGroup_info, self).get_context_data(group_id, **kwargs)

        context.update(
            {'tab': 'info'})

        return context


class OMAGroupFasta(FastaView, GroupBase):
    def get_fastaheader(self, memb):
        return ' | '.join([memb.omaid, memb.canonicalid, "OMAGroup:{:05d}".format(memb.oma_group),
                           '[{}]'.format(memb.genome.sciname)])

    def render_to_response(self, context):
        return self.render_to_fasta_response(context['members'])


class OMAGroupJson(GroupBase, JsonModelMixin, View):
    json_fields = {'omaid': 'protid', 'genome.kingdom': 'kingdom',
                   'genome.species_and_strain_as_dict': 'taxon',
                   'canonicalid': 'xrefid', 'description': None}

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        data = list(self.to_json_dict(context['members']))
        return JsonResponse(data, safe=False)


class OMAGroup(GroupBase, TemplateView):
    template_name = "omagroup_members.html"

    def get_context_data(self, group_id, **kwargs):
        context = super(OMAGroup, self).get_context_data(group_id, **kwargs)
        grp_nr = context['members'][0].oma_group
        king_comp = collections.defaultdict(int)
        for e in context['members']:
            king_comp[e.genome.kingdom] += 1
        context.update({'kingdom_composition': dict(king_comp),
                        'sub_tab': 'member_list',
                        'table_data_url': reverse('omagroup-json', args=(grp_nr,)),
                        'longest_seq': max([len(z.sequence) for z in context['members']])
                        })
        return context

@method_decorator(never_cache, name='dispatch')
class OMAGroup_align(AsyncMsaMixin, OMAGroup):
    template_name = "omagroup_align.html"

    def get_context_data(self, group_id, **kwargs):
        context = super(OMAGroup_align, self).get_context_data(group_id)
        context.update(self.get_msa_results('og', group_id))
        context.update(
            {'tab': 'align'})
        return context


## TODO: either remove or properly implement the following classes for OMAGroup sub-stuff

class OMAGroupBase(ContextMixin):
    def get_context_data(self, group_id, **kwargs):
        context = super(OMAGroupBase, self).get_context_data(**kwargs)
        try:
            context['members'] = [utils.ProteinEntry(e) for e in utils.db.oma_group_members(group_id)]
            #context.update(utils.db.oma_group_metadata(context['members'][0].oma_group))

        except db.InvalidId as e:
            raise Http404(e)
        return context


class EntryCentricOMAGroup(OMAGroup, EntryCentricMixin):
    template_name = "omagroup_entry.html"

    def get_context_data(self, entry_id, **kwargs):
        entry = self.get_entry(entry_id)
        if entry.oma_group != 0:
            context = super(EntryCentricOMAGroup, self).get_context_data(entry.oma_group, **kwargs)
        else:
            context = {}
        context.update({'entry': entry, 'tab': 'groups',
                        'nr_vps': utils.db.count_vpairs(entry.entry_nr)})
        return context

@method_decorator(never_cache, name='dispatch')
class OMAGroupMSA(AsyncMsaMixin, OMAGroup):
    template_name = "omagroup_msa.html"

    def get_context_data(self, group_id, **kwargs):
        context = super(OMAGroupMSA, self).get_context_data(group_id)
        context.update(self.get_msa_results('og', context['group_nr']))
        context['sub_tab'] = 'msa'
        return context

@method_decorator(never_cache, name='dispatch')
class EntryCentricOMAGroupMSA(OMAGroupMSA, EntryCentricMixin):
    template_name = "omagroup_entry_msa.html"

    def get_context_data(self, entry_id, **kwargs):
        entry = self.get_entry(entry_id)
        if entry.oma_group != 0:
            context = super(EntryCentricOMAGroupMSA, self).get_context_data(entry.oma_group)
        else:
            context = {}
        context.update({'sub_tab': 'msa', 'entry': entry})
        return context


# //</editor-fold>

#<editor-fold desc="Search Widget">


class EntrySearchJson(JsonModelMixin):
    json_fields = {'omaid': 'protid', 'genome.kingdom': 'kingdom',
                   'genome.species_and_strain_as_dict': 'taxon',
                   'canonicalid': 'xrefid', 'oma_group': None,
                   'hog_family_nr': 'roothog', 'xrefs': None,
                   'description': None,
                   "found_by": "found_by",
                   "sequence" : "sequence"}


class GenomeModelJsonMixin(JsonModelMixin):
    json_fields = {'uniprot_species_code': None,
                   "species_and_strain_as_dict": 'sciname',
                   'ncbi_taxon_id': "ncbi",
                   "common_name": None,
                   "nr_entries": "prots", "kingdom": None,
                   "last_modified": None,
                   "found_by": "found_by",
                   "type": "type"}


class GenomesJson(GenomeModelJsonMixin, View):
    def get(self, request, *args, **kwargs):
        genome_key = utils.id_mapper['OMA']._genome_keys
        lg = [models.Genome(utils.db, utils.db.id_mapper['OMA'].genome_table[utils.db.id_mapper['OMA']._entry_off_keys[e - 1]]) for e in genome_key]
        data = list(self.to_json_dict(lg))
        return JsonResponse(data, safe=False)


class HOGSearchJson(JsonModelMixin):

    json_fields = {
        'hog_id': 'group_nr',
        'level': 'level',
        'nr_member_genes': 'size',
        'type':'type',
        'fingerprint': 'fingerprint',
        "found_by": "found_by"}


class FullTextJson(JsonModelMixin, View):
    json_fields = {'omaid': 'protid', 'genome.kingdom': 'kingdom',
                   'genome.species_and_strain_as_dict': 'taxon',
                   'canonicalid': 'xrefid', 'oma_group': None,
                   'hog_family_nr': 'roothog', 'xrefs': None,
                   'description': None}

    def get(self, request, query, *args, **kwargs):

        #data = search_fulltext(query)
        data = list(self.to_json_dict( search_fulltext(query)))
        return JsonResponse(data, safe=False)


def search_fulltext(query):

    terms = shlex.split(query)
    logger.info(terms)
    entry_cands = collections.Counter()
    missing_terms = []

    for term in terms:
        enr = check_term_for_entry_nr(term)
        if len(enr) == 0:
            missing_terms.append(term)
        entry_cands.update(enr)
        logger.info("term: '{}' matched {} entries".format(term, len(enr)))


    if len(entry_cands) == 0:
        return []
    else:
        _, top_cnt = entry_cands.most_common(1)[0]
        candidates = (models.ProteinEntry(utils.db, enr) for enr, cnts in entry_cands.most_common()
                      if cnts >= top_cnt-2)
        candidates = list(itertools.islice(candidates, 0, 1000))
        return candidates

    return []


def check_term_for_entry_nr(term): # todo apply this to general term logic
        try:
            prefix, id_ = term.split(':', maxsplit=1)
            if prefix == "GO":
                return utils.db.entrynrs_with_go_annotation(id_)
            elif prefix == "EC":
                return utils.db.entrynrs_with_ec_annotation(id_)
            elif prefix.lower() in ('cathdb', 'cath', 'gene3d', 'pfam', 'cath/gene3d'):
                return utils.db.entrynrs_with_domain_id(id_)
            elif prefix == "HOG":
                return {e['EntryNr'] for e in utils.db.member_of_hog_id(term)}
            elif prefix.lower() in ('oma', 'omagrp', 'omagroup'):
                return {e['EntryNr'] for e in utils.db.oma_group_members(id_)}
            elif prefix.lower() in ("tax", "ncbitax", "taxid", "species"):
                try:
                    return set([]) ############self._genome_entries_from_taxonomy(utils.db.tax.get_subtaxonomy_rooted_at(id_))
                except ValueError:
                    return set([])
        except ValueError:
            entry_nrs = set()
            try:
                entry_nrs.add(utils.id_resolver.resolve(term))
            except db.AmbiguousID as e:
                entry_nrs.update(e.candidates)
            except db.InvalidId:
                pass

            if len(term) >= 7 and utils.db.seq_search.contains_only_valid_chars(term):
                # check if valid AA sequence
                entry_nrs.update(utils.db.seq_search.exact_search(term))
            return entry_nrs


class Searcher(View):


    _entry_selector = ["id", "sequence"]
    _omagroup_selector = ["groupid", "fingerprint"]
    _hog_selector = ["groupid"]
    _genome_selector = ["name", "taxid"]
    _max_results = 50

    def analyse_search(self, request, type, query):

        terms = shlex.split(query)

        context = {'query': query, 'type': type, 'terms':terms}

        # if specific selector chosen (entry by protId) try to instant redirection if correct query
        if type!='all' and len(terms) == 1:

            data_type = type.split("_")[0]  # Entry, OG, HOG, Genome, Ancestral genome
            selector = [type.split("_")[1]]  # ID, sequence, Fingerprint, etc...

            meth = getattr(self, "search_" + data_type )
            resp = meth(request, terms[0], selector=selector, redirect_valid=True) # deal return if error

            if isinstance(resp,  HttpResponseRedirect):
                return resp

        # Otherwise apply the "All" Strategy with non redundant query

        logger.info("Start Search for '{}' with '{}' selector".format(query, type))

        self.logic_genomes(request, context, terms)

        genome_term = []
        protein_scope = []

        for term in terms:
            try:
                int(term)
                pass
            except ValueError:

                for geno in json.loads(context["data_genome"]):
                    result = re.findall('\\b' + term + '\\b', json.dumps(geno), flags=re.IGNORECASE)
                    if result:
                        genome_term.append(term)
                        try:
                            protein_scope += self._genome_entries_from_taxonomy(utils.db.tax.get_subtaxonomy_rooted_at(geno["ncbi"]))
                        except ValueError:
                            pass

        context["genome_term"] = list(set(genome_term))
        context["protein_scope"] = protein_scope

        pruned_term = [term for term in terms if term not in genome_term]

        self.logic_entry(request, context, pruned_term, scope = protein_scope )
        self.logic_group(request, context, pruned_term)

        context['url_fulltest_entries'] = reverse('fulltext_json', args=(query,))

        return render(request, 'search_test.html', context=context)

    def logic_entry(self,request, context, terms, scope = None):

        logger.info("Start entry search")

        if scope:
            scope=set(scope)

        # store per term information
        search_term_meta = {}
        for term in terms:
            search_term_meta[term] = {'id': 0, 'sequence': 0}

        # for each method to search an entry
        entry_search = {}
        search_entry_meta = {}
        total_search = 0
        union_entry = None


        align_info = []
        align_term = {}
        match= None

        for selector in self._entry_selector:
            raw_results = []

            # for each terms we get the raw results
            for term in terms:
                r, align_data, match = self.search_entry(request,  term, selector=[selector])

                if selector == 'sequence':
                    if align_data:
                        align_info += align_data
                        if match == 'exact':
                            for x in align_data:
                                align_term[x] = term

                if scope:
                    r = scope.intersection(set(r))
                    #r = list(filter(lambda x: x in scope, r))
                raw_results.append(r)
                search_term_meta[term][selector] += len(r)

            # Get the intersection of the raw results
            if raw_results:
                s = set(raw_results[0])
                ss = [set(e) for e in raw_results[1:]]

                if selector == 'id':
                    result = list(s.intersection(*ss))
                    union_entry = list(s.union(*ss))

                else:
                    result = list(s.union(*ss))

                entry_search[selector] = result
                total_search += len(result)
                search_entry_meta[selector] = len(result)
            else:
                entry_search[selector] = []
                total_search += 0
                search_entry_meta[selector] = 0

        search_entry_meta['total'] =  total_search

        # Look for the intersection of sequence with ids if more than one terms
        if len(terms) > 1:
            s1 = set(union_entry)
            s2 = set(entry_search['sequence'])

            entry_search['sequence'] = list(s1.intersection(s2))

        # select the top best 50 results
        sorted_results = []
        for k in sorted(entry_search, key=lambda k: len(entry_search[k])):
            for r in entry_search[k]:
                sorted_results.append([r,k])
        if len(sorted_results) <= 50:
            filtered_entries = sorted_results
        else:
            filtered_entries = sorted_results[:50]

        search_entry_meta['shown'] = len(filtered_entries)

        # encode entry data to json
        start = time.time()
        data_entry =  []
        if match == 'exact':
            align_genes = [x for x in align_info]
        elif match == 'approx':
            align_genes = [x[0] for x in align_info]
        else:
            align_genes = []

        for en in filtered_entries:
            p = models.ProteinEntry.from_entry_nr(utils.db, en[0])
            p.found_by = en[1]

            # if not sequence alignment then remove sequence attribute

            if p.entry_nr in align_genes:
                if match == "exact":

                    term = align_term[p.entry_nr]

                    seq_searcher = utils.db.seq_search
                    seq = seq_searcher._sanitise_seq(term).decode()

                    ali = [m.start() for m in re.finditer(seq, p.sequence)]

                    p.sequence = [{"sequence":p.sequence, 'align': [ali[0], ali[0] + len(term)]} for al in align_info  if al == p.entry_nr][0]

                elif match == 'approx':
                    p.sequence = [{"sequence":p.sequence, 'align': al[1]["alignment"][0][1:2][0]} for al in align_info  if al[0] == p.entry_nr][0]


            else:
                p.sequence = ""
            data_entry.append(p)

        json_encoder = EntrySearchJson()
        context['data_entry'] = json.dumps(json_encoder.as_json(data_entry))
        context['meta_entry'] = search_entry_meta
        context['meta_term_entry'] = search_term_meta
        end = time.time()
        logger.info("Entry json took {} sec for {} entry.".format(start - end, len(data_entry)))

        return

    def logic_group(self,request, context, terms):

        logger.info("Start group search")

        search_group_meta = {}

        # store per term information
        search_term_meta = {}
        for term in terms:
            search_term_meta[term] = {'groupid': 0, 'fingerprint': 0}

        # for each method to search an oma group
        og_search = {}
        total_search_og = 0
        search_og_meta = {}
        for selector in self._omagroup_selector:
            raw_results = []

            # for each terms we get the raw results
            for term in terms:
                r = self.search_group(request, term, selector=[selector])
                raw_results.append(r)
                search_term_meta[term][selector] += len(r)

            # Get the intersection of the raw results
            if raw_results:
                s = set(raw_results[0])
                ss = [set(e) for e in raw_results[1:]]
                inter = list(s.intersection(*ss))

                if len(inter) > 0:
                    toadd = inter

                else:
                    # If intersection is empty take the union
                    toadd = list(s.union(*ss))
            else:
                toadd = []

            og_search[selector] = toadd
            total_search_og += len(toadd)
            search_og_meta[selector] = len(toadd)

        search_og_meta['total'] = total_search_og
        search_og_meta['og_search'] = og_search

        # for each method to search an hog
        hog_search = {}
        search_hog_meta = {}
        total_search_hog = 0

        for selector in self._hog_selector:
            raw_results = []

            # for each terms we get the raw results
            for term in terms:
                r = self.search_hog(request, term, selector=[selector])
                raw_results.append(r)
                search_term_meta[term][selector] += len(r)

            # Get the intersection of the raw results

            if raw_results:
                s = set(raw_results[0])
                ss = [set(e) for e in raw_results[1:]]
                inter = list(s.intersection(*ss))

                if len(inter) > 0:
                    hog_search[selector] = inter
                    total_search_hog += len(inter)
                    search_hog_meta[selector] = len(inter)
                else:
                    # If intersection is empty take the union
                    union = list(s.union(*ss))
                    hog_search[selector] = union

                    total_search_hog += len(union)
                    search_hog_meta[selector] = len(union)
            else:
                hog_search[selector] = []
                total_search_hog += 0
                search_hog_meta[selector] = 0


        search_hog_meta['total'] = total_search_hog
        search_group_meta['total'] = total_search_hog + total_search_og

        # select the top best 50 results in og and hog
        sorted_results_og = []
        for k in sorted(og_search, key=lambda k: len(og_search[k])):
            for r in og_search[k]:
                sorted_results_og.append([r, k])

        sorted_results_hog = []
        for k in sorted(hog_search, key=lambda k: len(hog_search[k])):
            for r in hog_search[k]:
                sorted_results_hog.append([r, k])


        filtered_og = []
        filtered_hog = []

        # Both search overflow -> 25/25
        if len(sorted_results_og) >= 25 and len(sorted_results_hog) >= 25:
            filtered_og = sorted_results_og[:25]
            filtered_hog = sorted_results_hog[:25]
        else:
            # Both don't have enough results
            if len(sorted_results_og) <= 25 and len(sorted_results_hog) <= 25:
                filtered_og = sorted_results_og
                filtered_hog = sorted_results_hog
            # Oma group not enough
            elif len(sorted_results_og) < 25:
                filtered_og = sorted_results_og
                filtered_hog = sorted_results_hog[:len(sorted_results_hog) - len(filtered_og)]
            # HOG not enough
            elif len(sorted_results_hog) < 25:
                filtered_hog = sorted_results_hog
                filtered_og = sorted_results_og[:len(sorted_results_og) - len(filtered_hog)]
        search_og_meta['shown'] = len(filtered_og)
        search_hog_meta['shown'] = len(filtered_hog)
        search_group_meta['shown'] = len(filtered_hog) + len(filtered_og)

        search_group_meta['groupid'] = search_og_meta["groupid"] + search_hog_meta["groupid"]
        search_group_meta['fingerprint'] = search_og_meta["fingerprint"]

        # encode group data to json
        start = time.time()
        json_encoder_hog = HOGSearchJson()

        json_hog = []
        for hd in filtered_hog:
            h = models.HOG(utils.db, hd[0])
            h.fingerprint = None
            h.type = 'HOG'
            h.found_by = hd[1]
            json_hog.append(h)
        json_hog = json_encoder_hog.as_json(json_hog)

        json_og = []
        for ogd in filtered_og:
            og = utils.db.oma_group_metadata(ogd[0])
            og["type"] = 'OMA group'
            og["found_by"] = ogd[1]
            json_og.append(og)

        end = time.time()
        logger.info(
            "Group json took {} sec for {} group.".format(start - end, len(filtered_hog) + len(filtered_og)))

        context['data_group'] = json.dumps(json_hog + json_og)
        context['meta_group'] = search_group_meta
        context['meta_og'] = search_og_meta
        context['meta_hog'] = search_hog_meta
        context['meta_term_group'] = search_term_meta

    def logic_genomes(self,request, context, terms):


        def _add_genomes(genomes,search_data ,total_search, search_meta ):

            search_data[selector] += genomes
            total_search += len(genomes)
            search_meta[selector] = len(genomes)


        logger.info("Start genome search")

        # store general search info
        search_genome_meta = {}

        # store per term information for specificity widget
        search_term_meta = {}
        for term in terms:
            search_term_meta[term] = {select:0 for select in self._genome_selector}
            search_term_meta[term]['taxon'] = 0

        # for each method to search an extant genome store info
        ext_search = {select:[] for select in self._genome_selector}
        search_ext_meta = {select:0 for select in self._genome_selector}
        total_search_ext = 0

        for selector in self._genome_selector:

            # for each terms we get the raw results
            for term in terms:

                r = self.search_genome(request, term, selector=[selector])

                search_term_meta[term][selector] += len(r)

                _add_genomes(r, ext_search, total_search_ext, search_ext_meta)


        # for each method to search a taxon
        taxon_search = {select:[] for select in self._genome_selector}
        search_taxon_meta = {select:0 for select in self._genome_selector}
        total_search_taxon = 0

        for selector in self._genome_selector:


            # for each terms we get the raw results
            for term in terms:
                r = self.search_taxon(request,context,  term, selector=[selector])
                search_term_meta[term][selector] += len(r)
                _add_genomes(r, taxon_search, total_search_taxon, search_taxon_meta)

                for taxo in r:

                    induced_genome = self._genomes_from_taxonomy(
                        utils.db.tax.get_subtaxonomy_rooted_at(taxo['taxid']))

                    for it in induced_genome:
                        it.found_by = 'Ancestral genome'
                        it.type = 'Extant'

                    _add_genomes(induced_genome, ext_search, total_search_ext, search_ext_meta)
                    #search_term_meta[term][selector] += len(induced_genome)
                    search_term_meta[term]["taxon"] += len(induced_genome)

        search_taxon_meta['total'] = total_search_taxon
        search_genome_meta['total'] = total_search_taxon + total_search_ext

        sorted_results_genome = []
        for k in sorted(ext_search, key=lambda k: len(ext_search[k])):
            for r in ext_search[k]:
                sorted_results_genome.append(r)

        sorted_results_taxon = []
        for k in sorted(taxon_search, key=lambda k: len(taxon_search[k])):
            for r in taxon_search[k]:
                sorted_results_taxon.append(r)

        cleaned_genome = []
        seen = []
        for obj in sorted_results_genome:
            if obj.uniprot_species_code not in seen:
                cleaned_genome.append(obj)
                seen.append(obj.uniprot_species_code)

        cleaned_taxon = []
        seen = []
        for obj in sorted_results_taxon:
            if obj['taxid'] not in seen:
                cleaned_taxon.append(obj)
                seen.append(obj['taxid'])

        search_ext_meta['shown'] = len(cleaned_genome)
        search_taxon_meta['shown'] = len(cleaned_taxon)
        search_genome_meta['shown'] = len(cleaned_genome) + len(cleaned_taxon)

        search_genome_meta['name'] = search_ext_meta["name"] + search_taxon_meta["name"]
        search_genome_meta['taxid'] = search_ext_meta["taxid"] + search_taxon_meta["taxid"]

        start = time.time()
        # encode genome data to json

        json_genome = GenomeModelJsonMixin().as_json(cleaned_genome)

        if len(json_genome) < len(cleaned_taxon):
            context['data_genome'] = json.dumps(json_genome + cleaned_taxon)
        else:
            context['data_genome'] = json.dumps( cleaned_taxon + json_genome)

        context['meta_genome'] = search_genome_meta
        context['meta_extant'] = search_ext_meta
        context['meta_term'] = search_term_meta

        context['taxon'] = search_taxon_meta

        end = time.time()
        logger.info(
            "Genome json took {} sec for {} genomes.".format(start - end, len(cleaned_taxon) + len(cleaned_genome)))

    def search_entry(self, request,  query, selector=_entry_selector, redirect_valid=False):

        """
        data = entry found with different selector
        
        
        if selector apply only the search of select
        
        
        if redirect dont return data
        
        """

        data = []

        start = time.time()
        if "id" in selector:
            try:
                entry_nr = utils.id_resolver.resolve(query)

                if redirect_valid:
                    return redirect('pairs', entry_nr)
                else:

                    data.append(entry_nr)

            except db.AmbiguousID as ambiguous:
                logger.info("query {} maps to {} entries".format(query, len(ambiguous.candidates)))
                for entry in ambiguous.candidates:
                    data.append(entry)

            except db.InvalidId as e:
                data += []
        end = time.time()
        logger.info("[{}] Entry id search {}".format(query, start - end))

        start = time.time()
        align_data = None
        match=None
        if "sequence" in selector:

            seq_searcher = utils.db.seq_search
            seq = seq_searcher._sanitise_seq(query)
            if len(seq) >= 5:

                targets = []

                exact_matches = seq_searcher.exact_search(seq,only_full_length=False,is_sanitised=True)

                if len(exact_matches) == 1:
                    if redirect_valid:
                        redirect('pairs', exact_matches[0])


                for enr in exact_matches:
                    data.append(enr)
                    targets.append(enr)

                if len(targets) == 0:

                    approx = seq_searcher.approx_search(seq, is_sanitised=True)
                    for enr, align_results in approx:
                        if align_results['score'] < 50:
                            break
                        data.append(enr)
                    align_data = approx
                    match = 'approx'
                else:
                    align_data = exact_matches
                    match = 'exact'
        end = time.time()
        logger.info("[{}] Entry sequence search {}".format(query, start - end))

        return data, align_data, match

    def search_group(self, request, query, selector=_omagroup_selector, redirect_valid=False):


        def _check_group_number(gn):
            if isinstance(gn, int) and 0 < gn <= utils.db.get_nr_oma_groups():
                return gn
            elif isinstance(gn, numpy.integer):
                return int(gn)
            elif isinstance(gn, (bytes, str)) and gn.isdigit():
                return int(gn)
            return None


        """
        
        :param request: 
        :param query: 
        :param selector: array of restricted search to perform
        :param redirect_valid: if a perfect matched if founded we directly goes to the related page
        :param loaded_entries: array of entries already searched for this query, shortcut all entries search module 
        :return: 
        """

        data = []
        potential_group_nbr = []

        start = time.time()
        if "fingerprint" in selector:

            fingerprint = query

            if isinstance(fingerprint, (bytes, str)):

                if isinstance(fingerprint, str):
                    fingerprint = fingerprint.encode("utf-8")

                if fingerprint != b"n/a":
                    if utils.db.seq_search.contains_only_valid_chars(fingerprint):
                        if len(fingerprint) == 7:

                            group_meta_tab = utils.db.db.get_node("/OmaGroups/MetaData")
                            try:
                                e = next(
                                    group_meta_tab.where("(Fingerprint == {!r})".format(fingerprint))
                                )
                                data.append(int(e["GroupNr"]))

                                nbr = _check_group_number(int(e["GroupNr"]))

                                potential_group_nbr.append(nbr)

                                if nbr != None and redirect_valid:
                                    return redirect('omagroup_members', nbr)

                            except StopIteration:
                                pass
        end = time.time()
        logger.info("[{}] Group fingerprint search {}".format(query, start - end))

        start = time.time()
        if "groupid" in selector:
            nbr = _check_group_number(query)

            if nbr != None and redirect_valid:
                return redirect('omagroup_members', nbr)

            potential_group_nbr.append(nbr)
        end = time.time()
        logger.info("[{}] Group id search {}".format(query, start - end))

        # Check all Ids and add to data correct one:
        for gn in list(set(potential_group_nbr)):
            nbr = _check_group_number(gn)
            if nbr != None:
                data.append(nbr)

        return data

    def search_hog(self, request, query, selector=_hog_selector, redirect_valid=False):

        """

        :param request: 
        :param query: 
        :param selector: array of restricted search to perform
        :param redirect_valid: if a perfect matched if founded we directly goes to the related page
        :param loaded_entries: array of entries already searched for this query, shortcut all entries search module 
        :return: 
        """

        def _check_hog_number(gn):

            try:
                gn = int(gn)

                if 0 < gn <= utils.db.get_nr_toplevel_hogs():
                    return gn

            except ValueError:

                try:
                    return utils.db.parse_hog_id(gn)
                except ValueError:
                    return None

            return None

        data = []
        potential_group_nbr = []

        todo = selector if selector else ["entryid", "groupid", "protsequence"]

        if "groupid" in todo:

            start = time.time()

            hog_nbr = _check_hog_number(query)


            if hog_nbr:
                if redirect_valid:
                    return redirect('hog_viewer',  models.HOG(utils.db, hog_nbr).hog_id)
                potential_group_nbr.append(hog_nbr)

            end = time.time()
            logger.info("[{}] HOG id search".format(query, start - end))

        # Check all Ids and add to data correct one:
        for gn in list(set(potential_group_nbr)):
            nbr = _check_hog_number(gn)
            if nbr:
                data.append(nbr)

        return data

    def search_genome(self, request, query, selector=_genome_selector,redirect_valid=False):


        data = []

        if "name" in selector:

            start = time.time()
            try:

                if len(query) == 5:
                    genome1 = utils.id_mapper['OMA'].genome_from_UniProtCode(query)
                    genome = models.Genome(utils.db, genome1)
                    genome.found_by = 'name'
                    genome.type = 'Extant'
                else:
                    genome1 = utils.id_mapper['OMA'].genome_from_SciName(query)
                    genome = models.Genome(utils.db, genome1)
                    genome.found_by = 'name'
                    genome.type = 'Extant'

                if redirect_valid:
                    return redirect('genome_info', genome1['UniProtSpeciesCode'].decode())

                data.append(genome)

            except db.UnknownSpecies:

                amb_genome =  utils.id_mapper['OMA'].approx_search_genomes(query)

                for genome in amb_genome:
                    genome.found_by = 'name'
                    genome.type = 'Extant'
                    data.append(genome)

            end = time.time()
            logger.info("[{}] genome name search {}".format(query, start - end))


        if "taxid" in selector:

            start = time.time()

            if isinstance(query, int) or query.isdigit():
                try:
                    genome1 = utils.id_mapper['OMA'].genome_from_taxid(query)
                    genome = models.Genome(utils.db, genome1)
                    genome.found_by = 'taxid'
                    genome.type = 'Extant'

                    if redirect_valid:
                        return redirect('genome_info', genome1['UniProtSpeciesCode'].decode())

                    data.append(genome)

                except db.UnknownSpecies:
                    pass

            end = time.time()
            logger.info("[{}] genome taxid search {}".format(query, start - end))


        return data

    def search_taxon(self, request, context, query, selector=_genome_selector,redirect_valid=False):

        url = os.path.join(os.environ['DARWIN_BROWSERDATA_PATH'], 'genomes.json')

        def iterdict(d, search, query, found_by):
            for k, v in d.items():
                for key in selector:
                    if k == key and "children" in d.keys():
                        if str(v).lower() == str(query).lower():
                            search = d
                            if key == 'name':
                                found_by = 'name'

                            elif key == 'taxid':
                                found_by = 'taxid'

                if k == 'children':
                    for c in v:
                        search, found_by = iterdict(c, search, query, found_by)
            return search, found_by

        data = []

        start = time.time()
        search, found_by = iterdict(json.load(open(url, 'r')), False, query, None)
        end = time.time()
        logger.info("[{}] taxon search {}".format(query, start - end))

        if search:

            if redirect_valid:
                return redirect('ancestralgenome_info', search['taxid'])

            search["kingdom"] =  ""
            search["uniprot_species_code"] =  ""
            search["ncbi"] =  search["taxid"]
            search["sciname"] =  search["name"]
            search["common_name"] = ""
            search["last_modified"] =  ""
            search["prots"] =  search["nr_hogs"]
            search["type"] =  "Ancestral"
            search["found_by"] = found_by

            data.append(search)

        else:

            if 'name' in selector:

                amb_taxon = utils.taxon_approx_search.search_approx(query)

                for amb_taxa in amb_taxon:

                    query = amb_taxa[1]

                    search, found_by = iterdict(json.load(open(url, 'r')), False, query , None)
                    search["kingdom"] = ""
                    search["uniprot_species_code"] = ""
                    search["ncbi"] = search["taxid"]
                    search["sciname"] = search["name"]
                    search["common_name"] = ""
                    search["last_modified"] = ""
                    search["prots"] = search["nr_hogs"]
                    search["type"] = "Ancestral"
                    search["found_by"] = found_by

                    data.append(search)


        return data

    def get(self, request):

        type = request.GET.get('type', 'id').lower()
        query = request.GET.get('query', '')
        meth = getattr(self, "analyse_search")

        return meth(request, type, query)

    def post(self, request):

        type = request.POST.get('type', 'id').lower()
        query = request.POST.get('query', '')
        meth = getattr(self, "analyse_search")

        return meth(request,type, query)







































    def search_id(self, request, query):
        context = {'query': query, 'search_method': 'id'}
        try:
            entry_nr = utils.id_resolver.resolve(query)
            return redirect('pairs', entry_nr)
        except db.AmbiguousID as ambiguous:
            logger.info("query {} maps to {} entries".format(query, len(ambiguous.candidates)))
            entries = [models.ProteinEntry.from_entry_nr(utils.db, entry) for entry in ambiguous.candidates]
        except db.InvalidId as e:
            entries = []
            context['message'] = "Could not find any protein matching '{}'".format(query)
        context['data'] = json.dumps(EntrySearchJson().as_json(entries))
        return render(request, 'disambiguate_entry.html', context=context)

    def search_group2(self, request, query):
        try:
            group_nr = utils.db.resolve_oma_group(query)
            return redirect('omagroup_members', group_nr)
        except db.AmbiguousID as ambiguous:
            logger.info('search_group results in ambiguous match: {}'.format(ambiguous))
            context = {'query': query, 'search_method': 'group',
                       'data': json.dumps([utils.db.oma_group_metadata(grp) for grp in ambiguous.candidates])}
            return render(request, "disambiguate_group.html", context=context)

    def search_species(self, request, query):
        try:
            species = utils.id_mapper['OMA'].identify_genome(query)
            return redirect('genome_info', species['UniProtSpeciesCode'].decode())
        except db.UnknownSpecies:
            pass
        # search in taxonomy
        try:
            cand_species = self._genomes_from_taxonomy(utils.db.tax.get_subtaxonomy_rooted_at(query))
        except ValueError:
            # here we will only end up if species is ambiguous
            cand_species = utils.id_mapper['OMA'].approx_search_genomes(query)

        context = {'query': query, 'search_method': 'species'}
        if len(cand_species) == 0:
            context['message'] = 'Could not find any species that is similar to your query'
        else:
            context['data'] = json.dumps(GenomeModelJsonMixin().as_json(cand_species))

        return render(request, "disambiguate_species.html", context=context)

    def search_sequence(self, request, query, strategy='mixed'):
        strategy = strategy.lower()[:5]
        if strategy not in ('exact', 'mixed', 'approx'):
            raise ValueError("invalid search strategy parameter")
        seq_searcher = utils.db.seq_search
        seq = seq_searcher._sanitise_seq(query)
        if len(seq) < 5:
            raise ValueError('query sequence is too short')
        context = {'query': seq.decode(), 'search_method': 'sequence'}
        targets = []
        json_encoder = EntrySearchJson()

        if strategy[:5] in ('exact', 'mixed'):
            exact_matches = seq_searcher.exact_search(seq,
                                                      only_full_length=False,
                                                      is_sanitised=True)
            if len(exact_matches) == 1:
                return redirect('entry_info', exact_matches[0])

            context['identified_by'] = 'exact match'
            targets = [models.ProteinEntry.from_entry_nr(utils.db, enr) for enr in exact_matches]

        if strategy == 'approx' or (strategy == 'mixed' and len(targets) == 0):
            approx = seq_searcher.approx_search(seq, is_sanitised=True)
            for enr, align_results in approx:
                if align_results['score'] < 50:
                    break
                protein = models.ProteinEntry.from_entry_nr(utils.db, enr)
                protein.alignment_score = align_results['score']
                protein.alignment = [x[0] for x in align_results['alignment']]
                protein.alignment_range = align_results['alignment'][1][1]
                targets.append(protein)
            json_encoder.json_fields = dict(EntrySearchJson.json_fields)
            json_encoder.json_fields.update({'sequence': None, 'alignment': None,
                                             'alignment_score': None, 'alignment_range': None})
            context['identified_by'] = 'approximate match'
        context['data'] = json.dumps(json_encoder.as_json(targets))
        return render(request, "disambiguate_sequence.html", context=context)

    def _genome_entries_from_taxonomy(self, tax):
        genomes = self._genomes_from_taxonomy(tax)
        return set(enr for enr in itertools.chain.from_iterable(
            range(g.entry_nr_offset+1, g.entry_nr_offset+g.nr_entries+1) for g in genomes))

    def _genomes_from_taxonomy(self, tax):
        taxids = tax.get_taxid_of_extent_genomes()
        if len(tax.genomes) > 0:
            genomes = [tax.genomes[taxid] for taxid in taxids]
        else:
            genomes = [models.Genome(utils.db, utils.db.id_mapper['OMA'].genome_from_taxid(taxid)) for taxid in taxids]
        return genomes



    def search_fulltext2(self, request, query):
        terms = shlex.split(query)
        logger.info(terms)
        entry_cands = collections.Counter()
        species_cands = collections.Counter()
        missing_terms = []
        for term in terms:
            enr = self.check_term_for_entry_nr(term)
            if len(enr) == 0:
                missing_terms.append(term)
            entry_cands.update(enr)
            logger.info("term: '{}' matched {} entries".format(term, len(enr)))
        context = {'query': query, 'tokens': terms, 'missing_terms': missing_terms,
                   'total_candidates': len(entry_cands), 'search_method': 'fulltext'}
        if len(entry_cands) == 0:
            context['message'] = 'Could not find any protein matching your search pattern'
        else:
            _, top_cnt = entry_cands.most_common(1)[0]
            candidates = (models.ProteinEntry(utils.db, enr) for enr, cnts in entry_cands.most_common()
                          if cnts >= top_cnt-2)
            candidates = list(itertools.islice(candidates, 0, 1000))
            context['data'] = json.dumps(EntrySearchJson().as_json(candidates))
            context['total_shown'] = len(candidates)
        return render(request, 'disambiguate_entry.html', context=context)

    def post2(self, request):
        try:
            func = request.POST.get('type', 'id').lower()
            query = request.POST.get('query', '')
            if func not in self._allowed_functions:
                return HttpResponseBadRequest()
            meth = getattr(self, "search_"+func)
            return meth(request, query)
        except ValueError as e:
            return HttpResponseBadRequest(str(e))

# //</editor-fold>
