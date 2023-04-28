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
import sklearn
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
from django.shortcuts import redirect, resolve_url


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
from pyoma.browser.decorators import timethis

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
            entry_nr, is_modif = utils.id_resolver.resolve(entry_id, check_if_modified=True)
        except (db.InvalidId, db.AmbiguousID):
            raise Http404('requested id is unknown')
        entry = utils.db.entry_by_entry_nr(entry_nr)

        # this need to be added to have root level hog id
        model_entry = models.ProteinEntry(utils.db, entry)

        if model_entry.oma_hog:
            model_entry.oma_hog_root = model_entry.oma_hog.split(".")[0]
        else:
            model_entry.oma_hog_root = None

        model_entry.is_modified_xref = entry_id if is_modif else None
        model_entry.query_id = entry_id

        return model_entry

    def get_most_specific_hog(self, entry):
        if not isinstance(entry, models.ProteinEntry):
            entry = self.get_entry(entry)
        most_specific_hog = None
        if entry.oma_hog != "":
            # we want the hog at the first interesting level above the species itself
            level = None
            for level in entry.genome.lineage[1:]:
                if level.encode('utf-8') in utils.tax.all_hog_levels:
                    break
            hog_id = entry.oma_hog
            for _ in range(2):
                try:
                    most_specific_hog = utils.db.get_hog(hog_id, level)
                    break
                except ValueError:
                    i = hog_id.rfind('.')
                    if i >= 0:
                        hog_id = hog_id[:i]
                    else:  # i < 0:
                        # should not happen. we get just the deepest level to make sure
                        # we have something.
                        most_specific_hog = utils.db.get_hog(entry.oma_hog)
                        logger.error("Could not retrieve the most specific hog for entry '{}' (hog_id: {})"
                                     .format(entry.omaid, entry.oma_hog))
                        break
            most_specific_hog = utils.HOG(most_specific_hog)
        return most_specific_hog


# Information
class InfoBase(ContextMixin, EntryCentricMixin):
    def get_context_data(self, entry_id, **kwargs):
        context = super(InfoBase, self).get_context_data(**kwargs)
        entry = self.get_entry(entry_id)

        if entry.is_main_isoform:
            reference_entry= entry
        else:
            #In order to populate pairswise table, badge, link with main isofrma information we replace here
            reference_entry = entry.get_main_isoform()

        nr_ortholog_relations = utils.db.nr_ortholog_relations(reference_entry.entry_nr)
        nr_homoeologs_relations = utils.db.count_homoeologs(reference_entry.entry_nr)


        # get parent genome/hog level
        most_specific_hog = self.get_most_specific_hog(reference_entry)

        context.update({'entry': entry,
                        'reference_entry':reference_entry,
                        'most_specific_hog': most_specific_hog,
                        'tab': 'geneinformation',
                        'nr_homo': nr_homoeologs_relations,
                        'nr_vps': nr_ortholog_relations['NrAnyOrthologs'],
                        'nr_pps':  nr_ortholog_relations['NrHogInducedPWParalogs']})
        return context


class EntryInfoView(InfoBase, TemplateView):
    template_name = "entry_info.html"


class InfoViewFasta(InfoBase, FastaView):
    def get_fastaheader(self, member):
        return " | ".join([member.omaid, member.canonicalid,
                           "[{}]".format(member.genome.sciname)])

    def render_to_response(self, context, **kwargs):
        return self.render_to_fasta_response([context['entry']])


class LocalSyntenyView(InfoBase, TemplateView):
    template_name = "entry_localSynteny.html"

    """loads data to visualize the synteny around a query
    gene and its orthologs.
    the parameter 'mod' is used to keep the color between
    calls on different entries compatible, i.e. they selected
    gene should keep its color.
    the window paramter is used to select the size of the
    neighborhood."""

    def get_context_data(self, entry_id, mod=5, windows=5, **kwargs):
        context = super(LocalSyntenyView, self).get_context_data(entry_id, **kwargs)
        entry = context['reference_entry']
        taxa = entry.genome.lineage
        windows = int(windows)

        ngs_entry_nr, gene_left = utils.db.neighbour_genes(entry.entry_nr, windows)
        positions = list(range(-windows, windows + 1))  # list of intergers for gene positions

        blank_l = windows - gene_left
        blank_r1 = windows + len(ngs_entry_nr) - gene_left
        blank_r2 = 2 * windows + 1

        geneinfos = []
        md_geneinfos = {'genes': {}}  # gene informations for first row, entry gene species
        species = entry.genome.uniprot_species_code  # Species name of the entry gene

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
                "genenumber": "{0:05d}".format(info['EntryNr'] - entry.genome.entry_nr_offset),
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

        vps_entry_nr = utils.db.get_vpairs(entry.entry_nr)
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

        context.update({
            'positions': positions,
            'windows': windows,
            'md': md_geneinfos,
            'o_md': o_md_geneinfos,
            'colors': colors,
            'stripes': stripes,
            'tab': 'synteny',
            'xrefs': xrefs
        })
        return context


# Orthologs
class PairsBase(ContextMixin, EntryCentricMixin):
    """Base class to collect data for pairwise orthologs."""

    _max_entry_to_load = 25

    def get_context_data(self, entry_id, **kwargs):

        context = super(PairsBase, self).get_context_data(**kwargs)
        entry = self.get_entry(entry_id)

        if entry.is_main_isoform:
            reference_entry= entry
        else:
            #In order to populate pairswise table, badge, link with main isofrma information we replace here
            reference_entry = entry.get_main_isoform()

        nr_ortholog_relations = utils.db.nr_ortholog_relations(reference_entry.entry_nr)


        if nr_ortholog_relations['NrAnyOrthologs']  < self._max_entry_to_load:
            load_full_data = 0
            url = reverse('pairs_support_json', args=(reference_entry.omaid,))
        else:
            url = reverse('pairs_support_sample_json', args=(reference_entry.omaid,))
            load_full_data = reverse('pairs_support_json', args=(reference_entry.omaid,))

        nr_homeologs_relations = utils.db.count_homoeologs(reference_entry.entry_nr)

        # get parent genome/hog level
        most_specific_hog = self.get_most_specific_hog(reference_entry)

        context.update(
            {'entry': entry,
             'reference_entry':reference_entry,
             'most_specific_hog': most_specific_hog,
             'nr_pps': nr_ortholog_relations['NrHogInducedPWParalogs'],
             'nr_homo': nr_homeologs_relations,
             'nr_vps': nr_ortholog_relations['NrAnyOrthologs'],
             'tab': 'orthologs',
             'table_data_url': url,
             'load_full_data': load_full_data,
             'sample_size': self._max_entry_to_load,
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

        if entry.is_main_isoform:
            reference_entry= entry
        else:
            #In order to populate pairswise table, badge, link with main isofrma information we replace here
            reference_entry = entry.get_main_isoform()

        nr_ortholog_relations = utils.db.nr_ortholog_relations(reference_entry.entry_nr)

        if nr_ortholog_relations['NrHogInducedPWParalogs'] < self._max_entry_to_load:
            load_full_data = 0
            url = reverse('paralogs_json', args=(reference_entry.omaid,))
        else:
            url = reverse('paralogs_sample_json', args=(reference_entry.omaid,))
            load_full_data = reverse('paralogs_json', args=(reference_entry.omaid,))

        nr_homeologs_relations = utils.db.count_homoeologs(reference_entry.entry_nr)

        # get parent genome/hog level
        most_specific_hog = self.get_most_specific_hog(reference_entry)

        context.update(
            {'entry': entry,
             'reference_entry': reference_entry,
             'most_specific_hog': most_specific_hog,
             'nr_pps': nr_ortholog_relations['NrHogInducedPWParalogs'],
             'nr_vps': nr_ortholog_relations['NrAnyOrthologs'],
             'tab': 'paralogs',
             'nr_homo': nr_homeologs_relations,
             'table_data_url': url,
             'load_full_data': load_full_data,
             'sample_size': self._max_entry_to_load,
             })
        return context


class ParalogsView(TemplateView, ParalogsBase):
    template_name = "entry_paralogy.html"


class ParalogsJson(ParalogsBase, JsonModelMixin, View):

    json_fields = {'omaid': 'protid', 'genome.kingdom': 'kingdom',
                   'genome.uniprot_species_code': 'code',
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
                   'genome.uniprot_species_code': 'code',
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


# Homeologs
class HomeologsBase(ContextMixin, EntryCentricMixin):
    """Base class to collect data for homeologs."""

    _max_entry_to_load = 25

    def get_context_data(self, entry_id, **kwargs):

        context = super(HomeologsBase, self).get_context_data(**kwargs)
        entry = self.get_entry(entry_id)

        if entry.is_main_isoform:
            reference_entry= entry
        else:
            #In order to populate pairswise table, badge, link with main isofrma information we replace here
            reference_entry = entry.get_main_isoform()

        nr_homeologs_relations  = utils.db.count_homoeologs(reference_entry.entry_nr)

        if nr_homeologs_relations < self._max_entry_to_load:
            load_full_data = 0
            url = reverse('homeologs_json', args=(reference_entry.omaid,))
        else:
            url = reverse('homeologs_sample_json', args=(reference_entry.omaid,))
            load_full_data = reverse('homeologs_json', args=(reference_entry.omaid,))

        nr_ortholog_relations = utils.db.nr_ortholog_relations(reference_entry.entry_nr)

        # get parent genome/hog level
        most_specific_hog = self.get_most_specific_hog(reference_entry)

        context.update(
            {'entry': entry,
             'reference_entry':reference_entry,
             'most_specific_hog': most_specific_hog,
             'nr_pps': nr_ortholog_relations['NrHogInducedPWParalogs'],
             'nr_homo': nr_homeologs_relations,
             'nr_vps': nr_ortholog_relations['NrAnyOrthologs'],
             'tab': 'homeologs',
             'table_data_url': url,
             'load_full_data': load_full_data,
             'sample_size': self._max_entry_to_load,
             })

        return context


class HomeologsView(TemplateView, HomeologsBase):
    template_name = "entry_homeologs.html"

class HomeologsJson(HomeologsBase, JsonModelMixin, View):

    json_fields = {'omaid': 'protid', 'genome.kingdom': 'kingdom',
                   'genome.species_and_strain_as_dict': 'taxon',
                   'canonicalid': 'xrefid', 'SyntenyConservationLocal':'conservation', 'Confidence':'confidence'}

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        entry = context['entry']

        pps = []
        for p in utils.db.get_homoeologs(entry.entry_nr):
            pm = models.ProteinEntry.from_entry_nr(utils.db, p[1])
            pm.SyntenyConservationLocal = p["SyntenyConservationLocal"].item()
            pm.Confidence = p["Confidence"].item()
            pps.append(pm)

        start = time.time()
        data = list(self.to_json_dict(pps))
        end = time.time()
        logger.info("[{}] Json formatting {}".format(context['entry'].omaid, end - start))
        return JsonResponse(data, safe=False)


class HomeologsSampleJson(HomeologsBase, JsonModelMixin, View):
        json_fields = {'omaid': 'protid', 'genome.kingdom': 'kingdom',
                       'genome.species_and_strain_as_dict': 'taxon',
                       'canonicalid': 'xrefid', 'SyntenyConservationLocal':'conservation', 'Confidence':'confidence'}

        def get(self, request, *args, **kwargs):
            context = self.get_context_data(**kwargs)
            entry = context['entry']

            pps = []
            for p in utils.db.get_homoeologs(entry.entry_nr):
                pm = models.ProteinEntry.from_entry_nr(utils.db, p[1])
                pm.SyntenyConservationLocal = p["SyntenyConservationLocal"].item()
                pm.Confidence = p["Confidence"].item()
                pps.append(pm)

            if len(pps) > HomeologsBase._max_entry_to_load:
                pps = list(pps)
                pps = pps[0:HomeologsBase._max_entry_to_load]

            data = list(self.to_json_dict(pps))
            return JsonResponse(data, safe=False)


# Isoforms (old before merging with sequences tab)
class Entry_Isoform(TemplateView, InfoBase):
    template_name = "entry_isoform.html"

    def get_context_data(self, entry_id, **kwargs):
        context = super(Entry_Isoform, self).get_context_data(entry_id, **kwargs)
        entry = self.get_entry(entry_id)

        isoforms = entry.alternative_isoforms
        isoforms.append(entry)


        main_isoform = None

        for iso in isoforms:
            if iso.is_main_isoform:
                main_isoform = iso


        context.update(
            {'entry': entry,
             'tab': 'isoform',
             'isoforms': isoforms,
             'main_isoform': main_isoform,
             'table_data_url': reverse('isoforms_json', args=(entry.omaid,))})
        return context



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


# Sequences & Isoforms
class Entry_sequences(TemplateView, InfoBase):

    template_name = "entry_sequences.html"

    def get_context_data(self, entry_id, **kwargs):
        context = super(Entry_sequences, self).get_context_data(entry_id, **kwargs)

        # get the query entry
        entry = self.get_entry(entry_id)

        #Get all isoforms including itself
        isoforms = entry.alternative_isoforms
        isoforms.append(entry)

        main_isoform = None

        for iso in isoforms:
            if iso.is_main_isoform:
                main_isoform = iso


        context.update(
            {'entry': entry,
             'tab': 'sequences',
             'isoforms': isoforms,
             'main_isoform': main_isoform,
             'table_data_url': reverse('isoforms_json', args=(entry.omaid,))})

        return context


class IsoformsJson(Entry_Isoform, JsonModelMixin, View):
    json_fields = {'omaid': 'protid',
                   'cdna': 'cdna',
                   'sequence': 'sequence',
                   'canonicalid': 'xrefid',
                   'sequence_length': 'seqlen',
                   'is_main_isoform': None,
                   'locus_start': 'locus_start',
                   'locus_end': 'locus_end',
                   'exons.as_list_of_dict': 'exons'}


    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        data = list(self.to_json_dict(context['isoforms']))

        return JsonResponse(data, safe=False)


class FamBase(ContextMixin):
    def get_context_data(self, fam, **kwargs):
        context = super(FamBase, self).get_context_data(**kwargs)
        context['fam'] = fam
        return context

    def iter_members(self, fam, start=0, stop=None):
        famhog_id = utils.db.format_hogid(fam)
        return utils.db.iter_members_of_hog_id(famhog_id, start, stop)


class FamBaseFromEntry(ContextMixin, EntryCentricMixin):

    def get_context_data(self, entry_id, start=0, stop=None, **kwargs):
        context = super(FamBaseFromEntry, self).get_context_data(**kwargs)
        entry = self.get_entry(entry_id)
        famhog_id = utils.db.format_hogid(utils.db.hog_family(entry.entry_nr))
        fam_members = list(utils.db.iter_members_of_hog_id(famhog_id, start, stop))
        context.update({'entry': entry, 'fam_members': fam_members})
        genes_to_use = []
        for gene in fam_members:
            genes_to_use.append([gene.entry_nr, gene.omaid])
        return context, genes_to_use, famhog_id


class FamGeneDataJsonFromEntry(FamBaseFromEntry, JsonModelMixin, View):
    json_fields = {'entry_nr': 'id', 'omaid': 'protid', 'sequence_length': None,
                   'genome.species_and_strain_as_dict': 'taxon',
                   'canonicalid': 'xrefid', 'gc_content': None, 'nr_exons': None}


    def get(self, request, entry_id, *args, **kwargs):
        offset = int(request.GET.get('offset', 0))
        limit = request.GET.get('limit', None)
        if limit is not None:
            limit = offset + int(limit)
        entry = self.get_entry(entry_id)
        response_ready = False
        go_sim_computed = False
        try:
            encoded_data = utils.db.get_cached_family_json(entry.hog_family_nr)
            encoded_data = encoded_data.replace("gene_similarity", "similarity")

            if offset == 0 and limit is None:
                response = HttpResponse(content=encoded_data, content_type="application/json")
                response_ready = True
            else:
                data = json.loads(encoded_data)[offset:limit]
                go_sim_computed = True
        except db.DBOutdatedError:
            context, genes_to_use, hog_id = self.get_context_data(entry_id=entry_id, start=offset, stop=limit, **kwargs)
            data = [x for x in self.to_json_dict(context['fam_members'])]

        if not response_ready:
            if not go_sim_computed and len(genes_to_use) < 200:
                go_annots_not_fetched, gene_similarity_vals = utils.db.get_gene_similarities_hog(hog_id)
                for g, gene in enumerate(genes_to_use):
                    if gene[0] in go_annots_not_fetched:
                        data[g].update({'similarity': None})
                    else:
                        data[g].update({'similarity': gene_similarity_vals[gene[0]]})
            response = JsonResponse(data, safe=False)
        response['Access-Control-Allow-Origin'] = '*'
        return response


class InfoView(InfoBase, TemplateView):
    template_name = "entry_info.html"

    def get_context_data(self, entry_id, **kwargs):
        context = super(InfoView, self).get_context_data(entry_id, **kwargs)

        nr_ortholog_relations = utils.db.nr_ortholog_relations(context['entry'].entry_nr)
        context['nr_pps'] = nr_ortholog_relations['NrHogInducedPWParalogs']
        context['nr_vps'] = nr_ortholog_relations['NrAnyOrthologs']
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
            {'entry': entry, 'nr_vps': nr_ortholog_relations['NrAnyOrthologs'],
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
    def get_context_data(self, species_id, **kwargs):
        context = super(GenomeBase, self).get_context_data(**kwargs)
        try:
            genome_obj = models.Genome(utils.db, utils.db.id_mapper['OMA'].genome_from_UniProtCode(species_id))
            meta = utils.db.per_species_metadata_retriever(species_id)
            context['genome'] = genome_obj
            context['genome_meta'] = meta
            context['supported_ancestral_levels'] = set(l.decode() for l in utils.tax.all_hog_levels).intersection(genome_obj.lineage)
        except db.UnknownSpecies as e:
            raise Http404(e)
        return context


class GenomeCentricInfo(GenomeBase, TemplateView):
    template_name = "genome_info.html"

    def get_context_data(self, species_id, **kwargs):
        context = super(GenomeCentricInfo, self).get_context_data(species_id, **kwargs)

        prot_in_group = context['genome_meta'].get_nr_genes_in_group(group_type="OMAGroup")
        prot_in_hogs = context['genome_meta'].get_nr_genes_in_group(group_type="HOG")

        context.update({'tab': 'information', "prot_in_group": prot_in_group, "prot_in_hogs": prot_in_hogs})
        return context


class GenomeCentricGenes(GenomeBase, TemplateView):
    template_name = "genome_genes.html"

    def get_context_data(self, species_id, **kwargs):
        context = super(GenomeCentricGenes, self).get_context_data(species_id, **kwargs)

        context.update({'tab': 'genes', 'api_base': 'genome',
                        'amuse_bouche': '/api/genome/{}/proteins/?&per_page=2500000'.format(species_id),
                        'api_url': '/api/genome/{}/proteins/?&per_page=25'.format(species_id)})
        return context


class GenomeCentricClosestGroups(GenomeBase, TemplateView):
    template_name = "genome_closest_groups.html"

    def get_context_data(self, species_id, **kwargs):
        context = super(GenomeCentricClosestGroups, self).get_context_data(species_id, **kwargs)

        gr_close_raw = context['genome_meta'].get_most_similar_species(limit=10, group_type='OMAGroup')
        gr_close = []
        for g in gr_close_raw:
            gr_close.append({'genome': utils.Genome(utils.db.id_mapper['OMA'].genome_from_UniProtCode(g[0])),
                             'nbr': g[1]})

        gr_least_raw = context['genome_meta'].get_least_similar_species(limit=11, group_type='OMAGroup')
        gr_least = []
        for g in gr_least_raw:
            gr_least.append({'genome': utils.Genome(utils.db.id_mapper['OMA'].genome_from_UniProtCode(g[0])),
                             'nbr': g[1]})

        context.update({'tab': 'closest', 'subtab': 'groups', 'closest': gr_close, 'least': gr_least})
        return context


class GenomeCentricClosestHOGs(GenomeBase, TemplateView):
    template_name = "genome_closest_hogs.html"

    def get_context_data(self, species_id, **kwargs):
        context = super(GenomeCentricClosestHOGs, self).get_context_data(species_id, **kwargs)
        hog_closest_raw = context['genome_meta'].get_most_similar_species(limit=10, group_type='HOG')
        hog_least_raw = context['genome_meta'].get_least_similar_species(limit=10, group_type='HOG')

        hog_closest = []
        for g in hog_closest_raw:
            hog_closest.append({'genome': models.Genome(utils.db, utils.db.id_mapper['OMA'].genome_from_UniProtCode(g[0])), 'nbr': g[1]})

        hog_least = []
        for g in hog_least_raw:
            hog_least.append({'genome': models.Genome(utils.db, utils.db.id_mapper['OMA'].genome_from_UniProtCode(g[0])), 'nbr': g[1]})


        context.update({'tab': 'closest', 'subtab':'hogs', 'closest':hog_closest, 'least':hog_least })
        return context


class GenomeCentricSynteny(GenomeBase, TemplateView):
    template_name = "genome_synteny.html"

    def get_context_data(self, species_id, **kwargs):
        context = super(GenomeCentricSynteny, self).get_context_data(species_id, **kwargs)
        genome_obj = models.Genome(utils.db, utils.db.id_mapper['OMA'].genome_from_UniProtCode(species_id))
        context.update({'tab': 'synteny', 'genome_obj':genome_obj})
        return context

#</editor-fold >

#<editor-fold desc="Ancestral Genome Centric">

class AncestralGenomeBase(ContextMixin):

    def get_context_data(self, species_id, **kwargs):
        context = super(AncestralGenomeBase, self).get_context_data(**kwargs)
        try:
            def iterdict(d, search, query):
                for k, v in d.items():
                    if k == 'taxid' or k == 'name':
                        if str(v).lower() == str(query).lower():
                            search = d
                    if k == 'children':
                        for c in v:
                            search = iterdict(c, search, query)
                return search

            def count_species(d):
                cpt = 0
                try:
                    for child in d['children']:
                        cpt += count_species(child)
                except KeyError:
                    # leaf node
                    cpt = 1
                return cpt

            genomes_json = utils.load_genomes_json_file()
            search = iterdict(genomes_json, False, species_id)
            if search:
                try:
                    context['taxid'] = search['taxid']
                except KeyError:
                    context['taxid'] = 0
                context['genome_name'] = search['name']
                try:
                    context['nr_hogs'] = search['nr_hogs']
                except KeyError:
                    context['nr_hogs'] = len(utils.db.get_all_hogs_at_level(search['name']))
                context['nbr_species'] = count_species(search)
            else:
                raise ValueError("Could not find ancestral genome {}".format(species_id))
        except ValueError as e:
            raise Http404(e)
        return context


class AncestralGenomeCentricInfo(AncestralGenomeBase, TemplateView):
    template_name = "ancestralgenome_info.html"

    def get_context_data(self, species_id, **kwargs):
        context = super(AncestralGenomeCentricInfo, self).get_context_data(species_id, **kwargs)
        if context['taxid'] == 0:
            subtax = utils.tax
        else:
            subtax = utils.tax.get_subtaxonomy_rooted_at(context['taxid'])

        ext_genomes = []
        for taxid in subtax.get_taxid_of_extent_genomes():
            ext_genomes.append(utils.Genome(utils.id_mapper['OMA'].genome_from_taxid(taxid)))
        ext_genomes_json = GenomeModelJsonTableMixin().as_json(ext_genomes)
        context.update({'tab': 'information',
                        'extant_genomes': ext_genomes_json})
        return context


class AncestralGenomeCentricGenes(AncestralGenomeBase, TemplateView):
    template_name = "ancestralgenome_genes.html"

    def get_context_data(self, species_id, level=None, **kwargs):
        context = super(AncestralGenomeCentricGenes, self).get_context_data(species_id, **kwargs)

        ## get list lineage up
        #  get an extant genome lineage
        if context['taxid'] != 0:
            taxid = utils.tax.get_subtaxonomy_rooted_at(context['taxid']).get_taxid_of_extent_genomes()[0]
            extant = utils.Genome(utils.id_mapper['OMA'].genome_from_taxid(taxid))
            full_lineage = extant.lineage

            # cut before current level
            index = full_lineage.index(context['genome_name'])
            lineage = full_lineage[index+1:]
        else:
            lineage = []

        context.update({'tab': 'genes',
                        'level': level,
                        'api_url': '/api/hog/?level={}&per_page=250000'.format(context['genome_name']),
                        'lineage': lineage})
        return context



#</editor-fold >

#<editor-fold desc="HOGs Centric">


def resolve_hog_id(request, hog_id):
    # matches e.g. "HOG:0002124.1a.53bz.2a_4893"
    match = re.match(
        r'(?P<id>HOG:(?P<rel>[A-Z]+)?(?P<fam>\d+)(?:[a-z0-9.]*))(?:_(?P<taxid>\d+))?',
        hog_id
    )
    if match is None:
        raise Http404("Invalid HOG id format: {}".format(hog_id))
    if match.group('taxid') is not None:
        taxid = int(match.group('taxid'))
        if taxid in (0, 131567):
            level = "LUCA"
        else:
            try:
                taxnode = utils.tax.get_taxnode_from_name_or_taxid(taxid)
                level = taxnode[0]['Name'].decode()
            except Exception:
                logger.exception("cannot determine taxon node for {}".format(taxid))
                raise Http404("taxonid {} is unknown in OMA database".format(taxid))
        args = (match.group('id'), level)
    else:
        args = (match.group('id'), )
    return HttpResponseRedirect(reverse('hog_table', args=args))


class HOGBase(ContextMixin):
    def get_context_data(self, hog_id, level=None, only_validate=False, **kwargs):
        context = super(HOGBase, self).get_context_data(**kwargs)
        try:
            # check to verify hog id is correct, raises ValueError if unknown
            hog = utils.HOG(utils.db.get_hog(hog_id, level=level))

            # check if sub hog or not
            if len(hog_id.split('.')) > 1:
                is_subhog = True
            else:
                if hog.is_root:
                    is_subhog = False
                else:
                    is_subhog = True

            logger.debug("hog: {}".format(hog))
            # update context
            context['hog'] = hog
            context['hog_id'] = hog_id
            context['root_id'] = hog_id.split('.')[0]
            context['hog_fam'] = hog.fam
            context['level'] = hog.level
            if hog.level != "LUCA":
                context['taxid'] = utils.tax.get_taxnode_from_name_or_taxid(hog.level)[0]['NCBITaxonId']
            else:
                context['taxid'] = 0
            context['description'] = hog.keyword
            context['is_subhog'] = is_subhog
            context['api_base'] = 'hog'

            if not only_validate:
                lineage_up = utils.db.get_parent_hogs(hog.hog_id, level=hog.level)
                # load only up to 100 subhogs for performance reasons
                subhogs_down = list(itertools.islice(
                    utils.db.get_subhogs(hog_id, level=level, include_subids=True, include_leaf_levels=False),
                    100))

                context['lineage_down'] = subhogs_down
                context['lineage_up'] = lineage_up
                context['rootlevel'] = lineage_up[0].level
        except ValueError as e:
            raise Http404(e)
        return context


class HOGInfo(HOGBase, TemplateView):
    template_name = "hog_info.html"

    def get_context_data(self, hog_id, **kwargs):
        context = super(HOGInfo, self).get_context_data(hog_id, **kwargs)

        hog = context['hog']
        sub_hogs = list(utils.db.get_subhogs(hog.fam, include_subids=True))
        context.update({'tab': 'info', 'sub_hogs': sub_hogs, 'lineage_link_name': 'hog_viewer',})
        return context


class HOGSimilarProfile(HOGBase, TemplateView):
    template_name = "hog_similar_profile.html"

    def get_context_data(self, hog_id, idtype='OMA', **kwargs):
        context = super(HOGSimilarProfile, self).get_context_data(hog_id, **kwargs)
        results = utils.db.get_families_with_similar_hog_profile(context['hog'].fam)
        if len(results.similar.keys()) > 1:
            run_prof = True
        else:
            run_prof = False

        context.update({'tab': 'similar',
                        'subtab': 'profile',
                        'run_prof': run_prof,
                        "sim_hogs": results.jaccard_distance.keys(),
                        'table_data_url': reverse('hog_similar_profile_json', args=(hog_id,)),
                        'lineage_link_name': 'hog_similar_profile',
                        })


        return context


class ProfileJson(HOGSimilarProfile, JsonModelMixin, View):

    def get(self, request, hog_id,  *args, **kwargs):
        context = self.get_context_data(hog_id, **kwargs)
        class NumpyEncoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, numpy.ndarray):
                    return obj.tolist()
                return json.JSONEncoder.default(self, obj)

        fam = context['hog'].fam
        #Get profile from args and sort hogid  according to jaccard
        results = utils.db.get_families_with_similar_hog_profile(fam)
        sortedhogs = [(k, v) for k, v in results.jaccard_distance.items()]
        sortedhogs = sorted(sortedhogs, key=lambda x: x[1])
        sortedhogs = [e[0] for e in sortedhogs]
        sortedhogs.reverse()

        sim_hogs = []
        # we add manually the reference with tag name reference
        if str(fam) in sortedhogs:
            sortedhogs.remove(str(fam))
            p = results.similar[int(fam)].tolist()
            d = models.HOG(utils.db, hog_id).keyword
            sim_hogs.append({"id": "Reference",
                             "profile": p,
                             "jaccard": None,
                             "description": d})
        for sim in sortedhogs[:19]:
            id_hog = utils.db.format_hogid(int(sim))
            sim_hogs.append({"id": sim, "profile": results.similar[int(sim)].tolist(),
                             "jaccard": results.jaccard_distance[sim],
                             "description": models.HOG(utils.db, id_hog).keyword
                             })
        data = {"profile": sim_hogs,
                "tax": results.tax_classes,
                "species": results.species_names,
                }
        return JsonResponse(data, safe=False)


class HOGSimilarDomain(HOGBase, TemplateView):
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

        context.update({'hog_row': fam_row,
                        'sim_hogs': sim_fams,
                        'longest_seq': longest_seq,
                        'tab': 'similar',
                        'subtab': 'domain',
                        'lineage_link_name': 'hog_similar_domain',})
        return context


class HOGSimilarPairwise(HOGBase, TemplateView):
    template_name = "hog_similar_pairwise.html"

    def get_context_data(self, hog_id, idtype='OMA', **kwargs):
        context = super(HOGSimilarPairwise, self).get_context_data(hog_id, **kwargs)

        members_models = context['hog'].members
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


        if len(sorted_HOGs) == 0:
            data = ''
        else:

            data = []
            cpt = 0
            for h in sorted_HOGs:
                cpt += 1
                hog = models.HOG(utils.db, h[1])

                hdata = {"rank": cpt,
                         "HOG ID": hog.hog_id,
                         "nbr_orthologs": h[0],
                         "nbr_members": hog.nr_member_genes,
                         "Description": hog.keyword,
                         }

                data.append(hdata)


        context.update({
            'tab': 'similar',
            'subtab': 'pairwise',
            'similar': data,
            "sim_hogs": sorted_HOGs,
            'lineage_link_name': 'hog_similar_pairwise',
            'similar_hogs': sorted_HOGs})

        return context

class HOGSimilarPairwiseJSON(HOGSimilarPairwise, View):


    def get(self, request, hog_id, *args, **kwargs):
        context = self.get_context_data(hog_id, **kwargs)
        hogs = context['similar_hogs']
        if len(hogs) == 0:
            data = ''
        else:

            data = []
            cpt = 0
            for h in hogs:
                cpt+=1
                hog = models.HOG(utils.db, h[1])

                hdata = {"rank": cpt,
                        "HOG ID": hog.hog_id,
                        "nbr_orthologs": h[0],
                        "nbr_members": hog.nr_member_genes,
                        "Description": hog.keyword,
                        }

                data.append(hdata)

        return JsonResponse(data,safe=False)



class HOGDomainsJson(HOGSimilarDomain, JsonModelMixin, View):

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


class HOGviewer(HOGBase, TemplateView):
    template_name = "hog_ihamviewer.html"
    show_internal_labels = True

    def get_context_data(self, hog_id, idtype='OMA', **kwargs):
        context = super(HOGviewer, self).get_context_data(hog_id, **kwargs)
        one_entry = next(utils.db.iter_members_of_hog_id(context['hog'].hog_id))

        context.update({'tab': 'iham',
                        'entry': one_entry,
                        'lineage_link_name': 'hog_viewer',
                        })
        try:
            context.update({'fam': {'id': 'HOG:{:07d}'.format(context['hog'].fam)},
                            'show_internal_labels': self.show_internal_labels,
                            })
            if context['hog'].fam == 0:
                context['isSingleton'] = True
        except db.Singleton:
            context['isSingleton'] = True
        return context


class HOGtable(HOGBase, TemplateView):
    template_name = "hog_table.html"

    def get_context_data(self, hog_id, **kwargs):
        context = super(HOGtable, self).get_context_data(hog_id, **kwargs)
        hog = context['hog']
        context.update({'tab': 'table',
                        'api_base': 'hog',
                        'api_url': '/api/hog/{}/members/?level={}'.format(hog.hog_id, hog.level),
                        'lineage_link_name': 'hog_table',
                        })
        return context


class HOGFasta(FastaView, HOGBase):
    def get_fastaheader(self, memb):
        return ' | '.join([memb.omaid, memb.canonicalid, memb.oma_hog,
                           '[{}]'.format(memb.genome.sciname)])

    def render_to_response(self, context):
        return self.render_to_fasta_response(context['hog'].members)


class HOGSynteny(HOGBase, TemplateView):
    template_name = "hog_synteny.html"

    def get_context_data(self, hog_id, **kwargs):

        context = super(HOGSynteny, self).get_context_data(hog_id, **kwargs)

        try:
            graph = utils.db.get_syntentic_hogs(hog_id=hog_id, level=context['level'], steps=2)
        except db.DBConsistencyError as e:
            raise Http404(str(e))

        ancestral_synteny = {"nodes": [], "links": []}
        neigh = []

        # Prune the hog neighbor to prevent unreadable graph
        limit_first_radius = 20
        limit_second_radius = 5

        logger.debug("pruning of big graph")
        # get the source hog node
        selected_node = [n for n, v in graph.nodes(data=True) if n == hog_id]
        if len(selected_node) != 1:
            logger.info("Error during graph pruning, {} nodes have been found for {}".format(len(selected_node), hog_id))

        neighbors = [selected_node[0]]
        logger.debug("pruning of big graph: query node found")
        e = graph.edges(selected_node[0], data="weight")
        if len(e) < limit_first_radius:
            limit_first_radius = len(e)
            logger.debug("pruning of big graph:  first radius receive")

        for edge in sorted(e, key=lambda x: x[2], reverse=True)[:limit_first_radius]:
            neighbors.append(edge[1])
            se = graph.edges(edge[1], data="weight")
            logger.debug("pruning of big graph:  second radius receive / {} ".format(limit_first_radius))
            if len(se) < limit_second_radius:
                limit_second_radius = len(se)
            for subedge in sorted( se,key=lambda x: x[2], reverse=True)[:limit_second_radius]:
                neighbors.append(subedge[1])
        graph = graph.subgraph(neighbors)
        logger.debug("pruning of big graph:  done ")

        for n in graph.nodes.data('weight'):
            ancestral_synteny["nodes"].append({"id": n[0], "name": n[0]})
        for e in graph.edges.data('weight'):
            ancestral_synteny["links"].append({"source_id": e[0], "target_id": e[1], "weight": str(e[2])})
            if e[0] == hog_id:
                h = models.HOG(utils.db, e[1])
                neigh.append({'hog': e[1], 'weight': str(e[2]), 'description': h.keyword})
            if e[1] == hog_id:
                h = models.HOG(utils.db, e[0])
                neigh.append({'hog': e[0], 'weight': str(e[2]), 'description': h.keyword})
        logger.debug("data ready to ship ")
        context.update({'tab': 'synteny',
                        'lineage_link_name': 'hog_synteny',
                        'synteny': ancestral_synteny,
                        'neighbor': neigh})
        return context


@method_decorator(never_cache, name='dispatch')
class HOGsMSA(AsyncMsaMixin, HOGBase, TemplateView):
    template_name = "hog_msa.html"

    def get_context_data(self, **kwargs):
        context = super(HOGsMSA, self).get_context_data(**kwargs)
        hog = context['hog']
        context.update(self.get_msa_results('hog', hog.hog_id, hog.level))
        context.update({'lineage_link_name': "hog_msa",
                        "tab": "msa"})
        return context


class HOGsOrthoXMLView(HOGBase, View):
    def get(self, request, file_type=None, **kwargs):
        context = self.get_context_data(only_validate=True, **kwargs)
        augmented = False
        if file_type == 'augmented':
            augmented = True
        try:
            fam = context['hog'].fam
            orthoxml = utils.db.get_orthoxml(fam, augmented=augmented)
        except ValueError as e:
            raise Http404(e.message)
        response = HttpResponse(content_type='text/plain')  #'application/xml')
        response.write(orthoxml)
        response['Access-Control-Allow-Origin'] = '*'
        return response



class HOGtableFromEntry(EntryCentricMixin, View):
    redirect_to = "hog_table"

    def get(self, request, entry_id, level=None, **kwargs):
        entry = self.get_entry(entry_id)
        try:
            if level is not None:
                subhogs = [utils.HOG(h) for h in utils.db.get_subhogs_at_level(entry.hog_family_nr, level)]
                for hog in subhogs:
                    if entry.oma_hog.startswith(hog.hog_id):
                        return redirect(self.redirect_to, hog.hog_id, hog.level)
            else:
                hog = self.get_most_specific_hog(entry)
                if hog is not None:
                    return redirect(self.redirect_to, hog.hog_id, hog.level)
        except db.InvalidId:
            pass
        logger.info("hog for requested entry '{}' ({}) has no hog. redirect to protein info"
                    .format(entry_id, entry.omaid))
        return redirect("pairs", entry_id)


class HOGiHamFromEntry(HOGtableFromEntry):
    redirect_to = "hog_viewer"


# might be needed for external resources (orthoxml by protein entry)
class OrthoXMLFromEntry(EntryCentricMixin, View):
    def get(self, request, entry_id, **kwargs):
        entry = self.get_entry(entry_id)
        if entry.hog_family_nr == 0:
            raise Http404("{} doesn't belong to any HOG".format(entry_id))
        orthoxml = utils.db.get_orthoxml(entry.hog_family_nr)

        response = HttpResponse(content_type='text/plain')  #'application/xml')
        response.write(orthoxml)
        response['Access-Control-Allow-Origin'] = '*'
        return response


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
    tweets = misc.retrieve_last_tweets(3)
    if settings.OMA_INSTANCE_NAME == "full":
        template = "home.html"
    else:
        template = "home-{}.html".format(settings.OMA_INSTANCE_NAME)

    context = {'tweets': tweets,
               'nr_genomes': len(utils.id_mapper['OMA']._genome_keys),
               'nr_proteins': utils.id_resolver.max_entry_nr,
               'nr_groups': utils.db.get_nr_oma_groups(),
               'nr_hogs': utils.db.get_nr_toplevel_hogs(),
               'release': utils.db.get_release_name(),
               'mailinglist_enabled': 'mailman_subscribe' in settings.INSTALLED_APPS,
               }
    return render(request, template, context)


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
    form_cls = forms.FunctionProjectionUploadForm if 'captcha' in settings.INSTALLED_APPS else forms.FunctionProjectionUploadFormBase
    if request.method == 'POST':
        form = form_cls(request.POST, request.FILES)
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
        form = form_cls()
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
        logger.debug("context data: {}".format(context))
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

    len1 = models.Genome(utils.db, utils.db.id_mapper['OMA'].identify_genome(g1)).approx_chromosome_length(chr1)
    len2 = models.Genome(utils.db, utils.db.id_mapper['OMA'].identify_genome(g2)).approx_chromosome_length(chr2)

    return render(request, 'dotplot_viewer.html', {'len_genome1':len1,'len_genome2':len2,   'genome1': g1, 'genome2': g2, 'chromosome1': chr1, 'chromosome2': chr2})


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
            og = utils.db.resolve_oma_group(group_id)
        except db.InvalidId as e:
            try:
                entry_nr = utils.id_resolver.resolve(group_id)
                entry = utils.db.entry_by_entry_nr(entry_nr)
                if entry['OmaGroup'] == 0:
                    raise db.InvalidId("Protein '{}' is not part of any oma group".format(group_id))
                og = entry['OmaGroup']
            except db.AmbiguousID as e:
                group_nrs = {utils.db.entry_by_entry_nr(nr)["OmaGroup"] for nr in e.candidates}
                group_nrs.discard(0)
                if len(group_nrs) == 1:
                    og = int(group_nrs.pop())
                else:
                    raise Http404(str(e))
            except db.InvalidId as e:
                raise Http404(str(e))
        except db.AmbiguousID as e:
            raise Http404(e)
        return models.OmaGroup(utils.db, og)


class GroupBase(ContextMixin, OgCentricMixin):
    def get_context_data(self, group_id, **kwargs):
        context = super(GroupBase, self).get_context_data(**kwargs)
        try:
            og = self.get_og(group_id)
            context.update({'omagroup': og,
                            'nr_member': len(og)})

        except db.InvalidId as e:
            raise Http404(e)
        return context


class OMAGroup_members(TemplateView, GroupBase):
    template_name = "omagroup_members.html"

    def get_context_data(self, group_id, **kwargs):
        context = super(OMAGroup_members, self).get_context_data(group_id, **kwargs)
        grp = context['omagroup']
        context.update({
            'toolbar': True,
            'tab': 'members',
            'table_data_url': reverse('omagroup-json', args=(grp.group_nbr,)),
            'longest_seq': max([len(z) for z in grp.members]),
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
        gene_ids = [e.entry_nr for e in context['omagroup'].members]

        # get orthologs of the group members
        gene_outside = []

        for m in context['members']:
            vps_raw = sorted(utils.db.get_vpairs(m.entry_nr), key=lambda x: x['RelType'])
            gene_outside += [models.ProteinEntry.from_entry_nr(utils.db, rel[1]) for rel in vps_raw if rel[1] not in gene_ids ]


        # count for each group orthologs the numbers of relations
        count_groups = defaultdict(int)

        for gene in gene_outside:
            if gene.oma_group > 0:
                count_groups[gene.oma_group] += 1


        # sorted the groups by number of orthologous relations
        sorted_groups = sorted([(value, key) for (key, value) in count_groups.items()], reverse=True)
        context.update(
            {'tab': 'similar', 'subtab': 'pairwise',
             'similar_groups': sorted_groups})
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
        return self.render_to_fasta_response(context['omagroup'].members)


class OMAGroupJson(GroupBase, JsonModelMixin, View):
    json_fields = {'omaid': 'protid', 'genome.kingdom': 'kingdom',
                   'genome.species_and_strain_as_dict': 'taxon',
                   'canonicalid': 'xrefid', 'description': None}

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        data = list(self.to_json_dict(context['omagroup'].members))
        return JsonResponse(data, safe=False)


class OMAGroup(GroupBase, TemplateView):
    template_name = "omagroup_members.html"

    def get_context_data(self, group_id, **kwargs):
        context = super(OMAGroup, self).get_context_data(group_id, **kwargs)
        grp = context['omagroup']
        king_comp = collections.defaultdict(int)
        for e in grp.members:
            king_comp[e.genome.kingdom] += 1
        context.update({'kingdom_composition': dict(king_comp),
                        'sub_tab': 'member_list',
                        'table_data_url': reverse('omagroup-json', args=(grp.group_nbr,)),
                        'longest_seq': max([len(z) for z in grp.members])
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


class GenomeModelJsonTableMixin(JsonModelMixin):
    json_fields = {'uniprot_species_code': None,
                   "species_and_strain_as_dict": 'sciname',
                   'ncbi_taxon_id': "ncbi",
                   "common_name": None,
                   "nr_entries": "prots", "kingdom": None,
                   "last_modified": None}


class GenomesJson(GenomeModelJsonTableMixin, View):
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
        'type': 'type',
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


    _entry_selector = ["id", "sequence", "crossref"]
    _omagroup_selector = ["groupid", "fingerprint"]
    _hog_selector = ["groupid"]
    _genome_selector = ["name", "taxid"]
    _max_results = 50


    def analyse_search(self, request, type, query):
        if query == "":
            return redirect('home')
        if type.endswith("_sequence"):
            terms = [query]
        else:
            terms = shlex.split(query)

        context = {'query': query, 'type': type, 'terms': terms, "outdated_HOG": False}
        redir = (type != 'all' and len(terms) == 1)

        # if specific selector chosen (entry by protId) try to instant redirection if correct query
        if type != 'all' and len(terms) == 1:

            data_type = type.split("_")[0]  # Entry, OG, HOG, Genome, Ancestral genome
            selector = [type.split("_")[1]]  # ID, sequence, Fingerprint, etc...

            meth = getattr(self, "search_" + data_type)
            logger.debug("calling shortcut {} with query: {}".format(meth, terms[0]))
            resp = meth(request, terms[0], selector=selector, redirect_valid=True)  # deal return if error

            if isinstance(resp, HttpResponseRedirect):
                return resp

        # Otherwise apply the "All" Strategy with non redundant query

        logger.info("Start Search for '{}' with '{}' selector".format(query, type))

        self.logic_genomes(request, context, terms)

        genome_term = []
        protein_scope = []
        genome_term_link = []

        for term in terms:
            try:
                int(term)
                pass
            except ValueError:

                for geno in json.loads(context["data_genome"]):
                    result = re.findall('\\b' + term + '\\b', json.dumps(geno), flags=re.IGNORECASE)
                    if result:
                        genome_term.append(term)
                        if geno["ncbi"]:
                            genome_term_link.append([term,geno["uniprot_species_code"], geno["sciname"]])
                        try:
                            protein_scope += self._genome_entries_from_taxonomy(utils.db.tax.get_subtaxonomy_rooted_at(geno["ncbi"]))

                        except ValueError:
                            pass


        context["genome_term"] = list(set(genome_term))
        context["genome_term_link"] = genome_term_link
        context["protein_scope"] = protein_scope

        pruned_term = [term for term in terms if term not in genome_term]

        self.logic_entry(request, context, pruned_term, scope = protein_scope, redirect_valid=redir )
        self.logic_group(request, context, pruned_term)

        context['url_fulltest_entries'] = reverse('fulltext_json', args=(query,))

        return render(request, 'search_test.html', context=context)

    def logic_entry(self,request, context, terms, scope=None, redirect_valid=False):
        logger.info("Start entry search")
        if scope:
            scope = set(scope)

        # store per term information
        search_term_meta = {}
        for term in terms:
            search_term_meta[term] = {'id': 0, 'sequence': 0, 'crossref': 0}

        # for each method to search an entry
        entry_search = {}
        search_entry_meta = {}
        total_search = 0
        union_entry = None


        @timethis(logging.INFO)
        def search_crossref_and_desc(terms):
            hits_by_entry = collections.defaultdict(list)
            intersect_id = None
            intersect_xref = None

            def update_intersections(iset, add_set):
                if iset is None:
                    return set(add_set)
                else:
                    return iset.intersection(add_set)

            def update_result_dicts(iset, type):
                # lets order the intersection set according to the number of hits
                if iset is None:
                    iset = []
                res = sorted(list(iset), key=lambda id: -len(hits_by_entry[id]))
                entry_search[type] = res
                search_entry_meta[type] = len(res)

            # for each terms we get the raw results
            only_one_term = len(terms) == 1
            for term in terms:
                term_hit_id = set([])
                term_hit_xref = set([])
                # TODO: if only_one_term, then we can limit to fewer results, but need to know
                # how many in total would be found. requires alternative interface for search_id?!
                hits = utils.id_resolver.search_protein(term)
                # filter hits to proteins outside our scope of interest
                if scope:
                    hits = {id: hit for id, hit in hits.items() if id in scope}
                for id, hit in hits.items():
                    for accessor, value in hit.items():
                        hits_by_entry[id].append((term, accessor, value))
                        if accessor == "numeric_id" or accessor == "omaid":
                            term_hit_id.add(id)
                        else:
                            term_hit_xref.add(id)
                search_term_meta[term]["id"] += len(term_hit_id)
                search_term_meta[term]["crossref"] += len(term_hit_xref)
                intersect_id = update_intersections(intersect_id, term_hit_id)
                intersect_xref = update_intersections(intersect_xref, term_hit_xref)
            update_result_dicts(intersect_id, "id")
            update_result_dicts(intersect_xref, "crossref")
            return hits_by_entry

        # search terms in ids and crossrefs,
        # updates entry_search and search_entry_meta
        id_hits_by_entry = search_crossref_and_desc(terms)


        # search by Sequence
        start = time.time()

        raw_hits_seq = []
        align_data = {}

        # for each terms we get the raw results sequence
        for term in terms:
            term_hit_seq = []

            seq_searcher = utils.db.seq_search
            seq = seq_searcher._sanitise_seq(term)
            logger.debug("searching '{}' as sequence: {}".format(term, seq))
            if len(seq) >= 5:
                exact_matches = seq_searcher.exact_search(seq, only_full_length=False, is_sanitised=True)
                logger.debug("found {} exact matches for sequence {}".format(len(exact_matches), seq))
                if len(exact_matches) == 1:
                    if redirect_valid:
                        logger.debug("redirect to pairs page of entry {}".format(exact_matches[0]))
                        redirect('pairs', exact_matches[0])

                if len(exact_matches) == 0:
                    approx = seq_searcher.approx_search(seq, is_sanitised=True)
                    logger.debug("approx search yield {} results".format(len(approx)))
                    for enr, align_results in approx:
                        if align_results['score'] < 50:
                            break
                        term_hit_seq.append(enr)
                        align_results['mode'] = 'approx'
                        align_data[enr] = align_results
                else:
                    term_hit_seq = exact_matches
                    # we put a high score for exact matches, can anyways not be higher with an approx match
                    align_data.update({enr: {'mode': 'exact', 'query': term, 'score': 20000} for enr in exact_matches})

            if scope:
                term_hit_seq = scope.intersection(set(term_hit_seq))
            raw_hits_seq.append(term_hit_seq)
            search_term_meta[term]["sequence"] += len(term_hit_seq)

        # Get the intersection of the raw results sequence
        if raw_hits_seq:
            # TODO: says intersect, but does union...
            s = set(raw_hits_seq[0])
            ss = [set(e) for e in raw_hits_seq[1:]]
            result = list(s.union(*ss))
        else:
            result = []

        entry_search['sequence'] = result
        total_search += len(result)
        search_entry_meta['sequence'] = len(result)
        search_entry_meta['total'] = total_search

        logger.info("Search entry by Sequences took {} sec".format(time.time() - start))

        # Look for the intersection of sequence with ids if more than one terms
        # TODO: does this make sense? I wouldn't thinking len(terms)>1 is correct...
        if len(terms) > 1:
            s1 = set(id_hits_by_entry)
            s2 = set(entry_search['sequence'])
            entry_search['sequence'] = list(s1.intersection(s2))
        # sort sequence search results according to alignment score
        entry_search['sequence'] = sorted(entry_search['sequence'], key=lambda enr: -align_data[enr]['score'])

        # select the top best 50 results
        filtered_entries = []
        for k in sorted(entry_search, key=lambda k: len(entry_search[k])):
            res = entry_search[k]
            if len(res) >= 15:
                res = res[:15]
            for r in res:
                filtered_entries.append([r, k])
        search_entry_meta['shown'] = len(filtered_entries)

        # encode entry data to json
        start = time.time()
        data_entry = []

        for en in filtered_entries:
            p = models.ProteinEntry.from_entry_nr(utils.db, en[0])
            p.found_by = en[1]

            # if not sequence alignment then remove sequence attribute
            if p.entry_nr in align_data:
                al = align_data[p.entry_nr]
                if al['mode'] == "exact":
                    seq_searcher = utils.db.seq_search
                    seq = seq_searcher._sanitise_seq(al['query']).decode()
                    ali = [m.start() for m in re.finditer(seq, p.sequence)]
                    p.sequence = {"sequence": p.sequence, 'align': [ali[0], ali[0] + len(seq)]}
                elif al['mode'] == 'approx':
                    p.sequence = {"sequence": p.sequence, 'align': al['alignment'][0][1]}
            else:
                p.sequence = ""
            data_entry.append(p)

        json_encoder = EntrySearchJson()
        context['data_entry'] = json.dumps(json_encoder.as_json(data_entry))
        context['meta_entry'] = search_entry_meta
        context['meta_term_entry'] = search_term_meta
        logger.info("Entry json took {} sec for {} entry.".format(time.time() - start, len(data_entry)))
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
                try:
                    r = self.search_hog(request, term, selector=[selector])
                except db.OutdatedHogId as exception :

                    try:
                        candidates = utils.hogid_forward_mapper.map_hogid(exception.outdated_hog_id)
                    except AttributeError:
                        candidates = {}

                    new_hogs = []
                    for new_id, jaccard in candidates.items():
                        h = utils.HOG(utils.db.get_hog(new_id))
                        h.jaccard = jaccard
                        h.redirect_url = resolve_url("hog_viewer", h.hog_id)
                        new_hogs.append(h)
                    new_hogs.sort(key=lambda h: -h.jaccard)

                    context["outdated_HOG"] = True
                    context["outdated_hog_id"] = exception.outdated_hog_id.decode()
                    context["candidate_hogs"] = new_hogs

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

            og["size"] = len(models.OmaGroup(utils.db, og))
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

    def logic_genomes(self, request, context, terms):

        def _add_genomes(genomes, search_data, total_search, search_meta):
            search_data[selector] += genomes
            total_search += len(genomes)
            search_meta[selector] = len(genomes)


        logger.info("Start genome search")

        # store general search info
        search_genome_meta = {}

        # store per term information for specificity widget
        search_term_meta = {}
        for term in terms:
            search_term_meta[term] = {select: 0 for select in self._genome_selector}
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
        taxon_search = {select: [] for select in self._genome_selector}
        search_taxon_meta = {select: 0 for select in self._genome_selector}
        total_search_taxon = 0

        for selector in self._genome_selector:

            # for each terms we get the raw results
            for term in terms:
                r = self.search_taxon(request, term, selector=[selector])

                search_term_meta[term][selector] += len(r)
                _add_genomes(r, taxon_search, total_search_taxon, search_taxon_meta)

                for taxo in r:
                    subtax = utils.db.tax
                    if taxo['ncbi'] != 0:
                        subtax = subtax.get_subtaxonomy_rooted_at(taxo['ncbi'])
                    induced_genome = self._genomes_from_taxonomy(subtax)

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
            if obj['ncbi'] not in seen:
                cleaned_taxon.append(obj)
                seen.append(obj['ncbi'])

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
        if "id" in selector or "crossref" in selector:
            try:
                entry_nr = utils.id_resolver.search_protein(query)

                if redirect_valid and len(list(entry_nr.keys()))==1:

                    # check if query is in founded match (e.g if search "DHE5_YEAST" we prefer keep this in url than "12")
                    entry_nr, matches = list(entry_nr.items())[0]
                    original_query = False

                    if len(list(matches.keys()) ) == 1:
                        t,m = list(matches.items())[0]
                        if len(m) == 1:
                            if m[0] == query:
                                original_query = m[0]

                    if original_query is False :
                        return redirect('pairs', list(entry_nr.keys())[0])
                    else:
                        return redirect('pairs', original_query)

                else:
                    for enr in entry_nr.keys():
                        data.append(enr)

            except db.AmbiguousID as ambiguous:
                logger.info("query {} maps to {} entries".format(query, len(ambiguous.candidates)))

                for entry in ambiguous.candidates:
                    pass
                    #data.append(entry)

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
            if nbr is not None and redirect_valid:
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

            except ValueError:

                try:
                    utils.db.get_hog(gn)
                    return gn
                except ValueError:
                    try:
                        gn = utils.db.parse_hog_id(gn)
                    except ValueError:
                        gn = -1

            if 0 < gn <= utils.db.get_nr_toplevel_hogs():
                return gn
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
                logger.info("QUERY HOG: {}".format(query))
                logger.info("QUERY CHECKED: {}".format(hog_nbr))
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

    def search_taxon(self, request, query, selector=_genome_selector, redirect_valid=False):

        def search_in_nested_dict(d, query, result=False, found_by=None):
            if "children" in d:
                for key in selector:
                    try:
                        if str(d[key]).lower() == query:
                            # create flat copy without children if found
                            result = {k: v for k, v in d.items() if k != "children"}
                            found_by = key
                            result = build_result_dict(result, key)
                            break
                    except KeyError:
                        pass
                if not result and found_by is None:
                    # traverse the children recursively
                    for child in d['children']:
                        result, found_by = search_in_nested_dict(child, query)
                        if result and found_by is not None:
                            break
            return result, found_by

        def build_result_dict(sp, found_by):
            res = {
                "kingdom": "",
                "uniprot_species_code": "",
                "sciname": sp['name'],
                "common_name": "",
                "last_modified": "",
                "prots": sp.get("nr_hogs", 0),
                "type": "Ancestral",
                "found_by": found_by
            }
            res.update(sp)
            try:
                res['ncbi'] = sp['taxid']
            except KeyError:
                res['ncbi'] = 0
            return res

        start = time.time()
        query = str(query).lower()
        genomes_json = utils.load_genomes_json_file()
        search_result, found_by = search_in_nested_dict(genomes_json, query)
        end = time.time()
        logger.info("[{}] taxon search {}".format(query, start - end))

        data = []
        if search_result:

            if redirect_valid:
                arg = search_result['taxid'] if 'taxid' in search_result else search_result['sciname']
                return redirect('ancestralgenome_info', arg)
            data.append(search_result)
        else:
            if 'name' in selector:
                amb_taxon = utils.tax.approx_search(query)
                for amb_taxa in amb_taxon:
                    query = str(amb_taxa[1]).lower()
                    search_result, found_by = search_in_nested_dict(genomes_json, query)
                    if search_result:
                        data.append(search_result)
        return data

    def get(self, request):
        type = request.GET.get('type', 'all').lower()
        query = request.GET.get('query', '')
        return self.analyse_search(request, type, query)

    def post(self, request):
        type = request.POST.get('type', 'all').lower()
        query = request.POST.get('query', '')
        return self.analyse_search(request, type, query)


























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
