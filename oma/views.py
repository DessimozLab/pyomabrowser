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
import pyham
import ete3

from . import tasks
from . import utils
from . import misc
from . import forms
from .models import FileResult
from pyoma.browser import db, models, search
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

        context.update({
            'tab': 'synteny',
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

class GenomeResolve(TemplateView):
    template_name = "explore_genomes.html"
    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        if not "query" in request.GET:
            return self.render_to_response(context)

        query_genome = request.GET.get("query").strip()
        try:
            g = utils.db.id_mapper['OMA'].identify_genome(query_genome)
            return HttpResponseRedirect(reverse('genome_info', args=(g['UniProtSpeciesCode'].decode(),)))
        except db.UnknownSpecies:
            try:
                tax = utils.db.tax.get_taxnode_from_name_or_taxid(query_genome)
                tax = tax["Name"][0].decode()
                return HttpResponseRedirect(reverse('ancestralgenome_info', args=(tax,)))
            except (db.InvalidTaxonId, KeyError) as e:
                # lets try with some approximate search
                candidates = utils.db.tax.approx_search(query_genome)
                cand_extant = utils.db.id_mapper['OMA'].approx_search_genomes(query_genome, scores=True)
                if len(candidates) > 0 and len(cand_extant) > 0:
                    if candidates[0][0] > cand_extant[1][0]:
                        return HttpResponseRedirect(reverse('ancestralgenome_info', args=(candidates[0][1],)))
                    else:
                        return HttpResponseRedirect(
                            reverse('genome_info', args=(cand_extant[0][0].uniprot_species_code))
                        )
                elif len(candidates) > 0:
                    return HttpResponseRedirect(reverse('ancestralgenome_info', args=(candidates[0][1],)))
                elif len(cand_extant) > 0:
                    return HttpResponseRedirect(
                        reverse('genome_info', args=(cand_extant[0][0].uniprot_species_code))
                    )
                else:
                    raise Http404(e)


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


class GenomeCentricGeneOrder(GenomeBase, TemplateView):
    template_name = "genome_order.html"

    def get_context_data(self, species_id, **kwargs):
        context = super(GenomeCentricGeneOrder, self).get_context_data(species_id, **kwargs)
        genome_obj = models.Genome(utils.db, utils.db.id_mapper['OMA'].genome_from_UniProtCode(species_id))

        target_param = self.request.GET.get('target', None)
        msg = json.dumps(None)

        if target_param:
            try:
                target_id = utils.id_resolver.resolve(target_param)
                entry = utils.db.entry_by_entry_nr(target_id)
                model_entry = models.ProteinEntry(utils.db, entry)

                if model_entry.genome.ncbi_taxon_id == genome_obj.ncbi_taxon_id:
                    target = model_entry.omaid
                else:
                    target = json.dumps(None)
                    msg = 'Focus: Gene Id {} is a valid id but is not present this genome.'.format(target_param)

            except (db.InvalidId, db.AmbiguousID):
                target = json.dumps(None)
                msg = 'Focus: {} is an invalid Id.'.format(target_param)

        else: target = json.dumps(None)

        context.update({'tab': 'gene_order', 'message_error': msg,  'target':target, 'genome_obj':genome_obj})
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
                lin_root_taxid = -1 if genomes_json['name'] == 'LUCA' else 0
                context['lineage'] = [
                    lev["Name"].decode() for lev in utils.db.tax.get_parent_taxa(context['taxid'], root=lin_root_taxid)
                ][1:]
                context['supported_ancestral_levels'] = set(l.decode() for l in utils.tax.all_hog_levels).intersection(
                    context['lineage'])
                context['ancestral_link_name'] = "ancestralgenome_info"
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


class AncestralGenomeCentricSynteny(AncestralGenomeBase, TemplateView):
    template_name = "ancestralgenome_synteny.html"

    def get_context_data(self, species_id, **kwargs):
        context = super(AncestralGenomeCentricSynteny, self).get_context_data(species_id, **kwargs)

        target_param = self.request.GET.get('target', None)
        msg = json.dumps(None)
        target = None
        hog_target = None

        if target_param:

            # if gene id as target
            if not target_param.startswith("HOG:"):

                try:
                    target_id = utils.id_resolver.resolve(target_param)
                    entry = utils.db.entry_by_entry_nr(target_id)
                    model_entry = models.ProteinEntry(utils.db, entry)
                    hog_target = model_entry.oma_hog


                except (db.InvalidId, db.AmbiguousID):
                    msg = 'Focus: {} is an invalid Gene Id.'.format(target_param)

            else: hog_target = target_param

            print('target', hog_target)

            if hog_target:

                hog = utils.db.iter_hogs_at_level(hog_id=hog_target, level=species_id)

                for h in hog:
                    if h[1].decode() == hog_target and h[2].decode() == species_id:
                        target = hog_target

            print(target)

            if not target:
                msg = 'Focus: {} is an invalid Id.'.format(target_param)

        if not target:
            target = json.dumps(None)

        context.update({'tab': 'synteny',
                        'message_error': msg,
                        'target':target,
                        'ancestral_link_name': "ancestralgenome_synteny"})
        return context

class AncestralGenomeCentricGenes(AncestralGenomeBase, TemplateView):
    template_name = "ancestralgenome_genes.html"

    def get_context_data(self, species_id, level=None, **kwargs):
        context = super(AncestralGenomeCentricGenes, self).get_context_data(species_id, **kwargs)

        if level is not None and level not in context['supported_ancestral_levels']:
            raise Http404(f"Reference level {f} is not valid as comparison with {species_id}")

        parent_level = None
        for parent_level in context['lineage']:
            if parent_level in context['supported_ancestral_levels']:
                break

        context.update({'tab': 'genes',
                        'level': level,
                        'api_url': '/api/hog/?level={}&per_page=250000'.format(context['genome_name']),
                        'parent_level': parent_level,
                        'ancestral_link_name': "ancestralgenome_genes"})
        return context



#</editor-fold >

#<editor-fold desc="HOGs Centric">


def resolve_hog_id(request, hog_id):
    # matches e.g. "HOG:0002124.1a.53bz.2a_4893"
    match = re.match(
        r'(?P<id>HOG:(?P<rel>[A-Z]+)?(?P<fam>\d+)(?:[a-z0-9.]*))(?:_(?P<taxid>-?\d+))?',
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
        for sim in sortedhogs:
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

class HOGgo(HOGBase, TemplateView):
    template_name = "hog_go.html"

    def get_context_data(self, hog_id, **kwargs):
        context = super(HOGgo, self).get_context_data(hog_id, **kwargs)
        hog = context['hog']
        context.update({'tab': 'go',
                        'api_url': '/api/hog/{}/gene_ontology/?level={}'.format(hog.hog_id, hog.level),
                        'lineage_link_name': 'hog_go',
                        })
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

        '''

        try:
            graph = utils.db.get_syntenic_hogs(hog_id=hog_id, level=context['level'], steps=2)
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
        
        '''

        context.update({'tab': 'synteny',
                        'hog_id': hog_id,
                        'lineage_link_name': 'hog_synteny'}) #synteny': ancestral_synteny,'neighbor': neigh})
        return context


class Matreex(HOGBase, TemplateView):
    template_name = "matreex.html"

    def get_context_data(self, hog_id, **kwargs):
        context = super(Matreex, self).get_context_data(hog_id, **kwargs)

        context.update({'tab': 'matreex', 'hog_id': hog_id,'lineage_link_name': 'matreex' })

        return context


class MatreexJson(HOGBase, JsonModelMixin, View):

    '''

    TO ADRIAN:

        ham2gt and gt2json are copy paste from matreex.py code
        I got problem with the newick tree from tax.newick() so i had to take the one from current release on browser (same problem on the original matreex code)
        I have not integrated the  _rename_gene_tree(cl, gt, family_name) and _add_lost_subtrees(gt, root_st) because not sure if needed

    '''

    def get(self, request, hog_id,  *args, **kwargs):
        context = self.get_context_data(hog_id, **kwargs)

        try:
            def ham2gt(node, hog_id):
                """
                Convert the pyham HOG object into a formatted ete3.Tree.
                """
                tree = ete3.Tree()

                if isinstance(node, pyham.Gene):
                    taxon = node.genome.name
                    tree.add_features(
                        event='',
                        gene=node.prot_id,
                        copy_nr='1'
                    )
                else:
                    if isinstance(node, pyham.DuplicationNode):

                        # taxon is MRCA of children
                        taxon = node.children[0].genome.taxon.get_common_ancestor(
                            [x.genome.taxon for x in node.children[1:]]).name
                        tree.add_features(
                            event='duplication'
                        )
                    else:
                        taxon = node.genome.name
                        hog_id = node.hog_id.split('_')[0] if node.hog_id else hog_id
                        tree.add_features(
                            event='speciation'
                        )

                #  common features between leaves, speciations and duplications
                tree.add_features(
                    HOG=hog_id,
                    HOG_name=hog_id,
                    taxon=taxon,
                    description=taxon,
                    color=''
                )
                # human friendly tree name
                tree.name = '{}_{}'.format(hog_id, taxon)

                if not isinstance(node, pyham.Gene):
                    # differentiate when descendant duplications or not
                    if hasattr(node, 'duplications'):

                        # because speciation children include children of child duplications, we consider only the one that did not arose by duplication
                        children = [x for x in node.children if not x.arose_by_duplication] + node.duplications

                    else:
                        children = node.children

                    for c in children:
                        tree.add_child(ham2gt(c, hog_id))

                return tree

            def gt2json(node):
                """
                Convert ete3.Tree gene tree into json.
                """
                event = node.event

                # pick name before id
                hog_name = node.HOG_name if node.HOG_name else node.HOG

                # leaf
                if node.is_leaf():
                    js = {
                        'HOG': hog_name,
                        'taxon': node.taxon,
                        'event': event if event == 'loss' else '',
                        'gene': node.gene,
                        'profile': {node.taxon: node.copy_nr},
                        'description': node.taxon
                    }

                else:
                    js = {
                        'HOG': hog_name,
                        'taxon': node.taxon,
                        'event': event,
                        'description': node.taxon
                    }

                if node.color:
                    js['color'] = node.color

                if not node.is_leaf():
                    js["children"] = []
                    for c in node.children:
                        js["children"].append(gt2json(c))

                return js

            fam = context['hog'].fam
            orthoxml = utils.db.get_orthoxml(fam)
            newick =  '''(("Archaeon GW2011_AR5", "Candidatus Altiarchaeales archaeon Bin_400", ("Heimdallarchaeota archaeon (strain B3-JM-08)", "Lokiarchaeota archaeon (strain CR_4)", "Odinarchaeota archaeon (strain LCB_4)", "Thorarchaeota archaeon (strain OWC)")"p__Asgardarchaeota", "Nanoarchaeota archaeon KR13_N2.mb.113", "Thermococci archaeon B88_G9", (("Archaeoglobus fulgidus (strain ATCC 49558 / DSM 4304 / JCM 9628 / NBRC 100126 / VC-16)", "Archaeoglobus profundus (strain DSM 5631 / JCM 9629 / NBRC 100127 / Av18)", "Archaeoglobus veneficus (strain DSM 11195 / SNP6)", "Ferroglobus placidus (strain DSM 10642 / AEDII12DO)")"f__Archaeoglobaceae", ("Halalkalicoccus jeotgali (strain DSM 18796 / CECT 7217 / JCM 14584 / KCTC 4019 / B3)", (("Haloarcula hispanica (strain ATCC 33960 / DSM 4426 / JCM 8911 / NBRC 102182 / NCIMB 2187 / VKM B-1755)", "Haloarcula marismortui (strain ATCC 43049 / DSM 3752 / JCM 8966 / VKM B-1809)")"g__Haloarcula", "Halomicrobium mukohataei (strain ATCC 700874 / DSM 12286 / JCM 9738 / NCIMB 13541)", "Halorhabdus utahensis (strain DSM 12940 / JCM 11049 / AX-2)", ("Natronomonas moolapensis (strain DSM 18674 / CECT 7526 / JCM 14361 / 8.8.11)", "Natronomonas pharaonis (strain ATCC 35678 / DSM 2160 / CIP 103997 / JCM 8858 / NBRC 14720 / NCIMB 2260 / Gabara)")"g__Natronomonas")"f__Haloarculaceae", ("Halobacterium salinarum (strain ATCC 29341 / DSM 671 / R1)", "Halobacterium salinarum (strain ATCC 700922 / JCM 11081 / NRC-1)")"s__Halobacterium salinarum", (("Haloferax mediterranei (strain ATCC 33500 / DSM 1411 / JCM 8866 / NBRC 14739 / NCIMB 2177 / R-4)", "Haloferax volcanii (strain ATCC 29605 / DSM 3757 / JCM 8879 / NBRC 14742 / NCIMB 2012 / VKM B-1768 / DS2)")"g__Haloferax", "Halogeometricum borinquense (strain ATCC 700274 / DSM 11551 / JCM 10706 / KCTC 4070 / PR3)", ("Haloquadratum walsbyi (strain DSM 16790 / HBSQ001)", "Haloquadratum walsbyi (strain DSM 16854 / JCM 12705 / C23)")"s__Haloquadratum walsbyi", ("Halorubrum lacusprofundi (strain ATCC 49239 / DSM 5036 / JCM 8891 / ACAM 34)", "Halorubrum vacuolatum")"g__Halorubrum")"f__Haloferacaceae", ("Halopiger xanaduensis (strain DSM 18323 / JCM 14033 / SH-6)", "Haloterrigena turkmenica (strain ATCC 51198 / DSM 5511 / JCM 9101 / NCIMB 13204 / VKM B-1734 / 4k)", "Halovivax ruber (strain DSM 18193 / JCM 13892 / XH-70)", ("Natrialba asiatica (strain ATCC 700177 / DSM 12278 / JCM 9576 / FERM P-10747 / NBRC 102637 / 172P1)", "Natrialba magadii (strain ATCC 43099 / DSM 3394 / CCM 3739 / CIP 104546 / IAM 13178 / JCM 8861 / NBRC 102185 / NCIMB 2190 / MS3)")"g__Natrialba", ("Natrinema sp. (strain J7-2)", "Natrinema pellirubrum (strain DSM 15624 / CIP 106293 / JCM 10476 / NCIMB 786 / 157)")"g__Natrinema", "Natronobacterium gregoryi (strain ATCC 43098 / DSM 3393 / CCM 3738 / CIP 104747 / IAM 13177 / JCM 8860 / NBRC 102187 / NCIMB 2189 / SP2)")"f__Natrialbaceae")"o__Halobacteriales", (("Methanocella conradii (strain DSM 24694 / JCM 17849 / CGMCC 1.5162 / HZ254)", "Methanocella paludicola (strain DSM 17711 / JCM 13418 / NBRC 101707 / SANAE)")"g__Methanocella", "Methanocella arvoryzae (strain DSM 22066 / NBRC 105507 / MRE50)")"f__Methanocellaceae", "Candidatus Methanoliparum thermophilum NM1a", ("Methanocorpusculum labreanum (strain ATCC 43576 / DSM 4855 / Z)", ("Methanoculleus bourgensis (strain ATCC 43281 / DSM 3045 / OCM 15 / MS2)", "Methanoculleus marisnigri (strain ATCC 35101 / DSM 1498 / JR1)")"g__Methanoculleus", "Methanolacinia petrolearia (strain DSM 11571 / OCM 486 / SEBR 4847)", ("Methanoregula boonei (strain DSM 21154 / JCM 14090 / 6A8)", "Methanoregula formicica (strain DSM 22288 / NBRC 105244 / SMSP)")"g__Methanoregula", "Methanosphaerula palustris (strain ATCC BAA-1556 / DSM 19958 / E1-9c)", "Methanospirillum hungatei JF-1 (strain ATCC 27890 / DSM 864 / NBRC 100397 / JF-1)")"o__Methanomicrobiales", "Candidatus Methanohalarchaeum thermophilum HMET1", (("Methanococcoides burtonii (strain DSM 6242 / NBRC 107633 / OCM 468 / ACE-M)", "Methanohalobium evestigatum (strain ATCC BAA-1072 / DSM 3721 / NBRC 107634 / OCM 161 / Z-7303)", "Methanohalophilus mahii (strain ATCC 35705 / DSM 5219 / SLP)", "Methanomethylovorans hollandica (strain DSM 15978 / NBRC 107637 / DMS1)", "Methanosalsum zhilinae (strain DSM 4017 / NBRC 107636 / OCM 62 / WeN5)", ("Methanosarcina acetivorans (strain ATCC 35395 / DSM 2834 / JCM 12185 / C2A)", "Methanosarcina barkeri (strain Fusaro / DSM 804)", "Methanosarcina mazei (strain ATCC BAA-159 / DSM 3647 / Goe1 / Go1 / JCM 11833 / OCM 88)")"g__Methanosarcina")"f__Methanosarcinaceae", ("Methanothrix soehngenii (strain ATCC 5969 / DSM 3671 / JCM 10134 / NBRC 103675 / OCM 69 / GP-6)", "Methanosaeta harundinacea (strain 6Ac)", "Methanothrix thermoacetophila (strain DSM 6194 / JCM 14653 / NBRC 101360 / PT)")"f__Methanotrichaceae")"c__Methanosarcinia", "Methanophagales archaeon G37ANME1")"p__Halobacteriota", "Candidatus Huberarchaeum crystalense CG_4_9_14_0_8_um_filter_31_21", "Archaeon GW2011_AR10", (("Methanobacterium lacus (strain AL-21)", "Methanobacterium paludis (strain DSM 25820 / JCM 18151 / SWAN1)", "Methanobrevibacter ruminantium (strain ATCC 35063 / DSM 1093 / JCM 13430 / OCM 146 / M1)", "Methanobrevibacter smithii (strain ATCC 35061 / DSM 861 / OCM 144 / PS)", "Methanosphaera stadtmanae (strain ATCC 43021 / DSM 3091 / JCM 11832 / MCB-3)")"f__Methanobacteriaceae", "Methanothermus fervidus (strain ATCC 43054 / DSM 2088 / JCM 10308 / V24 S)", ("Methanothermobacter marburgensis (strain ATCC BAA-927 / DSM 2133 / JCM 14651 / NBRC 100331 / OCM 82 / Marburg)", "Methanothermobacter thermautotrophicus (strain ATCC 29096 / DSM 1053 / JCM 10044 / NBRC 100330 / Delta H)")"g__Methanothermobacter")"o__Methanobacteriales", (((("Methanocaldococcus fervens (strain DSM 4213 / JCM 15782 / AG86)", "Methanocaldococcus jannaschii (strain ATCC 43067 / DSM 2661 / JAL-1 / JCM 10045 / NBRC 100440)", "Methanocaldococcus sp. (strain FS406-22)", "Methanocaldococcus vulcanius (strain ATCC 700851 / DSM 12094 / M7)")"g__Methanocaldococcus", "Methanocaldococcus infernus (strain DSM 11812 / JCM 15783 / ME)")"f__Methanocaldococcaceae", ((("Methanococcus maripaludis (strain S2 / LL)", "Methanococcus maripaludis X1")"s__Methanococcus maripaludis", "Methanococcus maripaludis (strain C7 / ATCC BAA-1331)", "Methanococcus maripaludis (strain C6 / ATCC BAA-1332)", "Methanococcus maripaludis (strain C5 / ATCC BAA-1333)", "Methanococcus vannielii (strain ATCC 35089 / DSM 1224 / JCM 13029 / OCM 148 / SB)", "Methanococcus voltae (strain ATCC BAA-1334 / A3)")"g__Methanococcus", ("Methanococcus aeolicus (strain ATCC BAA-1280 / DSM 17508 / OCM 812 / Nankai-3)", "Methanothermococcus okinawensis (strain DSM 14208 / JCM 11175 / IH1)")"g__Methanothermococcus_A", "Methanotorris igneus (strain DSM 5666 / JCM 11834 / Kol 5)")"f__Methanococcaceae")"o__Methanococcales", "Methanopyrus kandleri (strain AV19 / DSM 6324 / JCM 9639 / NBRC 100938)")"p__Methanobacteriota_A", (("Pyrococcus abyssi (strain GE5 / Orsay)", "Pyrococcus furiosus (strain ATCC 43587 / DSM 3638 / JCM 8422 / Vc1)", "Pyrococcus horikoshii (strain ATCC 700860 / DSM 12428 / JCM 9974 / NBRC 100139 / OT-3)", "Pyrococcus sp. (strain NA2)", "Pyrococcus yayanosii (strain CH1 / JCM 16557)")"g__Pyrococcus", ("Thermococcus gammatolerans (strain DSM 15229 / JCM 11827 / EJ3)", "Thermococcus kodakarensis (strain ATCC BAA-918 / JCM 12380 / KOD1)", "Thermococcus onnurineus (strain NA1)", "Thermococcus sp. (strain CGMCC 1.5172 / 4557)")"g__Thermococcus", ("Thermococcus litoralis (strain ATCC 51850 / DSM 5473 / JCM 8560 / NS-C)", "Thermococcus sibiricus (strain DSM 12597 / MM 739)")"g__Thermococcus_A", "Thermococcus barophilus (strain DSM 11836 / MP)")"f__Thermococcaceae", "Candidatus Fermentimicrarchaeum limneticum Sv326", (("Nanoarchaeum equitans (strain Kin4-M)", "Nanobsidianus stetteri")"o__Nanoarchaeales", "Archaeon GW2011_AR20", "Archaeon GW2011_AR15")"c__Nanoarchaeia", ("Nanosalina sp. (strain J07AB43)", "Nanosalinarum sp. (strain J07AB56)")"f__Nanosalinaceae", "Candidatus Altiarchaeota archaeon DPANNHV_H2.bin.121", ("Thermoplasmata archaeon B1_G16", "Thermoplasmatales archaeon MAG-13", "Candidatus Thermoplasmatota archaeon Zod_Metabat.400", "Candidatus Thalassarchaeum sp. BS30m-G33", "Euryarchaeota archaeon NC_groundwater_1308_Ag_S-0.2um_62_92", (("Aciduliprofundum boonei (strain DSM 19572 / T469)", "Aciduliprofundum sp. (strain MAR08-339)")"g__Aciduliprofundum", ("Methanomassiliicoccus intestinalis (strain Issoire-Mx1)", ("Methanomethylophilus alvus (strain Mx1201)", "Thermoplasmatales archaeon (strain BRNA1)")"g__Methanomethylophilus")"o__Methanomassiliicoccales", ("Picrophilus torridus (strain ATCC 700027 / DSM 9790 / JCM 10055 / NBRC 100828)", ("Thermoplasma acidophilum (strain ATCC 25905 / DSM 1728 / JCM 9062 / NBRC 15155 / AMRC-C165)", "Thermoplasma volcanium (strain ATCC 51530 / DSM 4299 / JCM 9571 / NBRC 15438 / GSS1)")"g__Thermoplasma")"f__Thermoplasmataceae")"c__Thermoplasmata")"p__Thermoplasmatota", ("Thaumarchaeota archaeon SJ3.Bin56", "Korarchaeum cryptofilum (strain OPF8)", "Candidatus Methanosuratus subterraneum Ch88", (("Cenarchaeum symbiosum (strain A)", "Nitrosopumilus maritimus (strain SCM1)")"f__Nitrosopumilaceae", "Nitrososphaera gargensis (strain Ga9.2)")"o__Nitrososphaerales", "Caldiarchaeum subterraneum", "archaeon B48_G17", ("Crenarchaeota archaeon SCGC AAA471-B05", (("Acidilobus saccharovorans (strain DSM 16705 / JCM 18335 / VKM B-2471 / 345-15)", "Aeropyrum pernix (strain ATCC 700893 / DSM 11879 / JCM 9820 / NBRC 100138 / K1)", "Caldisphaera lagunensis (strain DSM 15908 / JCM 11604 / ANMR 0165 / IC-154)")"f__Acidilobaceae", (("Desulfurococcus amylolyticus (strain DSM 18924 / JCM 16383 / VKM B-2413 / 1221n)", "Desulfurococcus mucosus (strain ATCC 35584 / DSM 2162 / JCM 9187 / O7/1)")"g__Desulfurococcus", ("Staphylothermus hellenicus (strain DSM 12710 / JCM 10830 / BK20S6-10-b1 / P8)", "Staphylothermus marinus (strain ATCC 43588 / DSM 3639 / JCM 9404 / F1)")"g__Staphylothermus", "Thermogladius calderae (strain DSM 22663 / VKM B-2946 / 1633)", "Thermosphaera aggregans (strain DSM 11486 / M11TL)")"f__Desulfurococcaceae", "Fervidicoccus fontis (strain DSM 19380 / JCM 18336 / VKM B-2539 / Kam940)", "Ignicoccus hospitalis (strain KIN4/I / DSM 18386 / JCM 14125)", "Ignisphaera aggregans (strain DSM 17230 / JCM 13409 / AQ1.S1)", ("Hyperthermus butylicus (strain DSM 5456 / JCM 9403 / PLM1-5)", "Pyrodictium occultum", "Pyrolobus fumarii (strain DSM 11204 / 1A)")"f__Pyrodictiaceae", ("Acidianus hospitalis (strain W1)", ("Metallosphaera cuprina (strain Ar-4)", "Metallosphaera sedula (strain ATCC 51363 / DSM 5348 / JCM 9185 / NBRC 15509 / TH2)")"g__Metallosphaera", (("Sulfolobus islandicus (strain HVE10/4)", "Sulfolobus islandicus (strain L.D.8.5 / Lassen #2)", "Sulfolobus islandicus (strain L.S.2.15 / Lassen #1)", "Sulfolobus islandicus (strain M.14.25 / Kamchatka #1)", "Sulfolobus islandicus (strain M.16.27)", "Sulfolobus islandicus (strain M.16.4 / Kamchatka #3)", "Sulfolobus islandicus (strain REY15A)", "Sulfolobus islandicus (strain Y.G.57.14 / Yellowstone #1)", "Sulfolobus islandicus (strain Y.N.15.51 / Yellowstone #2)")"s__Saccharolobus islandicus", ("Saccharolobus solfataricus (strain 98/2)", "Saccharolobus solfataricus (strain ATCC 35092 / DSM 1617 / JCM 11322 / P2)")"s__Saccharolobus solfataricus")"g__Saccharolobus", "Sulfolobus acidocaldarius (strain ATCC 33909 / DSM 639 / JCM 8929 / NBRC 15157 / NCIMB 11770)", "Sulfurisphaera tokodaii (strain DSM 16993 / JCM 10545 / NBRC 100140 / 7)")"f__Sulfolobaceae")"o__Sulfolobales", "Thermofilum pendens (strain DSM 2475 / Hrk 5)", (("Caldivirga maquilingensis (strain ATCC 700844 / DSM 13496 / JCM 10307 / IC-167)", ("Vulcanisaeta distributa (strain DSM 14429 / JCM 11212 / NBRC 100878 / IC-017)", "Vulcanisaeta moutnovskia (strain 768-28)")"g__Vulcanisaeta")"f__Thermocladiaceae", (("Pyrobaculum aerophilum (strain ATCC 51768 / DSM 7523 / JCM 9630 / CIP 104966 / NBRC 100827 / IM2)", "Pyrobaculum arsenaticum (strain DSM 13514 / JCM 11321 / PZ6)", "Pyrobaculum calidifontis (strain DSM 21063 / JCM 11548 / VA1)", "Pyrobaculum islandicum (strain DSM 4184 / JCM 9189 / GEO3)", "Pyrobaculum neutrophilum (strain DSM 2338 / JCM 9278 / NBRC 100436 / V24Sta)", "Pyrobaculum oguniense (strain DSM 13380 / JCM 10595 / TE7)")"g__Pyrobaculum", ("Thermoproteus tenax (strain ATCC 35583 / DSM 2078 / JCM 9277 / NBRC 100435 / Kra 1)", "Thermoproteus uzoniensis (strain 768-20)")"g__Thermoproteus")"f__Thermoproteaceae")"o__Thermoproteales")"c__Thermoproteia")"p__Thermoproteota", "Euryarchaeota archaeon ARS1358")"Archaea", ("bacterium Zod_Metabat.1143", "Candidatus Cloacimonetes bacterium 4572_55", ("Calditrichaeota bacterium co234_bin30", "candidate division LCP-89 bacterium B3_LCP", "Calditrichaeota bacterium SuakinDeep_MAG45_3", "bacterium BS750m-G18", "bacterium Aved_18-Q3-R54-62_MAXAC.418")"p__AABM5-125-24", "Gemmatimonadetes bacterium ARS69", "Candidatus Abyssubacteria bacterium SURF_5", (((("Acidobacterium capsulatum (strain ATCC 51196 / DSM 11244 / BCRC 80197 / JCM 7670 / NBRC 15755 / NCIMB 13165 / 161)", "Granulicella mallensis (strain ATCC BAA-1857 / DSM 23137 / MP5ACTX8)", "Granulicella tundricola (strain ATCC BAA-1859 / DSM 23138 / MP5ACTX9)", ("Terriglobus roseus (strain DSM 18391 / NRRL B-41598 / KBS 63)", "Terriglobus saanensis (strain ATCC BAA-1853 / DSM 23119 / SP1PR4)")"g__Terriglobus")"f__Acidobacteriaceae", "Koribacter versatilis (strain Ellin345)")"o__Acidobacteriales", "Solibacter usitatus (strain Ellin6076)")"c__Acidobacteriae", "bacterium (candidate division B38) B3_B38", "Chloracidobacterium thermophilum (strain B)", "bacterium HR11 HRbin11", "Sulfidibacter corallicola", "Acidobacteria bacterium Mor1", "Holophagales bacterium EsbW_18-Q3-R4-48_BAT3C.4_cln", "Acidobacteria bacterium s2_autometa_2-0", "Luteitalea pratensis")"p__Acidobacteriota", ("Acidimicrobium ferrooxidans (strain DSM 10331 / JCM 15462 / NBRC 103882 / ICP)", ("Acidothermus cellulolyticus (strain ATCC 43068 / DSM 8971 / 11B)", (("Arcanobacterium haemolyticum (strain ATCC 9345 / DSM 20595 / CCUG 17215 / LMG 16163 / NBRC 15585 / NCTC 8452 / 11018)", "Mobiluncus curtisii (strain ATCC 43063 / DSM 2711 / V125)")"f__Actinomycetaceae", "Beutenbergia cavernae (strain ATCC BAA-8 / DSM 12333 / NBRC 16432)", ("Bifidobacterium adolescentis (strain ATCC 15703 / DSM 20083 / NCTC 11814 / E194a)", ("Bifidobacterium animalis subsp. animalis (strain ATCC 25527 / DSM 20104 / JCM 1190 / R101-8)", "Bifidobacterium animalis subsp. lactis (strain AD011)", "Bifidobacterium animalis subsp. lactis (strain BB-12)", "Bifidobacterium animalis subsp. lactis (strain Bl-04 / DGCC2908 / RB 4825 / SD5219)", "Bifidobacterium animalis subsp. lactis (strain DSM 10140 / JCM 10602 / LMG 18314)", "Bifidobacterium animalis subsp. lactis (strain V9)")"s__Bifidobacterium animalis", "Bifidobacterium asteroides (strain PRL2011)", ("Bifidobacterium bifidum (strain PRL2010)", "Bifidobacterium bifidum (strain S17)")"s__Bifidobacterium bifidum", "Bifidobacterium breve (strain ACS-071-V-Sch8b)", "Bifidobacterium dentium (strain ATCC 27534 / DSM 20436 / JCM 1195 / Bd1)", "Bifidobacterium longum subsp. infantis (strain ATCC 15697 / DSM 20088 / JCM 1222 / NCTC 11817 / S12)", ("Bifidobacterium longum (strain DJO10A)", "Bifidobacterium longum (strain NCC 2705)", "Bifidobacterium longum subsp. infantis (strain 157F)", "Bifidobacterium longum subsp. longum (strain ATCC 15707 / DSM 20219 / JCM 1217 / NCTC 11818 / E194b)", "Bifidobacterium longum subsp. longum (strain BBMN68)", "Bifidobacterium longum subsp. longum (strain JDM301)")"s__Bifidobacterium longum", "Gardnerella vaginalis (strain 409-05)", ("Gardnerella vaginalis (strain ATCC 14019 / 317)", "Gardnerella vaginalis (strain HMP9231)")"s__Bifidobacterium vaginale")"g__Bifidobacterium", "Brevibacterium linens", (("Cellulomonas fimi (strain ATCC 484 / DSM 20113 / JCM 1341 / NBRC 15513 / NCIMB 8980 / NCTC 7547)", "Cellulomonas flavigena (strain ATCC 482 / DSM 20109 / BCRC 11376 / JCM 18109 / NBRC 3775 / NCIMB 8073 / NRS 134)", "Cellulomonas gilvus (strain ATCC 13127 / NRRL B-14078)")"g__Cellulomonas", "Isoptericola variabilis (strain 225)", "Jonesia denitrificans (strain ATCC 14870 / DSM 20603 / BCRC 15368 / CIP 55.134 / JCM 11481 / NBRC 15587 / NCTC 10816 / Prevot 55134)", "Sanguibacter keddieii (strain ATCC 51767 / DSM 10542 / NCFB 3025 / ST-74)", "Xylanimonas cellulosilytica (strain DSM 15894 / CECT 5975 / LMG 20990 / XIL07)")"f__Cellulomonadaceae", "Brachybacterium faecium (strain ATCC 43885 / DSM 4810 / JCM 11609 / LMG 19847 / NBRC 14762 / NCIMB 9860 / 6-10)", ("Intrasporangium calvum (strain ATCC 23552 / DSM 43043 / JCM 3097 / NBRC 12989 / 7 KIP)", "Kytococcus sedentarius (strain ATCC 14392 / DSM 20547 / CCM 314 / 541)")"f__Dermatophilaceae", "Kineococcus radiotolerans (strain ATCC BAA-149 / DSM 14245 / SRS30216)", (("Clavibacter michiganensis subsp. michiganensis (strain NCPPB 382)", "Clavibacter michiganensis subsp. sepedonicus (strain ATCC 33113 / DSM 20744 / JCM 9667 / LMG 2889 / C-1)")"g__Clavibacter", "Leifsonia xyli subsp. xyli (strain CTCB07)", "Microbacterium testaceum (strain StLB037)", ("Tropheryma whipplei (strain TW08/27)", "Tropheryma whipplei (strain Twist)")"s__Tropheryma whipplei")"f__Microbacteriaceae", ("Arthrobacter sp. (strain FB24)", "Glutamicibacter arilaitensis (strain DSM 16368 / CIP 108037 / IAM 15318 / JCM 13566 / NCIMB 14258 / Re117)", "Kocuria rhizophila (strain ATCC 9341 / DSM 348 / NBRC 103217 / DC2201)", "Micrococcus luteus (strain ATCC 4698 / DSM 20030 / JCM 1464 / NBRC 3333 / NCIMB 9278 / NCTC 2665 / VKM Ac-2230)", "Paenarthrobacter aurescens (strain TC1)", ("Pseudarthrobacter chlorophenolicus (strain ATCC 700700 / DSM 12829 / CIP 107037 / JCM 12360 / KCTC 9906 / NCIMB 13794 / A6)", "Pseudarthrobacter phenanthrenivorans (strain DSM 18606 / JCM 16027 / LMG 23796 / Sphe3)")"g__Pseudarthrobacter", "Renibacterium salmoninarum (strain ATCC 33209 / DSM 20767 / JCM 11484 / NBRC 15589 / NCIMB 2235)", ("Rothia dentocariosa (strain ATCC 17931 / CDC X599 / XDIA)", "Rothia mucilaginosa (strain DY-18)")"g__Rothia")"f__Micrococcaceae")"o__Actinomycetales", (("Frankia alni (strain ACN14a)", "Frankia casuarinae (strain DSM 45818 / CECT 9043 / CcI3)", "Frankia inefficax (strain DSM 45817 / CECT 9037 / EuI1c)", "Frankia sp. (strain EAN1pec)")"g__Frankia", ("Blastococcus saxobsidens (strain DD2)", "Geodermatophilus obscurus (strain ATCC 25078 / DSM 43160 / JCM 3152 / KCC A-0152 / KCTC 9177 / NBRC 13315 / NRRL B-3577 / G-20)", "Modestobacter marinus (strain BC501)")"f__Geodermatophilaceae", (("Actinoplanes missouriensis (strain ATCC 14538 / DSM 43046 / CBS 188.64 / JCM 3121 / NBRC 102363 / NCIMB 12654 / NRRL B-3342 / UNCC 431)", "Actinoplanes sp. (strain ATCC 31044 / CBS 674.73 / SE50/110)", "Actinoplanes utahensis")"g__Actinoplanes", ("Salinispora arenicola (strain CNS-205)", ("Micromonospora aurantiaca (strain ATCC 27029 / DSM 43813 / BCRC 12538 / CBS 129.76 / JCM 10878 / NBRC 16125 / NRRL B-16091 / INA 9442)", "Micromonospora sp. (strain L5)")"s__Micromonospora aurantiaca", "Micromonospora maris (strain DSM 45365 / JCM 31040 / NBRC 109089 / NRRL B-24793 / AB-18-032)", "Micromonospora sp. (strain ATCC 39149 / NRRL 15099 / SCC 1413)", "Salinispora tropica (strain ATCC BAA-916 / DSM 44818 / CNB-440)")"g__Micromonospora", "Stackebrandtia nassauensis (strain DSM 44728 / CIP 108903 / NRRL B-16338 / NBRC 102104 / LLR-40K-21)")"f__Micromonosporaceae", (("Corynebacterium aurimucosum (strain ATCC 700975 / DSM 44827 / CIP 107346 / CN-1)", ("Corynebacterium diphtheriae (strain 241)", "Corynebacterium diphtheriae (strain 31A)", "Corynebacterium diphtheriae (strain ATCC 27012 / C7 (beta))", "Corynebacterium diphtheriae (strain ATCC 700971 / NCTC 13129 / Biotype gravis)", "Corynebacterium diphtheriae (strain CDCE 8392)", "Corynebacterium diphtheriae (strain HC01)", "Corynebacterium diphtheriae (strain HC02)", "Corynebacterium diphtheriae (strain HC03)", "Corynebacterium diphtheriae (strain HC04)", "Corynebacterium diphtheriae (strain PW8)", "Corynebacterium diphtheriae (strain VA01)")"s__Corynebacterium diphtheriae", "Corynebacterium efficiens (strain DSM 44549 / YS-314 / AJ 12310 / JCM 11189 / NBRC 100395)", ("Corynebacterium glutamicum (strain ATCC 13032 / DSM 20300 / BCRC 11384 / JCM 1318 / LMG 3730 / NCIMB 10025)", "Corynebacterium glutamicum (strain ATCC 13032 / K051)", "Corynebacterium glutamicum (strain R)")"s__Corynebacterium glutamicum", "Corynebacterium jeikeium (strain K411)", "Corynebacterium kroppenstedtii (strain DSM 44385 / JCM 11950 / CIP 105744 / CCUG 35717)", "Corynebacterium lipophiloflavum (strain ATCC 700352 / DSM 44291 / CCUG 37336 / JCM 10383 / DMMZ 1944)", ("Corynebacterium pseudotuberculosis (strain 1002)", "Corynebacterium pseudotuberculosis (strain C231)", "Corynebacterium pseudotuberculosis (strain FRC41)", "Corynebacterium pseudotuberculosis (strain I19)")"s__Corynebacterium pseudotuberculosis", "Corynebacterium resistens (strain DSM 45100 / JCM 12819 / GTC 2026 / SICGH 158)", "Corynebacterium ulcerans (strain BR-AD22)", "Corynebacterium urealyticum (strain ATCC 43042 / DSM 7109)", "Corynebacterium variabile (strain DSM 44702 / CIP 107183 / JCM 12073 / NCIMB 30131)")"g__Corynebacterium", ("Gordonia bronchialis (strain ATCC 25592 / DSM 43247 / BCRC 13721 / JCM 3198 / KCTC 3076 / NBRC 16047 / NCTC 10667)", "Gordonia polyisoprenivorans (strain DSM 44266 / VH2)")"g__Gordonia", "Hoyosella subflava (strain DSM 45089 / JCM 17490 / NBRC 109087 / DQS3-9A1)", (("Escherichia coli (strain ATCC 33849 / DSM 4235 / NCIMB 12045 / K12 / DH1)", "Mycobacteroides abscessus (strain ATCC 19977 / DSM 44196 / CIP 104536 / JCM 13569 / NCTC 13031 / TMC 1543)")"s__Mycobacterium abscessus", "Mycobacterium asiaticum", "Mycolicibacterium vanbaalenii (strain DSM 7251 / JCM 13017 / BCRC 16820 / KCTC 9966 / NRRL B-24157 / PYR-1)", ("Mycobacterium avium (strain 104)", "Mycolicibacterium paratuberculosis (strain ATCC BAA-968 / K-10)")"s__Mycobacterium avium", "Mycoplasma conjunctivae (strain ATCC 25834 / HRC/581 / NCTC 10147)", "Mycobacteroides chelonae", "Mycolicibacterium chubuense", "Mycobacterium chubuense (strain NBB4)", ("Mycolicibacterium gilvum (strain DSM 45189 / LMG 24558 / Spyr1)", "Mycolicibacterium gilvum (strain PYR-GCK)")"s__Mycobacterium gilvum", "Mycobacterium gordonae", "Mycolicibacterium hassiacum (strain DSM 44199 / CIP 105218 / JCM 12690 / 3849)", "Mycobacterium intracellulare (strain ATCC 13950 / DSM 43223 / JCM 6384 / NCTC 13025 / 3600)", "Mycobacterium kansasii", ("Mycobacterium leprae (strain Br4923)", "Mycobacterium leprae (strain TN)")"s__Mycobacterium leprae", ("Mycobacterium marinum (strain ATCC BAA-535 / M)", "Mycobacterium ulcerans (strain Agy99)")"s__Mycobacterium marinum", ("Mycobacterium sp. (strain JLS)", "Mycobacterium sp. (strain KMS)", "Mycobacterium sp. (strain MCS)")"s__Mycobacterium monacense", "Mycolicibacterium rhodesiae (strain NBB3)", "Mycobacterium shimoidei", "Mycolicibacter sinensis (strain JDM601)", "Mycolicibacterium smegmatis (strain ATCC 700084 / mc(2)155)", "Mycolicibacterium thermoresistibile (strain ATCC 19527 / DSM 44167 / CIP 105390 / JCM 6362 / NCTC 10409 / 316)", ("Mycobacterium africanum (strain GM041182)", "Mycobacterium bovis (strain ATCC BAA-935 / AF2122/97)", "Mycobacterium bovis (strain BCG / Pasteur 1173P2)", "Mycobacterium bovis (strain BCG / Tokyo 172 / ATCC 35737 / TMC 1019)", "Mycobacterium canettii (strain CIPT 140010059)", "Mycobacterium tuberculosis (strain ATCC 25177 / H37Ra)", "Mycobacterium tuberculosis (strain ATCC 25618 / H37Rv)", "Mycobacterium tuberculosis (strain CCDC5079)", "Mycobacterium tuberculosis (strain CCDC5180)", "Mycobacterium tuberculosis (strain F11)", "Mycobacterium tuberculosis (strain KZN 1435 / MDR)")"s__Mycobacterium tuberculosis")"g__Mycobacterium", ("Nocardia cyriacigeorgica (strain GUH-2)", "Nocardia farcinica (strain IFM 10152)")"g__Nocardia", ("Rhodococcus erythropolis (strain PR4 / NBRC 100887)", "Rhodococcus hoagii (strain 103S)", "Rhodococcus jostii (strain RHA1)", "Rhodococcus opacus (strain B4)")"g__Rhodococcus", "Segniliparus rotundus (strain ATCC BAA-972 / CDC 1076 / CIP 108378 / DSM 44985 / JCM 13578)", "Tsukamurella paurometabola (strain ATCC 8368 / DSM 20162 / CCUG 35730 / CIP 100753 / JCM 10117 / KCTC 9821 / NBRC 16120 / NCIMB 702349 / NCTC 13040)")"f__Mycobacteriaceae", "Nakamurella multipartita (strain ATCC 700099 / DSM 44233 / CIP 104796 / JCM 9543 / NBRC 105858 / Y-104)", (("Saccharothrix espanaensis (strain ATCC 51144 / DSM 44229 / JCM 9112 / NBRC 15066 / NRRL 15764)", "Actinosynnema mirum (strain ATCC 29888 / DSM 43827 / JCM 3225 / NBRC 14064 / NCIMB 13271 / NRRL B-12336 / IMRU 3971 / 101)")"g__Actinosynnema", ("Amycolatopsis mediterranei (strain S699)", "Amycolatopsis mediterranei (strain U-32)")"s__Amycolatopsis mediterranei", "Lentzea aerocolonigenes", "Pseudonocardia dioxanivorans (strain ATCC 55486 / DSM 44775 / JCM 13855 / CB1190)", "Saccharomonospora viridis (strain ATCC 15386 / DSM 43017 / JCM 3036 / NBRC 12207 / P101)", "Saccharopolyspora erythraea (strain ATCC 11635 / DSM 40517 / JCM 4748 / NBRC 13426 / NCIMB 8594 / NRRL 2338)")"f__Pseudonocardiaceae")"o__Mycobacteriales", ("Kribbella flavida (strain DSM 17836 / JCM 10339 / NBRC 14399)", ("Nocardioides simplex", "Nocardioides sp. (strain ATCC BAA-499 / JS614)")"g__Nocardioides", ("Acidipropionibacterium acidipropionici (strain ATCC 4875 / DSM 20272 / JCM 6432 / NBRC 12425 / NCIMB 8070 / 4)", "Arachnia propionica (strain F0230a)", ("Cutibacterium acnes (strain DSM 16379 / KPA171202)", "Cutibacterium acnes (strain SK137)")"s__Cutibacterium acnes", "Microlunatus phosphovorus (strain ATCC 700054 / DSM 10555 / JCM 9379 / NBRC 101784 / NCIMB 13414 / VKM Ac-1990 / NM-1)", "Propionibacterium freudenreichii subsp. shermanii (strain ATCC 9614 / DSM 4902 / CIP 103027 / NCIMB 8099 / CIRM-BIA1)")"f__Propionibacteriaceae")"o__Propionibacteriales", ("Catenulispora acidiphila (strain DSM 44928 / JCM 14897 / NBRC 102108 / NRRL B-24433 / ID139908)", (("Kitasatospora griseola", "Streptomyces rubellomurinus (strain ATCC 31215)", "Kitasatospora setae (strain ATCC 33774 / DSM 43861 / JCM 3304 / KCC A-0304 / NBRC 14216 / KM-6054)")"g__Kitasatospora", ("Streptomyces ambofaciens (strain ATCC 23877 / 3486 / DSM 40053 / JCM 4204 / NBRC 12836 / NRRL B-2516)", "Streptomyces coelicolor (strain ATCC BAA-471 / A3(2) / M145)", "Streptomyces avermitilis (strain ATCC 31267 / DSM 46492 / JCM 5070 / NBRC 14893 / NCIMB 12804 / NRRL 8165 / MA-4680)", "Streptomyces cattleya (strain ATCC 35852 / DSM 46488 / JCM 4925 / NBRC 14057 / NRRL 8057)", "Streptomyces clavuligerus", "Streptomyces collinus (strain DSM 40733 / Tue 365)", "Streptomyces davaonensis (strain DSM 101723 / JCM 4913 / KCC S-0913 / 768)", "Streptomyces glaucescens", "Streptomyces griseus subsp. griseus (strain JCM 4626 / NBRC 13350)", "Streptomyces lincolnensis", "Streptomyces bingchenggensis (strain BCW-1)", "Streptomyces netropsis", "Streptomyces hygroscopicus subsp. jinggangensis (strain 5008)", "Streptomyces pratensis (strain ATCC 33331 / IAF-45CD)", "Streptomyces pristinaespiralis (strain ATCC 25486 / DSM 40338 / CBS 914.69 / JCM 4507 / NBRC 13074 / NRRL 2958 / 5647)", "Streptomyces rimosus subsp. rimosus (strain ATCC 10970 / DSM 40260 / JCM 4667 / NRRL 2234)", "Streptomyces scabiei (strain 87.22)", "Streptomyces sp. (strain SPB074)", "Streptomyces sp. (strain SirexAA-E / ActE)", "Kitasatospora aureofaciens", "Streptomyces toyocaensis", "Streptomyces tsukubensis (strain DSM 42081 / NBRC 108919 / NRRL 18488 / 9993)", "Streptomyces venezuelae (strain ATCC 10712 / CBS 650.69 / DSM 40230 / JCM 4526 / NBRC 13096 / PD 04745)", "Streptomyces viridosporus (strain ATCC 14672 / DSM 40746 / JCM 4963 / KCTC 9882 / NRRL B-12104 / FH 1290)", "Streptomyces fradiae")"g__Streptomyces")"f__Streptomycetaceae")"o__Streptomycetales", (("Nocardiopsis alba (strain ATCC BAA-2165 / BE74)", "Nocardiopsis dassonvillei (strain ATCC 23218 / DSM 43111 / CIP 107115 / JCM 7437 / KCTC 9190 / NBRC 14626 / NCTC 10488 / NRRL B-5397 / IMRU 509)")"g__Nocardiopsis", "Streptosporangium roseum (strain ATCC 12428 / DSM 43021 / JCM 3005 / NI 9100)", "Thermobifida fusca (strain YX)", "Thermobispora bispora (strain ATCC 19993 / DSM 43833 / CBS 139.67 / JCM 10125 / KCTC 9307 / NBRC 14880 / R51)", "Thermomonospora curvata (strain ATCC 19995 / DSM 43183 / JCM 3096 / KCTC 9072 / NBRC 15933 / NCIMB 10081 / Henssen B9)")"f__Streptosporangiaceae")"c__Actinomycetia", "Actinobacteria bacterium CROMO_BS_222_8", (("Lancefieldella parvula (strain ATCC 33793 / DSM 20469 / CCUG 32760 / JCM 10300 / KCTC 3663 / VPI 0546 / 1246)", "Olsenella uli (strain ATCC 49627 / DSM 7084 / CIP 109912 / JCM 12494 / NCIMB 702895 / VPI D76D-27C)")"f__Atopobiaceae", "Coriobacterium glomerans (strain ATCC 49209 / DSM 20642 / JCM 10262 / PW2)", ("Cryptobacterium curtum (strain ATCC 700683 / DSM 15641 / CCUG 43107 / 12-3)", "Eggerthella lenta (strain ATCC 25559 / DSM 2243 / CCUG 17323 / JCM 9979 / KCTC 3265 / NCTC 11813 / VPI 0255 / 1899 B)", "Eggerthella sp. (strain YY7918)", "Slackia heliotrinireducens (strain ATCC 29202 / DSM 20476 / NCTC 11029 / RHS 1)")"f__Eggerthellaceae")"o__Coriobacteriales", "Actinobacteria bacterium MAG-41", "Rubrobacter xylanophilus (strain DSM 9941 / NBRC 16129 / PRD-1)", "Conexibacter woesei (strain DSM 14684 / CIP 108061 / JCM 11494 / NBRC 100937 / ID131577)", "Actinobacteria bacterium Dino_bin11")"p__Actinobacteriota", "Candidatus Aerophobetes bacterium Ae_b3b", (((("Aquifex aeolicus (strain VF5)", "Hydrogenobacter thermophilus (strain DSM 6534 / IAM 12695 / TK-6)", "Thermocrinis albus (strain DSM 14484 / JCM 11386 / HI 11/12)")"f__Aquificaceae", "Hydrogenobaculum sp. (strain Y04AAS1)")"o__Aquificales", ("Persephonella marina (strain DSM 14350 / EX-H1)", ("Sulfurihydrogenibium azorense (strain Az-Fu1 / DSM 15241 / OCM 825)", "Sulfurihydrogenibium sp. (strain YO3AOP1)")"g__Sulfurihydrogenibium")"f__Hydrogenothermaceae")"c__Aquificae", ("Desulfurobacterium thermolithotrophum (strain DSM 11699 / BSA)", "Thermovibrio ammonificans (strain DSM 15698 / JCM 12110 / HB-1)")"f__Desulfurobacteriaceae")"p__Aquificota", ("Abitibacteriaceae bacterium CP_BM_RX_R8_36", "Armatimonas rosea", "Chthonomonas calidirosea (strain DSM 23976 / ICMP 18418 / T49)", "Fimbriimonas ginsengisoli", "Armatimonadetes bacterium AS09scLD_344", "Armatimonadetes bacterium NC_groundwater_1868_Pr3_B-0.1um_69_17", "Armatimonadetes bacterium Ch1", "Abditibacteriota bacterium RGIG7931")"p__Armatimonadota", ("Atribacter laminatus", "Candidatus Atribacteria bacterium AS21ysBPME_310")"p__Atribacterota", "Candidatus Coatesbacteria bacterium Zod_Metabat.233", "bacterium BMS3Abin14", "candidate division KSB1 bacterium BS750m-G25", "Candidatus Omnitrophica bacterium BS750m-G34", ("Ignavibacteriales bacterium CG07_land_8_20_14_0_80_59_12", (("Azobacteroides pseudotrichonymphae genomovar. CFP2", ((("Bacteroides fragilis (strain 638R)", "Bacteroides fragilis (strain ATCC 25285 / DSM 2151 / CCUG 4856 / JCM 11019 / NCTC 9343 / Onslow)", "Bacteroides fragilis (strain YCH46)")"s__Bacteroides fragilis", "Bacteroides helcogenes (strain ATCC 35417 / DSM 20613 / JCM 6297 / CCUG 15421 / P 36-108)", "Bacteroides stercoris", "Bacteroides thetaiotaomicron (strain ATCC 29148 / DSM 2079 / JCM 5827 / CCUG 10774 / NCTC 10582 / VPI-5482 / E50)")"g__Bacteroides", ("Phocaeicola salanitronis (strain DSM 18170 / JCM 13657 / BL78)", "Phocaeicola vulgatus (strain ATCC 8482 / DSM 1447 / JCM 5826 / CCUG 4940 / NBRC 14291 / NCTC 11154)")"g__Phocaeicola", ("Prevotella denticola (strain F0289)", "Prevotella intermedia (strain 17)", "Prevotella melaninogenica (strain ATCC 25845 / DSM 7089 / JCM 6325 / VPI 2381 / B282)", "Prevotella ruminicola (strain ATCC 19189 / JCM 8958 / 23)", "Prevotella dentalis (strain ATCC 49559 / DSM 3688 / JCM 13448 / NCTC 12043 / ES 2772)")"g__Prevotella")"f__Bacteroidaceae", "Odoribacter splanchnicus (strain ATCC 29572 / DSM 20712 / CIP 104287 / JCM 15291 / NCTC 10825 / 1651/6)", "Paludibacter propionicigenes (strain DSM 17365 / JCM 13257 / WB4)", (("Porphyromonas asaccharolytica (strain ATCC 25260 / DSM 20707 / BCRC 10618 / JCM 6326 / LMG 13178 / VPI 4198)", "Porphyromonas endodontalis (strain ATCC 35406 / BCRC 14492 / JCM 8526 / NCTC 13058 / HG 370)", ("Porphyromonas gingivalis (strain ATCC 33277 / DSM 20709 / CIP 103683 / JCM 12257 / NCTC 11834 / 2561)", "Porphyromonas gingivalis (strain ATCC BAA-308 / W83)")"s__Porphyromonas gingivalis")"g__Porphyromonas", "Porphyromonas cangingivalis")"f__Porphyromonadaceae", "Alistipes finegoldii (strain DSM 17242 / JCM 16770 / CCUG 46020 / CIP 107999 / KCTC 15236 / AHN 2437)", ("Parabacteroides distasonis (strain ATCC 8503 / DSM 20701 / CIP 104284 / JCM 5825 / NCTC 11152)", "Tannerella forsythia (strain ATCC 43037 / JCM 10827 / CCUG 21028 A / KCTC 5666 / FDC 338)")"f__Tannerellaceae")"o__Bacteroidales", (("Chitinophaga pinensis (strain ATCC 43595 / DSM 2588 / LMG 13176 / NBRC 15968 / NCIMB 11800 / UQM 2034)", "Niabella drilacis (strain DSM 25811 / CCM 8410 / LMG 26954 / E90)", "Niastella koreensis (strain DSM 17620 / KACC 11465 / NBRC 106392 / GR20-10)")"f__Chitinophagaceae", ("Haliscomenobacter hydrossis (strain ATCC 27775 / DSM 1100 / LMG 10767 / O)", "Saprospira grandis (strain Lewin)")"f__Saprospiraceae")"o__Chitinophagales", ("Amoebophilus asiaticus (strain 5a2)", "Bernardetia litoralis (strain ATCC 23117 / DSM 6794 / NBRC 15988 / NCIMB 1366 / Fx l1 / Sio-4)", ("Belliella baltica (strain DSM 15883 / CIP 108006 / LMG 21964 / BA134)", "Cyclobacterium marinum (strain ATCC 25205 / DSM 745 / LMG 13164 / NCIMB 1802)", "Echinicola vietnamensis (strain DSM 17526 / LMG 23754 / KMM 6221)", "Marivirga tractuosa (strain ATCC 23168 / DSM 4126 / NBRC 15989 / NCIMB 1408 / VKM B-1430 / H-43)", "Roseivirga ehrenbergii (strain DSM 102268 / JCM 13514 / KCTC 12282 / NCIMB 14502 / KMM 6017)")"f__Cyclobacteriaceae", "Cytophaga hutchinsonii (strain ATCC 33406 / DSM 1761 / CIP 103989 / NBRC 15051 / NCIMB 9469 / D465)", ("Dyadobacter fermentans (strain ATCC 700827 / DSM 18053 / CIP 107007 / KCTC 52180 / NS114)", "Emticicia oligotrophica (strain DSM 17448 / CIP 109782 / MTCC 6937 / GPTSA100-15)", "Leadbetterella byssophila (strain DSM 17132 / JCM 16389 / KACC 11308 / NBRC 106382 / 4M15)", "Runella slithyformis (strain ATCC 29530 / DSM 19594 / LMG 11500 / NCIMB 11436 / LSU 4)", "Spirosoma linguale (strain ATCC 33905 / DSM 74 / LMG 10896)")"f__Spirosomaceae")"o__Cytophagales", ((("Blattabacterium sp. subsp. Blattella germanica (strain Bge)", "Blattabacterium sp. subsp. Periplaneta americana (strain BPLAN)")"g__Blattabacterium", "Sulcia muelleri (strain CARI)")"f__Blattabacteriaceae", "Fluviicola taffensis (strain DSM 16823 / NCIMB 13979 / RW262)", ("Aequorivita sublithincola (strain DSM 14238 / LMG 21431 / ACAM 643 / 9-3)", ("Capnocytophaga canimorsus (strain 5)", "Capnocytophaga gingivalis", "Capnocytophaga ochracea (strain ATCC 27872 / DSM 7271 / JCM 12966 / NCTC 12371 / VPI 2845)")"g__Capnocytophaga", ("Cellulophaga algicola (strain DSM 14237 / IC166 / ACAM 630)", "Cellulophaga lytica (strain ATCC 23178 / DSM 7489 / JCM 8516 / NBRC 14961 / NCIMB 1423 / VKM B-1433 / Cy l20)")"g__Cellulophaga", "Croceibacter atlanticus (strain ATCC BAA-628 / HTCC2559 / KCTC 12090)", "Dokdonia sp. (strain 4H-3-7-5)", ("Flavobacterium branchiophilum (strain FL-15)", "Flavobacterium columnare (strain ATCC 49512 / CIP 103533 / TG 44/87)", "Flavobacterium frigoris (strain PS1)", "Flavobacterium indicum (strain DSM 17447 / CIP 109464 / GPTSA100-9)", "Flavobacterium johnsoniae (strain ATCC 17061 / DSM 2064 / JCM 8514 / NBRC 14942 / NCIMB 11054 / UW101)", "Flavobacterium psychrophilum (strain ATCC 49511 / DSM 21280 / CIP 103535 / JIP02/86)", "Flavobacterium sp. (strain CF136)")"g__Flavobacterium", "Formosa agariphila (strain DSM 15362 / KCTC 12365 / LMG 23005 / KMM 3901 / M-2Alg 35-1)", "Gramella forsetii (strain KT0803)", "Lacinutrix sp. (strain 5H-3-7-4)", "Leeuwenhoekiella blandensis (strain CECT 7118 / CCUG 51940 / MED217)", "Flavobacteria bacterium (strain MS024-2A)", "Maribacter sp. (strain HTCC2170 / KCCM 42371)", "Muricauda ruestringensis (strain DSM 13258 / CIP 107369 / LMG 19739 / B1)", ("Nonlabens dokdonensis (strain DSM 17205 / KCTC 12402 / DSW-6)", "Flavobacteria bacterium (strain BBFL7)")"g__Nonlabens", "Psychroflexus torquis (strain ATCC 700755 / ACAM 623)", "Robiginitalea biformata (strain ATCC BAA-864 / HTCC2501 / KCTC 12146)", "Zobellia galactanivorans (strain DSM 12802 / CCUG 47099 / CIP 106680 / NCIMB 13871 / Dsij)", "Zunongwangia profunda (strain DSM 18752 / CCTCC AB 206139 / SM-A87)")"f__Flavobacteriaceae", "Owenweeksia hongkongensis (strain DSM 17368 / CIP 108786 / JCM 12287 / NRRL B-23963 / UST20020801)", ("Chryseobacterium sp. (strain P1-3)", "Flavobacteriaceae bacterium (strain 3519-10)", "Ornithobacterium rhinotracheale (strain ATCC 51463 / DSM 15997 / CCUG 23171 / CIP 104009 / LMG 9086)", "Riemerella anatipestifer (strain RA-GD)", "Weeksella virosa (strain ATCC 43766 / DSM 16922 / JCM 21250 / CCUG 30538 / CDC 9751 / IAM 14551 / NBRC 16016 / NCTC 11634 / CL345/78)")"f__Weeksellaceae")"o__Flavobacteriales", ("Pedobacter heparinus (strain ATCC 13125 / DSM 2366 / CIP 104194 / JCM 7457 / NBRC 12017 / NCIMB 9290 / NRRL B-14731 / HIM 762-3)", "Pseudopedobacter saltans (strain ATCC 51119 / DSM 12145 / JCM 21818 / CCUG 39354 / LMG 10337 / NBRC 100064 / NCIMB 13643)", "Sphingobacterium sp. (strain 21)", "Solitalea canadensis (strain ATCC 29591 / DSM 3403 / NBRC 15130 / NCIMB 12057 / USAM 9D)")"f__Sphingobacteriaceae")"c__Bacteroidia", ((("Chlorobaculum parvum (strain DSM 263 / NCIMB 8327)", "Chlorobaculum tepidum (strain ATCC 49652 / DSM 12025 / NBRC 103806 / TLS)")"g__Chlorobaculum", ("Chlorobium chlorochromatii (strain CaD3)", "Chlorobium limicola (strain DSM 245 / NBRC 103803 / 6330)", "Chlorobium luteolum (strain DSM 273 / BCRC 81028 / 2530)", "Chlorobium phaeobacteroides (strain DSM 266)", "Pelodictyon phaeoclathratiforme (strain DSM 5477 / BU-1)", "Chlorobium phaeovibrioides (strain DSM 265 / 1930)")"g__Chlorobium", "Chlorobium phaeobacteroides (strain BS1)", "Prosthecochloris aestuarii (strain DSM 271 / SK 413)")"f__Chlorobiaceae", "Chloroherpeton thalassium (strain ATCC 35110 / GB-78)")"o__Chlorobiales", ("Ignavibacterium album (strain DSM 19864 / JCM 16511 / NBRC 101810 / Mat9-16)", "Melioribacter roseus (strain JCM 17771 / P3M-2)")"o__Ignavibacteriales", "Bacteroidetes bacterium MAG_11", "Chlorobi bacterium Kalu_18-Q3-R12-55_MAXAC.169", "Candidatus Kryptobacter tengchongensis JGI-3", ("Rhodothermus marinus (strain ATCC 43812 / DSM 4252 / R-10)", ("Salinibacter ruber (strain DSM 13855 / M31)", "Salinibacter ruber (strain M8)")"s__Salinibacter ruber")"o__Rhodothermales", "Ignavibacteria bacterium Vibo_18-Q3-R45-57_BATAC.435", "Ignavibacteriales bacterium NC_groundwater_1911_Pr3_S2p5_40_15")"p__Bacteroidota", ("Halobacteriovorax marinus (strain ATCC BAA-682 / DSM 15412 / SJ)", "Bdellovibrio bacteriovorus (strain ATCC 15356 / DSM 50701 / NCIMB 9529 / HD100)", "Bdellovibrionales bacterium SZAS-2", "Deltaproteobacteria bacterium NC_groundwater_823_Pr1_B-0.1um_55_34", ("Candidatus Micrarchaeota archaeon B47_G15", "Fluviispira sanaruensis")"f__Silvanigrellaceae", "Deltaproteobacteria bacterium UWPOB_DELTA4", "Bdellovibrionales bacterium SZAS-4", "Deltaproteobacteria bacterium RIFOXYA12_FULL_61_11 none")"p__Bdellovibrionota", "bacterium new MAG-396", "Deltaproteobacteria bacterium GWA2_38_16 none", "Candidatus Bipolaricaulis sibiricus Ch78", "Candidatus Omnitrophica bacterium Modern_marine.mb.319", ("Elusimicrobia bacterium HGW-Elusimicrobia-2", "Elusimicrobia bacterium Zod_Metabat.862")"p__CG03", "Deltaproteobacteria bacterium M_MetaBat.58", "Nitrospirae bacterium CG2_30_70_394", "bacterium MAG_59", ("candidate division CSSED10-310 bacterium Zod_Metabat.419", "Candidatus Schekmanbacteria bacterium NC_groundwater_415_Ag_B-0.1um_66_15", "bacterium Zod_Metabat.886")"p__CSSED10-310", "Caldisericum exile (strain DSM 21853 / NBRC 104410 / AZM16c01)", "Caldithrix abyssi", "bacterium HR19 HRbin19", (((("Aliarcobacter butzleri (strain RM4018)", "Arcobacter nitrofigilis (strain ATCC 33309 / DSM 7299 / CCUG 15893 / LMG 7604 / NCTC 12251 / CI)")"f__Arcobacteraceae", ("Campylobacter fetus subsp. fetus (strain 82-40)", ("Campylobacter concisus (strain 13826)", "Campylobacter curvus (strain 525.92)")"g__Campylobacter_A", "Campylobacter hominis (strain ATCC BAA-381 / LMG 19568 / NCTC 13146 / CH001A)", (("Campylobacter jejuni (strain RM1221)", "Campylobacter jejuni subsp. doylei (strain ATCC BAA-1458 / RM4099 / 269.97)", "Campylobacter jejuni subsp. jejuni (strain IA3902)", "Campylobacter jejuni subsp. jejuni (strain S3)", "Campylobacter jejuni subsp. jejuni serotype HS21 (strain M1 / 99/308)", "Campylobacter jejuni subsp. jejuni serotype HS:41 (strain ICDCCJ07001)", "Campylobacter jejuni subsp. jejuni serotype O:2 (strain ATCC 700819 / NCTC 11168)", "Campylobacter jejuni subsp. jejuni serotype O:23/36 (strain 81-176)", "Campylobacter jejuni subsp. jejuni serotype O:6 (strain 81116 / NCTC 11828)")"s__Campylobacter_D jejuni", "Campylobacter lari (strain RM2100 / D67 / ATCC BAA-1060)")"g__Campylobacter_D")"f__Campylobacteraceae", (("Helicobacter acinonychis (strain Sheeba)", ("Helicobacter pylori (strain ATCC 700392 / 26695)", "Helicobacter pylori (strain B38)", "Helicobacter pylori (strain B8)", "Helicobacter pylori (strain G27)", "Helicobacter pylori (strain HPAG1)", "Helicobacter pylori (strain India7)", "Helicobacter pylori (strain Lithuania75)", "Helicobacter pylori (strain P12)")"s__Helicobacter pylori", ("Helicobacter pylori (strain 908)", "Helicobacter pylori (strain Gambia94/24)", "Helicobacter pylori (strain J99 / ATCC 700824)")"s__Helicobacter pylori_BU", ("Helicobacter pylori (strain 35A)", "Helicobacter pylori (strain 51)", "Helicobacter pylori (strain 52)", "Helicobacter pylori (strain Cuz20)", "Helicobacter pylori (strain F16)", "Helicobacter pylori (strain F30)", "Helicobacter pylori (strain F32)", "Helicobacter pylori (strain F57)", "Helicobacter pylori (strain PeCan4)", "Helicobacter pylori (strain Shi470)", "Helicobacter pylori (strain v225d)")"s__Helicobacter pylori_C", "Helicobacter pylori (strain SJM180)")"g__Helicobacter", ("Helicobacter cinaedi (strain PAGU611)", "Helicobacter hepaticus (strain ATCC 51449 / 3B1)")"g__Helicobacter_C", ("Helicobacter bizzozeronii (strain CIII-1)", "Helicobacter felis (strain ATCC 49179 / NCTC 12436 / CS1)")"g__Helicobacter_E", "Helicobacter mustelae (strain ATCC 43772 / LMG 18044 / NCTC 12198 / 12198)", "Wolinella succinogenes (strain ATCC 29543 / DSM 1740 / LMG 7466 / NCTC 11488 / FDC 602W)")"f__Helicobacteraceae", "Nitratiruptor sp. (strain SB155-2)", ("Sulfuricurvum kujiense (strain ATCC BAA-921 / DSM 16994 / JCM 11577 / YK-1)", ("Sulfurimonas autotrophica (strain ATCC BAA-671 / DSM 16294 / JCM 11897 / OK10)", "Sulfurimonas denitrificans (strain ATCC 33889 / DSM 1251)")"g__Sulfurimonas")"f__Sulfurimonadaceae", ("Sulfurospirillum barnesii (strain ATCC 700032 / DSM 10660 / SES-3)", "Sulfurospirillum deleyianum (strain ATCC 51133 / DSM 6946 / 5175)")"g__Sulfurospirillum", ("Nitratifractor salsuginis (strain DSM 16511 / JCM 12458 / E9I37-1)", "Sulfurovum sp. (strain NBC37-1)")"f__Sulfurovaceae")"o__Campylobacterales", "Nautilia profundicola (strain ATCC BAA-1463 / DSM 18972 / AmH)")"c__Campylobacteria", "Hippea maritima (strain ATCC 700847 / DSM 10411 / MH2)")"p__Campylobacterota", ((("Chlamydia muridarum (strain MoPn / Nigg)", ("Chlamydia trachomatis (strain D/UW-3/Cx)", "Chlamydia trachomatis (strain L2c)", "Chlamydia trachomatis serovar A (strain A2497)", "Chlamydia trachomatis serovar A (strain ATCC VR-571B / DSM 19440 / HAR-13)", "Chlamydia trachomatis serovar B (strain Jali20/OT)", "Chlamydia trachomatis serovar B (strain TZ1A828/OT)", "Chlamydia trachomatis serovar D (strain D-EC)", "Chlamydia trachomatis serovar D (strain D-LC)", "Chlamydia trachomatis serovar E (strain E/11023)", "Chlamydia trachomatis serovar E (strain E/150)", "Chlamydia trachomatis serovar E (strain Sweden2)", "Chlamydia trachomatis serovar G (strain G/11074)", "Chlamydia trachomatis serovar G (strain G/11222)", "Chlamydia trachomatis serovar G (strain G/9301)", "Chlamydia trachomatis serovar G (strain G/9768)", "Chlamydia trachomatis serovar L2 (strain 434/Bu / ATCC VR-902B)", "Chlamydia trachomatis serovar L2b (strain UCH-1/proctitis)")"s__Chlamydia trachomatis")"g__Chlamydia", ("Chlamydia abortus (strain DSM 27085 / S26/3)", "Chlamydia caviae (strain ATCC VR-813 / DSM 19441 / 03DC25 / GPIC)", "Chlamydia felis (strain Fe/C-56)", "Chlamydia pecorum (strain ATCC VR-628 / E58)", ("Chlamydia pneumoniae CWL029", "Chlamydophila pneumoniae (strain LPCoLN)")"s__Chlamydophila pneumoniae", ("Chlamydia psittaci (strain RD1)", "Chlamydophila psittaci (strain ATCC VR-125 / 6BC)")"s__Chlamydophila psittaci")"g__Chlamydophila")"f__Chlamydiaceae", ("Parachlamydia acanthamoebae (strain UV7)", "Protochlamydia amoebophila (strain UWE25)")"f__Parachlamydiaceae", "Simkania negevensis (strain ATCC VR-1471 / Z)", "Waddlia chondrophila (strain ATCC VR-1470 / WSU 86-1044)")"o__Chlamydiales", (("Anaerolinea thermophila (strain DSM 14523 / JCM 11388 / NBRC 100420 / UNI-1)", "Caldilinea aerophila (strain DSM 14535 / JCM 11387 / NBRC 104270 / STL-6-O1)")"c__Anaerolineae", ((("Chloroflexus aggregans (strain MD-66 / DSM 9485)", ("Chloroflexus aurantiacus (strain ATCC 29364 / DSM 637 / Y-400-fl)", "Chloroflexus aurantiacus (strain ATCC 29366 / DSM 635 / J-10-fl)")"s__Chloroflexus aurantiacus")"g__Chloroflexus", "Herpetosiphon aurantiacus (strain ATCC 23779 / DSM 785 / 114-95)", ("Roseiflexus castenholzii (strain DSM 13941 / HLO8)", "Roseiflexus sp. (strain RS-1)")"g__Roseiflexus")"o__Chloroflexales", "Thermobaculum terrenum (strain ATCC BAA-798 / YNP1)", ("Sphaerobacter thermophilus (strain DSM 20745 / S 6022)", "Thermomicrobium roseum (strain ATCC 27502 / DSM 5159 / P-2)")"f__Thermomicrobiaceae")"c__Chloroflexia", "Chloroflexi bacterium NC_groundwater_1535_Pr4_S-0.65um_62_11", (("Dehalococcoides mccartyi (strain ATCC BAA-2266 / KCTC 15142 / 195)", "Dehalococcoides mccartyi (strain VS)", ("Dehalococcoides mccartyi (strain ATCC BAA-2100 / JCM 16839 / KCTC 5957 / BAV1)", "Dehalococcoides mccartyi (strain CBDB1)", "Dehalococcoides mccartyi (strain GT)")"s__Dehalococcoides mccartyi_B")"g__Dehalococcoides", "Dehalogenimonas lykanthroporepellens (strain ATCC BAA-1523 / JCM 15061 / BL-DC-9)")"f__Dehalococcoidaceae", "Chloroflexi bacterium FW602_bin.22", "Ktedonosporobacter rubrisoli", "Chloroflexi bacterium MAG002", "Chloroflexi bacterium SB0661_bin_6", "Chloroflexi bacterium RRmetagenome_bin17", "Chloroflexi bacterium Baikal-deep-G117")"p__Chloroflexota", "Desulfurispirillum indicum (strain ATCC BAA-1389 / DSM 22839 / S5)", "Cloacimonas acidaminovorans (strain Evry)", "Coprothermobacter proteolyticus (strain ATCC 35245 / DSM 5265 / OCM 4 / BT)", ((("Chamaesiphon minutus (strain ATCC 27169 / PCC 6605)", "Chroococcidiopsis thermalis (strain PCC 7203)", ("Cyanobacterium stanieri (strain ATCC 29140 / PCC 7202)", "Synechococcus sp. (strain ATCC 27264 / PCC 7002 / PR-6)", "Cyanobacterium aponinum (strain PCC 10605)")"f__Cyanobacteriaceae", ("Arthrospira platensis (strain NIES-39 / IAM M-135)", "Lyngbya sp. (strain PCC 8106)", "Trichodesmium erythraeum (strain IMS101)")"f__Microcoleaceae", (("Gloeothece citriformis (strain PCC 7424)", "Gloeothece verrucosa (strain PCC 7822)")"g__Gloeothece", "Microcystis aeruginosa (strain NIES-843)")"f__Microcystaceae", ("Atelocyanobacterium thalassa (isolate ALOHA)", "Crocosphaera subtropica (strain ATCC 51142 / BH68)", ("Rippkaea orientalis (strain PCC 8801)", "Rippkaea orientalis (strain PCC 8802)")"s__Rippkaea orientalis", "Synechocystis sp. (strain PCC 6803 / Kazusa)")"f__Microcystaceae_A", ("Anabaena cylindrica (strain ATCC 27899 / PCC 7122)", "Nostoc punctiforme (strain ATCC 29133 / PCC 73102)", ("Nostoc sp. (strain PCC 7120 / SAG 25.82 / UTEX 2576)", "Nostoc sp. (strain ATCC 29411 / PCC 7524)", "Trichormus variabilis (strain ATCC 29413 / PCC 7937)")"g__Trichormus", "Nostoc azollae (strain 0708)")"f__Nostocaceae", "Halothece sp. (strain PCC 7418)", "Stanieria cyanosphaera (strain ATCC 29371 / PCC 7437)")"o__Cyanobacteriales", "Gloeobacter violaceus (strain ATCC 29082 / PCC 7421)", ("Cyanobium gracile (strain ATCC 27147 / PCC 6307)", "Prochlorococcus marinus (strain SARG / CCMP1375 / SS120)", ("Prochlorococcus marinus (strain MIT 9215)", "Prochlorococcus marinus (strain MIT 9301)", "Prochlorococcus marinus (strain MIT 9312)", "Prochlorococcus marinus (strain AS9601)", "Prochlorococcus marinus (strain MIT 9515)", "Prochlorococcus marinus subsp. pastoris (strain CCMP1986 / NIES-2087 / MED4)")"g__Prochlorococcus_A", ("Prochlorococcus marinus (strain NATL1A)", "Prochlorococcus marinus (strain NATL2A)")"s__Prochlorococcus_B marinus_B", ("Prochlorococcus marinus (strain MIT 9303)", "Prochlorococcus marinus (strain MIT 9313)")"s__Prochlorococcus_C marinus_B", "Prochlorococcus marinus (strain MIT 9211)", "Synechococcus sp. (strain RCC307)", ("Synechococcus sp. (strain CC9311)", "Synechococcus sp. (strain WH7803)", "Synechococcus sp. (strain WH7805)")"g__Synechococcus_C", ("Synechococcus sp. (strain CC9902)", "Synechococcus sp. (strain CC9605)", "Parasynechococcus marenigrum (strain WH8102)")"g__Synechococcus_E")"f__Cyanobiaceae", ("Synechococcus sp. (strain JA-3-3Ab)", "Synechococcus sp. (strain JA-2-3B'a(2-13))")"g__JA-3-3Ab", "Synechococcus sp. (strain ATCC 29403 / PCC 7335)", ("Synechococcus elongatus (strain PCC 7942 / FACHB-805)", "Synechococcus sp. (strain ATCC 27144 / PCC 6301 / SAUG 1402/1)")"s__Synechococcus elongatus", ("Acaryochloris marina (strain MBIC 11017)", "Cyanothece sp. (strain PCC 7425 / ATCC 29141)", "Synechococcus sp. (strain ATCC 27167 / PCC 6312)", "Thermosynechococcus vestitus (strain IAM M-273 / NIES-2133 / BP-1)")"f__Thermosynechococcaceae")"c__Cyanobacteriia", "bacterium BIN46", "Candidatus Obscuribacter sp. Fred_18-Q3-R57-64_MAXAC.356")"p__Cyanobacteria", "Firmicutes bacterium AS04akNAM_72", "bacterium AS04akNAM_5", ("Calditerrivibrio nitroreducens (strain DSM 19672 / NBRC 101217 / Yu37-1)", "Deferribacter desulfuricans (strain DSM 14783 / JCM 11476 / NBRC 101012 / SSM1)", "Denitrovibrio acetiphilus (strain DSM 12809 / NBRC 114555 / N2460)", "Flexistipes sinusarabici (strain ATCC 49648 / DSM 4947 / MAS 10)")"o__Deferribacterales", ((("Deinococcus deserti (strain DSM 17065 / CIP 109153 / LMG 22923 / VCD115)", "Deinococcus geothermalis (strain DSM 11300 / AG-3a)", "Deinococcus gobiensis (strain DSM 21396 / JCM 16679 / CGMCC 1.7299 / I-0)", "Deinococcus proteolyticus (strain ATCC 35074 / DSM 20540 / JCM 6276 / NBRC 101906 / NCIMB 13154 / VKM Ac-1939 / CCM 2703 / MRP)", "Deinococcus radiodurans (strain ATCC 13939 / DSM 20539 / JCM 16871 / LMG 4051 / NBRC 15346 / NCIMB 9279 / R1 / VKM B-1422)")"g__Deinococcus", "Deinococcus peraridilitoris (strain DSM 19664 / LMG 22246 / CIP 109416 / KR-200)", "Deinococcus maricopensis (strain DSM 21211 / LMG 22137 / NRRL B-23946 / LB-34)")"f__Deinococcaceae", ("Marinithermus hydrothermalis (strain DSM 14884 / JCM 11576 / T1)", "Oceanithermus profundus (strain DSM 14977 / NBRC 100410 / VKM B-2274 / 506)")"f__Marinithermaceae", ("Meiothermus ruber (strain ATCC 35948 / DSM 1279 / VKM B-1258 / 21)", "Meiothermus silvanus (strain ATCC 700542 / DSM 9946 / VI-R2)", ("Thermus thermophilus (strain ATCC 27634 / DSM 579 / HB8)", "Thermus thermophilus (strain ATCC BAA-163 / DSM 7039 / HB27)", "Thermus thermophilus (strain SG0.5JP17-16)")"s__Thermus thermophilus")"f__Thermaceae", "Truepera radiovictrix (strain DSM 17093 / CIP 108686 / LMG 22925 / RQ-24)")"o__Deinococcales", "Candidatus Delongbacteria bacterium ZodW_Metabat.17", "bacterium AalE_18-Q3-R2-46_BAT3C.1_cln", ("Syntrophaceae bacterium UWMA-0184", "Desulfarculus baarsii (strain ATCC 33931 / DSM 2075 / LMG 7858 / VKM B-1802 / 2st14)", "Desulfobacca acetoxidans (strain ATCC 700848 / DSM 11109 / ASRB2)", (("Desulfatibacillum aliphaticivorans", "Desulfatibacillum alkenivorans (strain AK-01)")"g__Desulfatibacillum", ("Desulforapulum autotrophicum (strain ATCC 43914 / DSM 3382 / VKM B-1955 / HRM2)", "Desulfobacula toluolica (strain DSM 7467 / Tol2)")"f__Desulfobacteraceae", "Desulfococcus oleovorans (strain DSM 6200 / JCM 39069 / Hxd3)")"o__Desulfobacterales", ("Desulfobulbus propionicus (strain ATCC 33891 / DSM 2032 / VKM B-1956 / 1pr3)", ("Desulfocapsa sulfexigens (strain DSM 10523 / SB164P1)", "Desulfotalea psychrophila (strain LSv54 / DSM 12343)")"f__Desulfocapsaceae", "Desulfurivibrio alkaliphilus (strain DSM 19089 / UNIQEM U267 / AHT2)")"o__Desulfobulbales", "Desulfomonile tiedjei (strain ATCC 49306 / DSM 6799 / DCB-1)", ("Syntrophotalea carbinolica (strain DSM 2380 / NBRC 103641 / GraBd1)", ((("Geobacter metallireducens (strain ATCC 53774 / DSM 7210 / GS-15)", ("Geobacter sulfurreducens (strain ATCC 51573 / DSM 12127 / PCA)", "Geobacter sulfurreducens (strain DL-1 / KN400)")"s__Geobacter sulfurreducens")"g__Geobacter", ("Citrifermentans bemidjiense (strain ATCC BAA-1014 / DSM 16622 / JCM 12645 / Bem)", "Geobacter sp. (strain M21)", "Geobacter sp. (strain M18)")"g__Geomonas", ("Geotalea daltonii (strain DSM 22248 / JCM 15807 / FRC-32)", "Geotalea uraniireducens (strain Rf4)")"g__Geotalea")"f__Geobacteraceae", ("Pelobacter propionicus (strain DSM 2379 / NBRC 103807 / OttBd1)", "Trichlorobacter lovleyi (strain ATCC BAA-1151 / DSM 17278 / SZ)")"f__Pseudopelobacteraceae")"o__Geobacterales")"c__Desulfuromonadia", "Dissulfurirhabdus thermomarina", "Deltaproteobacteria bacterium GWC2_55_46", "Deltaproteobacteria bacterium NC_groundwater_360_Ag_B-0.1um_69_10", "Deltaproteobacteria bacterium NC_groundwater_1540_Pr4_S-0.65um_55_10", "Proteobacteria bacterium C1.bin.36", "Proteobacteria bacterium SpSt-1152", "Syntrophus aciditrophicus (strain SB)", "Syntrophobacter fumaroxidans (strain DSM 10017 / MPOB)", ("Thermodesulfatator indicus (strain DSM 15286 / JCM 11887 / CIR29812)", "Thermodesulfobacterium geofontis (strain OPF15)")"o__Thermodesulfobacteriales", "Desulfobacterales bacterium NC_groundwater_1491_Pr4_B-0.1um_43_5", "Candidatus Zymogeniaceaea bacterium Zod_Metabat.1292")"p__Desulfobacterota", "Deltaproteobacteria bacterium NC_groundwater_25_Pr7_B-0.1um_64_59", "Candidatus Anaeroferrophillus wilburensis Zod_Metabat.940", "Candidatus Dadabacteria bacterium MH-Pat-all_metabat2_32", "Deltaproteobacteria bacterium NC_groundwater_1648_Pr3_B-0.1um_61_38", ("Desulfohalobium retbaense (strain ATCC 49708 / DSM 5692 / JCM 16813 / HR100)", "Desulfomicrobium baculatum (strain DSM 4028 / VKM B-1378 / X)", ("Desulfovibrio vulgaris (strain DSM 19637 / Miyazaki F)", "Desulfovibrio desulfuricans (strain ATCC 27774 / DSM 6949 / MB)", "Lawsonia intracellularis (strain PHE/MN1-00)", "Maridesulfovibrio salexigens (strain ATCC 14822 / DSM 2638 / NCIMB 8403 / VKM B-1763)", "Megalodesulfovibrio gigas (strain ATCC 19364 / DSM 1382 / NCIMB 9332 / VKM B-1759)", ("Desulfovibrio vulgaris (strain ATCC 29579 / DSM 644 / NCIMB 8303 / VKM B-1760 / Hildenborough)", "Desulfovibrio vulgaris (strain RCH1)", "Desulfovibrio vulgaris subsp. vulgaris (strain DP4)")"s__Nitratidesulfovibrio vulgaris", "Oleidesulfovibrio alaskensis (strain ATCC BAA-1058 / DSM 17464 / G20)", ("Pseudodesulfovibrio aespoeensis (strain ATCC 700646 / DSM 10631 / Aspo-2)", "Pseudodesulfovibrio piezophilus (strain DSM 21447 / JCM 15486 / C1TLV30)")"g__Pseudodesulfovibrio", "Solidesulfovibrio magneticus (strain ATCC 700980 / DSM 13731 / RS-1)")"f__Desulfovibrionaceae")"o__Desulfovibrionales", ("Dictyoglomus thermophilum (strain ATCC 35947 / DSM 3960 / H-6-12)", "Dictyoglomus turgidum (strain DSM 6724 / Z-1310)")"g__Dictyoglomus", "Candidatus Edwardsbacteria bacterium RifOxyA12_full_54_48 none", "Candidatus Eisenbacteria bacterium Fred_18-Q3-R57-64_MAXAC.354", ("Elusimicrobium minutum (strain Pei191)", "Endomicrobium trichonymphae", "Elusimicrobia bacterium Zod_Metabat.39")"p__Elusimicrobiota", ("Candidatus Eremiobacteraeota bacterium CP_BM_RX_R8_7", "Armatimonadetes bacterium NC_groundwater_315_Ag_B-0.1um_31_7", "Armatimonadetes bacterium NC_groundwater_316_Ag_B-0.1um_55_8", "Candidatus Eremiobacteraeota bacterium SCN18_25_8_15_R3_B_62_28")"p__Eremiobacterota", "candidate division FCPU426 bacterium Zod_Metabat.219", "Myxococcales bacterium AS27yjCOA_30", "Candidatus Fermentibacteria bacterium Zod_Metabat.355", ("Fibrobacter succinogenes (strain ATCC 19169 / S85)", "Candidatus Raymondbacteria bacterium RIFOXYA2_FULL_49_16 none")"p__Fibrobacterota", ((("Acholeplasma laidlawii (strain PG-8A)", ("Phytoplasma australiense", "Phytoplasma mali (strain AT)", "Onion yellows phytoplasma (strain OY-M)", "Aster yellows witches'-broom phytoplasma (strain AYWB)")"g__Phytoplasma")"f__Acholeplasmataceae", ("Alicyclobacillus acidocaldarius subsp. acidocaldarius (strain ATCC 27009 / DSM 446 / BCRC 14685 / JCM 5260 / KCTC 1825 / NBRC 15652 / NCIMB 11725 / NRRL B-14509 / 104-IA)", "Alicyclobacillus acidocaldarius (strain Tc-4-1)", "Alicyclobacillus acidoterrestris (strain ATCC 49025 / DSM 3922 / CIP 106132 / NCIMB 13137 / GD3B)")"g__Alicyclobacillus", (("Anoxybacillus flavithermus (strain DSM 21510 / WK1)", ("Geobacillus thermodenitrificans (strain NG80-2)", ("Geobacillus kaustophilus (strain HTA426)", "Geobacillus sp. (strain Y412MC61)")"s__Geobacillus thermoleovorans")"g__Geobacillus", (("Geobacillus sp. (strain Y4.1MC1)", "Parageobacillus thermoglucosidasius (strain C56-YS93)")"s__Parageobacillus thermoglucosidasius", "Geobacillus sp. (strain WCH70)")"g__Parageobacillus")"f__Anoxybacillaceae", ("Bacillus amyloliquefaciens (strain ATCC 23350 / DSM 7 / BCRC 11601 / CCUG 28519 / NBRC 15535 / NRRL B-14393 / F)", "Bacillus atrophaeus (strain 1942)", "Bacillus licheniformis (strain ATCC 14580 / DSM 13 / JCM 2505 / CCUG 7422 / NBRC 12200 / NCIMB 9375 / NCTC 10341 / NRRL NRS-1264 / Gibson 46)", "Bacillus pumilus (strain SAFR-032)", ("Bacillus spizizenii (strain ATCC 23059 / NRRL B-14472 / W23)", "Bacillus spizizenii (strain DSM 15029 / JCM 12233 / NBRC 101239 / NRRL B-23049 / TU-B-10)")"s__Bacillus spizizenii", ("Bacillus subtilis (strain 168)", "Bacillus subtilis (strain BSn5)")"s__Bacillus subtilis", "Bacillus velezensis (strain DSM 23117 / BGSC 10A6 / LMG 26770 / FZB42)")"g__Bacillus", (("Bacillus anthracis (strain A0248)", "Bacillus anthracis (strain CDC 684 / NRRL 3495)", "Bacillus anthracis str. 'Ames Ancestor'", "Bacillus cereus (strain 03BB102)", "Bacillus cereus (strain AH820)", "Bacillus cereus (strain ZK / E33L)", "Bacillus cereus var. anthracis (strain CI)", "Bacillus thuringiensis (strain Al Hakam)", "Bacillus thuringiensis subsp. konkukian (strain 97-27)")"s__Bacillus_A anthracis", ("Bacillus cereus (strain ATCC 14579 / DSM 31 / CCUG 7414 / JCM 2152 / NBRC 15305 / NCIMB 9373 / NCTC 2599 / NRRL B-3711)", "Bacillus cereus (strain B4264)", "Bacillus thuringiensis (strain BMB171)")"s__Bacillus_A cereus", "Bacillus cytotoxicus (strain DSM 22905 / CIP 110041 / 391-98 / NVH 391-98)", "Bacillus mycoides (strain KBAB4)", ("Bacillus cereus (strain AH187)", "Bacillus cereus (strain ATCC 10987 / NRS 248)", "Bacillus cereus (strain Q1)", "Bacillus thuringiensis subsp. finitimus (strain YBT-020)")"s__Bacillus_A paranthracis", "Bacillus cereus (strain G9842)")"g__Bacillus_A", ("Priestia megaterium (strain ATCC 12872 / QMB1551)", "Priestia megaterium (strain DSM 319 / IMG 1521)")"s__Priestia megaterium")"o__Bacillales", ("Lysinibacillus sphaericus (strain C3-41)", "Solibacillus silvestris (strain StLB046)")"f__Planococcaceae", ("Weizmannia coagulans (strain 2-6)", "Niallia circulans")"o__Bacillales_B", ("Amphibacillus xylanus (strain ATCC 51415 / DSM 6626 / JCM 7361 / LMG 17667 / NBRC 15112 / Ep01)", "Oceanobacillus iheyensis (strain DSM 14371 / CIP 107618 / JCM 11309 / KCTC 3954 / HTE831)")"f__Amphibacillaceae", (("Alkalihalobacillus clausii (strain KSM-K16)", "Alkalihalobacillus akibai (strain ATCC 43226 / DSM 21942 / CIP 109018 / JCM 9157 / 1139)", "Alkalihalobacillus halodurans (strain ATCC BAA-125 / DSM 18197 / FERM 7344 / JCM 9153 / C-125)", "Alkalihalobacillus pseudofirmus (strain ATCC BAA-2126 / JCM 17055 / OF4)")"f__Bacillaceae_D", ("Evansella cellulosilytica (strain ATCC 21833 / DSM 2522 / FERM P-1141 / JCM 9156 / N-4)", "Bacillus selenitireducens (strain ATCC 700615 / DSM 15326 / MLS10)")"f__Salisediminibacteriaceae")"o__Bacillales_H", "Brevibacillus brevis (strain 47 / JCM 6285 / NBRC 100599)", "Erysipelothrix rhusiopathiae (strain Fujisawa)", ("Exiguobacterium sp. (strain ATCC BAA-1283 / AT1b)", ("Exiguobacterium antarcticum (strain B7)", "Exiguobacterium sibiricum (strain DSM 17290 / CIP 109462 / JCM 13490 / 255-15)")"g__Exiguobacterium_A")"f__Exiguobacteraceae", "Kyrpidia tusciae (strain DSM 2912 / NBRC 15312 / T2)", ("Aerococcus urinae (strain ACS-120-V-Col10a)", "Carnobacterium sp. (strain 17-4)", (("Enterococcus faecalis (strain 62)", "Enterococcus faecalis (strain ATCC 47077 / OG1RF)", "Enterococcus faecalis (strain ATCC 700802 / V583)")"s__Enterococcus faecalis", (("Enterococcus faecium (strain ATCC BAA-472 / TX0016 / DO)", "Enterococcus faecium (strain Aus0004)")"s__Enterococcus_B faecium", "Enterococcus thailandicus")"g__Enterococcus_B", "Enterococcus italicus (strain DSM 15952 / CCUG 50447 / LMG 22039 / TP 1.5)", ("Melissococcus plutonius (strain ATCC 35311 / CIP 104052 / LMG 20360 / NCIMB 702443)", "Melissococcus plutonius (strain DAT561)")"s__Melissococcus plutonius", "Tetragenococcus halophilus (strain DSM 20338 / JCM 20259 / NCIMB 9735 / NBRC 12172)")"f__Enterococcaceae", ("Fructilactobacillus sanfranciscensis (strain TMW 1.1304)", (("Lacticaseibacillus casei (strain BD-II)", "Lacticaseibacillus paracasei (strain ATCC 334 / BCRC 17002 / CCUG 31169 / CIP 107868 / KCTC 3260 / NRRL B-441)")"s__Lacticaseibacillus paracasei", ("Lacticaseibacillus rhamnosus (strain ATCC 53103 / LMG 18243 / GG)", "Lacticaseibacillus rhamnosus (strain Lc 705)")"s__Lacticaseibacillus rhamnosus")"g__Lacticaseibacillus", ("Lactiplantibacillus plantarum (strain ATCC BAA-793 / NCIMB 8826 / WCFS1)", "Lactiplantibacillus plantarum (strain JDM1)", "Lactiplantibacillus plantarum (strain ST-III)")"s__Lactiplantibacillus plantarum", ("Lactobacillus acidophilus (strain ATCC 700396 / NCK56 / N2 / NCFM)", ("Lactobacillus amylovorus (strain GRL 1112)", "Lactobacillus amylovorus (strain GRL 1118)")"s__Lactobacillus amylovorus", "Lactobacillus crispatus (strain ST1)", ("Lactobacillus delbrueckii subsp. bulgaricus (strain 2038)", "Lactobacillus delbrueckii subsp. bulgaricus (strain ATCC 11842 / DSM 20081 / BCRC 10696 / JCM 1002 / NBRC 13953 / NCIMB 11778 / NCTC 12712 / WDCM 00102 / Lb 14)", "Lactobacillus delbrueckii subsp. bulgaricus (strain ATCC BAA-365 / Lb-18)", "Lactobacillus delbrueckii subsp. bulgaricus (strain ND02)")"s__Lactobacillus delbrueckii", "Lactobacillus gasseri (strain ATCC 33323 / DSM 20243 / BCRC 14619 / CIP 102991 / JCM 1131 / KCTC 3163 / NCIMB 11718 / NCTC 13722 / AM63)", "Lactobacillus helveticus (strain DPC 4571)", ("Lactobacillus johnsonii (strain CNCM I-12250 / La1 / NCC 533)", "Lactobacillus johnsonii (strain FI9785)")"s__Lactobacillus johnsonii", "Lactobacillus kefiranofaciens (strain ZW3)")"g__Lactobacillus", "Latilactobacillus sakei subsp. sakei (strain 23K)", "Lentilactobacillus buchneri (strain NRRL B-30929)", ("Leuconostoc carnosum (strain JB16)", "Leuconostoc citreum (strain KM20)", "Leuconostoc gelidum (strain JB7)", "Leuconostoc gelidum subsp. gasicomitatum (strain DSM 15947 / CCUG 46042 / CECT 5767 / JCM 12535 / LMG 18811 / NBRC 113245 / TB1-10)", "Leuconostoc sp. (strain C2)", "Leuconostoc mesenteroides subsp. mesenteroides (strain ATCC 8293 / DSM 20343 / BCRC 11652 / CCM 1803 / JCM 6124 / NCDO 523 / NBRC 100496 / NCIMB 8023 / NCTC 12954 / NRRL B-1118 / 37Y)")"g__Leuconostoc", "Levilactobacillus brevis (strain ATCC 367 / BCRC 12310 / CIP 105137 / JCM 1170 / LMG 11437 / NCIMB 947 / NCTC 947)", ("Ligilactobacillus ruminis (strain ATCC 27782 / RF3)", ("Ligilactobacillus salivarius (strain CECT 5713)", "Ligilactobacillus salivarius (strain UCC118)")"s__Ligilactobacillus salivarius")"g__Ligilactobacillus", (("Limosilactobacillus fermentum (strain CECT 5716 / Lc40)", "Limosilactobacillus fermentum (strain NBRC 3956 / LMG 18251)")"s__Limosilactobacillus fermentum", ("Limosilactobacillus reuteri (strain DSM 20016)", "Limosilactobacillus reuteri (strain JCM 1112)")"s__Limosilactobacillus reuteri", "Limosilactobacillus reuteri (strain ATCC 55730 / SD2112)")"g__Limosilactobacillus", "Oenococcus oeni (strain ATCC BAA-331 / PSU-1)", ("Pediococcus claussenii (strain ATCC BAA-344 / DSM 14800 / JCM 18046 / KCTC 3811 / P06)", "Pediococcus pentosaceus (strain ATCC 25745 / CCUG 21536 / LMG 10740 / 183-1w)")"g__Pediococcus", ("Weissella koreensis (strain KACC 15510)", "Weissella viridescens")"g__Weissella")"f__Lactobacillaceae", ("Listeria innocua serovar 6a (strain ATCC BAA-680 / CLIP 11262)", "Listeria ivanovii (strain ATCC BAA-678 / PAM 55)", ("Listeria monocytogenes serotype 1/2a (strain 08-5923)", "Listeria monocytogenes serotype 1/2a (strain 10403S)", "Listeria monocytogenes serovar 1/2a (strain ATCC BAA-679 / EGD-e)")"s__Listeria monocytogenes", ("Listeria monocytogenes serotype 4b (strain CLIP80459)", "Listeria monocytogenes serotype 4b (strain F2365)")"s__Listeria monocytogenes_B", ("Listeria monocytogenes serotype 4a (strain HCC23)", "Listeria monocytogenes serotype 4a (strain L99)", "Listeria monocytogenes serotype 4a (strain M7)")"s__Listeria monocytogenes_C", "Listeria seeligeri serovar 1/2b (strain ATCC 35967 / DSM 20751 / CCM 3970 / CIP 100100 / NCTC 11856 / SLCC 3954 / 1120)", "Listeria welshimeri serovar 6b (strain ATCC 35897 / DSM 20650 / CIP 8149 / NCTC 11857 / SLCC 5334 / V8)")"g__Listeria", ((("Lactococcus lactis subsp. cremoris (strain MG1363)", "Lactococcus lactis subsp. cremoris (strain NZ9000)", "Lactococcus lactis subsp. cremoris (strain SK11)")"s__Lactococcus cremoris", ("Lactococcus garvieae (strain ATCC 49156 / DSM 6783 / JCM 8735 / NCIMB 13208 / YT-3)", "Lactococcus garvieae (strain Lg2)")"s__Lactococcus garvieae", ("Lactococcus lactis subsp. lactis (strain CV56)", "Lactococcus lactis subsp. lactis (strain IL1403)", "Lactococcus lactis subsp. lactis (strain KF147)")"s__Lactococcus lactis")"g__Lactococcus", (("Streptococcus agalactiae serotype III (strain NEM316)", "Streptococcus agalactiae serotype Ia (strain ATCC 27591 / A909 / CDC SS700)", "Streptococcus agalactiae serotype Ia (strain GD201008-001)", "Streptococcus agalactiae serotype V (strain ATCC BAA-611 / 2603 V/R)")"s__Streptococcus agalactiae", ("Streptococcus dysgalactiae subsp. equisimilis (strain ATCC 12394 / D166B)", "Streptococcus dysgalactiae subsp. equisimilis (strain GGS_124)")"s__Streptococcus dysgalactiae", ("Streptococcus equi subsp. equi (strain 4047)", "Streptococcus equi subsp. zooepidemicus (strain ATCC 35246 / C74-63)", "Streptococcus equi subsp. zooepidemicus (strain H70)", "Streptococcus equi subsp. zooepidemicus (strain MGCS10565)")"s__Streptococcus equi", ("Streptococcus gallolyticus (strain ATCC 43143 / F-1867)", "Streptococcus gallolyticus (strain ATCC BAA-2069)", "Streptococcus gallolyticus (strain UCN34)")"s__Streptococcus gallolyticus", "Streptococcus gordonii (strain Challis / ATCC 35105 / BCRC 15272 / CH1 / DL1 / V288)", "Streptococcus infantarius (strain CJ18)", "Streptococcus intermedius (strain JTH08)", "Streptococcus macedonicus (strain ACA-DC 198)", "Streptococcus mitis (strain B6)", ("Streptococcus mutans serotype c (strain ATCC 700610 / UA159)", "Streptococcus mutans serotype c (strain NN2025)")"s__Streptococcus mutans", "Streptococcus oralis (strain Uo5)", "Streptococcus parauberis (strain KCTC 11537)", "Streptococcus pasteurianus (strain ATCC 43144 / JCM 5346 / CDC 1723-81)", ("Streptococcus pneumoniae (strain 670-6B)", "Streptococcus pneumoniae (strain 70585)", "Streptococcus pneumoniae (strain ATCC 700669 / Spain 23F-1)", "Streptococcus pneumoniae (strain ATCC BAA-255 / R6)", "Streptococcus pneumoniae (strain CGSP14)", "Streptococcus pneumoniae (strain Hungary19A-6)", "Streptococcus pneumoniae (strain JJA)", "Streptococcus pneumoniae (strain P1031)", "Streptococcus pneumoniae (strain ST556)", "Streptococcus pneumoniae (strain Taiwan19F-14)", "Streptococcus pneumoniae serotype 1 (strain INV104)", "Streptococcus pneumoniae serotype 14 (strain INV200)", "Streptococcus pneumoniae serotype 19F (strain G54)", "Streptococcus pneumoniae serotype 2 (strain D39 / NCTC 7466)", "Streptococcus pneumoniae serotype 3 (strain OXC141)", "Streptococcus pneumoniae serotype 4 (strain ATCC BAA-334 / TIGR4)", "Streptococcus pneumoniae serotype A19 (strain TCH8431)")"s__Streptococcus pneumoniae", "Streptococcus pseudopneumoniae (strain IS7493)", ("Streptococcus pyogenes M1 GAS", "Streptococcus pyogenes serotype M12 (strain MGAS2096)", "Streptococcus pyogenes serotype M12 (strain MGAS9429)", "Streptococcus pyogenes serotype M18 (strain MGAS8232)", "Streptococcus pyogenes serotype M2 (strain MGAS10270)", "Streptococcus pyogenes serotype M28 (strain MGAS6180)", "Streptococcus pyogenes serotype M3 (strain ATCC BAA-595 / MGAS315)", "Streptococcus pyogenes serotype M3 (strain SSI-1)", "Streptococcus pyogenes serotype M4 (strain MGAS10750)", "Streptococcus pyogenes serotype M49 (strain NZ131)", "Streptococcus pyogenes serotype M5 (strain Manfredo)", "Streptococcus pyogenes serotype M6 (strain ATCC BAA-946 / MGAS10394)")"s__Streptococcus pyogenes", ("Streptococcus salivarius (strain 57.I)", "Streptococcus salivarius (strain CCHSS3)", "Streptococcus salivarius (strain JIM8777)")"s__Streptococcus salivarius", "Streptococcus sanguinis (strain SK36)", ("Streptococcus suis (strain 05ZYH33)", "Streptococcus suis (strain 98HAH33)", "Streptococcus suis (strain BM407)", "Streptococcus suis (strain GZ1)", "Streptococcus suis (strain JS14)", "Streptococcus suis (strain P1/7)", "Streptococcus suis (strain SC84)")"s__Streptococcus suis", ("Streptococcus thermophilus (strain ATCC BAA-250 / LMG 18311)", "Streptococcus thermophilus (strain ATCC BAA-491 / LMD-9)", "Streptococcus thermophilus (strain CNRZ 1066)", "Streptococcus thermophilus (strain ND03)")"s__Streptococcus thermophilus", "Streptococcus uberis (strain ATCC BAA-854 / 0140J)")"g__Streptococcus")"f__Streptococcaceae")"o__Lactobacillales", (((("Mycoplasma hyopneumoniae (strain 168)", "Mycoplasma hyopneumoniae (strain 232)", "Mycoplasma hyopneumoniae (strain 7448)", "Mycoplasma hyopneumoniae (strain J / ATCC 25934 / NCTC 10110)")"s__Mesomycoplasma hyopneumoniae", ("Mycoplasma hyorhinis (strain HUB-1)", "Mycoplasma hyorhinis (strain MCLD)")"s__Mesomycoplasma hyorhinis")"g__Mesomycoplasma", ("Mycoplasma arthritidis (strain 158L3-1)", "Mycoplasma hominis (strain ATCC 23114 / NBRC 14850 / NCTC 10111 / PG21)")"g__Metamycoplasma", "Mycoplasma mobile (strain ATCC 43663 / 163K / NCTC 11711)", ("Mycoplasmopsis agalactiae (strain NCTC 10123 / CIP 59.7 / PG2)", ("Mycoplasmopsis bovis (strain ATCC 25523 / DSM 22781 / NCTC 10131 / PG45)", "Mycoplasmopsis bovis (strain Hubei-1)")"s__Mycoplasmopsis bovis", ("Mycoplasmopsis fermentans (strain ATCC 19989 / NBRC 14854 / NCTC 10117 / PG18)", "Mycoplasmopsis fermentans (strain JER)", "Mycoplasmopsis fermentans (strain M64)")"s__Mycoplasmopsis fermentans")"g__Mycoplasmopsis", ("Mycoplasma crocodyli (strain ATCC 51981 / MP145)", "Mycoplasmopsis cynos (strain C142)", "Mycoplasmopsis synoviae (strain 53)")"g__Mycoplasmopsis_A", "Mycoplasmopsis pulmonis (strain UAB CTIP)")"f__Metamycoplasmataceae", ("Mesoplasma florum (strain ATCC 33453 / NBRC 100688 / NCTC 11704 / L1)", ("Mycoplasma capricolum subsp. capricolum (strain California kid / ATCC 27343 / NCTC 10154)", ("Mycoplasma leachii (strain 99/014/6)", "Mycoplasma leachii (strain DSM 21131 / NCTC 10133 / N29 / PG50)")"s__Mycoplasma leachii", ("Mycoplasma mycoides subsp. mycoides SC (strain Gladysdale)", "Mycoplasma mycoides subsp. mycoides SC (strain PG1)")"s__Mycoplasma mycoides", "Mycoplasma putrefaciens (strain ATCC 15718 / NCTC 10155 / C30 KS-1 / KS-1)")"g__Mycoplasma")"f__Mycoplasmataceae", (("Mycoplasma haemolamae (strain Purdue)", ("Mycoplasma suis (strain Illinois)", "Mycoplasma suis (strain KI_3806)")"s__Eperythrozoon_A suis", "Mycoplasma wenyonii (strain Massachusetts)")"g__Eperythrozoon_A", ("Mycoplasma haemocanis (strain Illinois)", ("Mycoplasma haemofelis (strain Langford 1)", "Mycoplasma haemofelis (strain Ohio2)")"s__Eperythrozoon_B haemofelis")"g__Eperythrozoon_B", "Mycoplasma penetrans (strain HF-2)", (("Mycoplasma gallisepticum (strain F)", "Mycoplasma gallisepticum (strain R(high / passage 156))", "Mycoplasma gallisepticum (strain R(low / passage 15 / clone 2))")"s__Mycoplasmoides gallisepticum", "Mycoplasma genitalium (strain ATCC 33530 / G-37 / NCTC 10195)", ("Mycoplasma pneumoniae (strain ATCC 15531 / DSM 22911 / NBRC 14401 / NCTC 10119 / FH)", "Mycoplasma pneumoniae (strain ATCC 29342 / M129)")"s__Mycoplasmoides pneumoniae")"g__Mycoplasmoides", (("Ureaplasma parvum serovar 3 (strain ATCC 27815 / 27 / NCTC 11736)", "Ureaplasma parvum serovar 3 (strain ATCC 700970)")"s__Ureaplasma parvum", "Ureaplasma urealyticum serovar 10 (strain ATCC 33699 / Western)")"g__Ureaplasma")"f__Mycoplasmoidaceae")"o__Mycoplasmatales", ("Paenibacillus mucilaginosus (strain KNP414)", (("Geobacillus sp. (strain Y412MC10)", "Paenibacillus polymyxa (strain E681)", "Paenibacillus polymyxa (strain SC2)", "Paenibacillus terrae (strain HPL-003)")"g__Paenibacillus", "Paenibacillus sp. (strain JDR-2)", "Thermobacillus composti (strain DSM 18247 / JCM 13945 / KWC4)")"f__Paenibacillaceae")"o__Paenibacillales", ("Macrococcus caseolyticus (strain JCSC5402)", (("Staphylococcus aureus (strain 04-02981)", "Staphylococcus aureus (strain COL)", "Staphylococcus aureus (strain ECT-R 2)", "Staphylococcus aureus (strain ED98)", "Staphylococcus aureus (strain JH1)", "Staphylococcus aureus (strain JH9)", "Staphylococcus aureus (strain JKD6008)", "Staphylococcus aureus (strain JKD6159)", "Staphylococcus aureus (strain MRSA ST398 / isolate S0385)", "Staphylococcus aureus (strain MRSA252)", "Staphylococcus aureus (strain MSSA476)", "Staphylococcus aureus (strain MW2)", "Staphylococcus aureus (strain Mu3 / ATCC 700698)", "Staphylococcus aureus (strain Mu50 / ATCC 700699)", "Staphylococcus aureus (strain N315)", "Staphylococcus aureus (strain NCTC 8325 / PS 47)", "Staphylococcus aureus (strain Newman)", "Staphylococcus aureus (strain TCH60)", "Staphylococcus aureus (strain TW20 / 0582)", "Staphylococcus aureus (strain USA300 / TCH1516)", "Staphylococcus aureus (strain USA300)", "Staphylococcus aureus (strain bovine RF122 / ET3-1)", "Staphylococcus aureus subsp. aureus (strain ED133)")"s__Staphylococcus aureus", "Staphylococcus carnosus (strain TM300)", ("Staphylococcus epidermidis (strain ATCC 12228 / FDA PCI 1200)", "Staphylococcus epidermidis (strain ATCC 35984 / RP62A)")"s__Staphylococcus epidermidis", "Staphylococcus haemolyticus (strain JCSC1435)", "Staphylococcus hyicus", "Staphylococcus lugdunensis (strain HKU09-01)", ("Staphylococcus pseudintermedius (strain ED99)", "Staphylococcus pseudintermedius (strain HKU10-03)")"s__Staphylococcus pseudintermedius", "Staphylococcus saprophyticus subsp. saprophyticus (strain ATCC 15305 / DSM 20229 / NCIMB 8711 / NCTC 7292 / S-41)")"g__Staphylococcus")"f__Staphylococcaceae", "Thermoactinomyces vulgaris")"c__Bacilli", "Firmicutes bacterium Bu12")"p__Firmicutes", ("Firmicutes bacterium Ch29", ((("Acetivibrio clariflavus (strain DSM 19732 / NBRC 101661 / EBR45)", ("Acetivibrio thermocellus (strain ATCC 27405 / DSM 1237 / JCM 9322 / NBRC 103400 / NCIMB 10682 / NRRL B-4536 / VPI 7372)", "Acetivibrio thermocellus (strain DSM 1313 / LMG 6656 / LQ8)")"s__Hungateiclostridium thermocellum")"f__Acetivibrionaceae", "Ruminiclostridium cellulolyticum (strain ATCC 35319 / DSM 5812 / JCM 6584 / H10)")"o__Acetivibrionales", (("Clostridium beijerinckii (strain ATCC 51743 / NCIMB 8052)", "Clostridium botulinum (strain Alaska E43 / Type E3)", "Clostridium botulinum (strain Eklund 17B / Type B)")"g__Clostridium", ("Clostridium kluyveri (strain ATCC 8527 / DSM 555 / NCIMB 10680)", "Clostridium ljungdahlii (strain ATCC 55383 / DSM 13528 / PETC)")"g__Clostridium_B", ("Clostridium botulinum (strain 230613 / Type F)", "Clostridium botulinum (strain 657 / Type Ba4)", "Clostridium botulinum (strain ATCC 19397 / Type A)", "Clostridium botulinum (strain H04402 065 / Type A5)", "Clostridium botulinum (strain Hall / ATCC 3502 / NCTC 13319 / Type A)", "Clostridium botulinum (strain Kyoto / Type A2)", "Clostridium botulinum (strain Langeland / NCTC 10281 / Type F)", "Clostridium botulinum (strain Loch Maree / Type A3)", "Clostridium botulinum (strain Okra / Type B1)")"s__Clostridium_F botulinum", "Clostridium tetani (strain Massachusetts / E88)", "Clostridium novyi (strain NT)", "Clostridium cellulovorans (strain ATCC 35296 / DSM 3052 / OCM 3 / 743B)", ("Clostridium perfringens (strain 13 / Type A)", "Clostridium perfringens (strain ATCC 13124 / DSM 756 / JCM 1290 / NCIMB 6125 / NCTC 8237 / Type A)", "Clostridium perfringens (strain SM101 / Type A)")"s__Clostridium_P perfringens", ("Clostridium acetobutylicum (strain ATCC 824 / DSM 792 / JCM 1419 / LMG 5710 / VKM B-1787)", "Clostridium acetobutylicum (strain EA 2018)")"s__Clostridium_S acetobutylicum", "Arthromitus sp. (strain SFB-mouse-Japan)")"f__Clostridiaceae", "Acetobacterium woodii (strain ATCC 29683 / DSM 1030 / JCM 2381 / KCTC 1655 / WB1)", ("Cellulosilyticum lentocellum (strain ATCC 49066 / DSM 5427 / NCIMB 11756 / RHM5)", ("Agathobacter rectalis (strain ATCC 33656 / DSM 3377 / JCM 17463 / KCTC 5835 / VPI 0990)", "Anaerostipes hadrus", "Butyrivibrio proteoclasticus (strain ATCC 51982 / DSM 14932 / B316)", "Clostridium sp. (strain SY8519)", "Lachnoclostridium phytofermentans (strain ATCC 700394 / DSM 18823 / ISDg)", "Lachnospira eligens (strain ATCC 27750 / DSM 3376 / VPI C15-48 / C15-B4)", "Lacrimispora saccharolytica (strain ATCC 35040 / DSM 2544 / NRCC 2533 / WM1)", "Roseburia hominis (strain DSM 16839 / JCM 17582 / NCIMB 14029 / A2-183)")"f__Lachnospiraceae")"o__Lachnospirales", "Mahella australiensis (strain DSM 15567 / CIP 107919 / 50-1 BON)", ("Ethanoligenens harbinense (strain DSM 18485 / JCM 12961 / CGMCC 1.5033 / YUAN-3)", "Oscillibacter valericigenes (strain DSM 18026 / NBRC 101213 / Sjm18-20)", ("Clostridium sp. (strain ATCC 29733 / VPI C48-50)", "Ruminococcus albus (strain ATCC 27210 / DSM 20455 / JCM 14654 / NCDO 2250 / 7)", "Ruminococcus champanellensis (strain DSM 18848 / JCM 17042 / KCTC 15320 / 18P13)")"f__Ruminococcaceae")"o__Oscillospirales", (("Acetoanaerobium sticklandii (strain ATCC 12662 / DSM 519 / JCM 1433 / CCUG 9281 / NCIMB 10654 / HF)", "Filifactor alocis (strain ATCC 35896 / D40 B5)")"f__Filifactoraceae", ("Alkaliphilus metalliredigens (strain QYMF)", "Alkaliphilus oremlandii (strain OhILAs)")"f__Natronincolaceae", ("Clostridioides difficile (strain 630)", "Clostridioides difficile (strain R20291)")"s__Clostridioides difficile")"o__Peptostreptococcales", "Mageeibacillus indolicus (strain UPII9-5)", ("Gottschalkia acidurici (strain ATCC 7906 / DSM 604 / BCRC 14475 / CIP 104303 / KCTC 5404 / NCIMB 10678 / 9a)", ("Anaerococcus prevotii (strain ATCC 9321 / DSM 20548 / JCM 6508 / NCTC 11806 / PC1)", "Finegoldia magna (strain ATCC 29328 / DSM 20472 / WAL 2508)")"f__Peptoniphilaceae")"o__Tissierellales")"c__Clostridia", (("Caldicellulosiruptor kristjanssonii (strain ATCC 700853 / DSM 12137 / I77R1B)", "Caldicellulosiruptor bescii (strain ATCC BAA-1888 / DSM 6725 / Z-1320)", "Caldicellulosiruptor hydrothermalis (strain DSM 18901 / VKM B-2411 / 108)", "Caldicellulosiruptor kronotskyensis (strain DSM 18902 / VKM B-2412 / 2002)", "Caldicellulosiruptor obsidiansis (strain ATCC BAA-2073 / strain OB47)", "Caldicellulosiruptor owensensis (strain ATCC 700167 / DSM 13100 / OL)", "Caldicellulosiruptor saccharolyticus (strain ATCC 43494 / DSM 8903 / Tp8T 6331)")"g__Caldicellulosiruptor", ("Caldanaerobacter subterraneus subsp. tengcongensis (strain DSM 15242 / JCM 11007 / NBRC 100824 / MB4)", (("Thermoanaerobacter pseudethanolicus (strain ATCC 33223 / 39E)", "Thermoanaerobacter sp. (strain X513)", "Thermoanaerobacter sp. (strain X514)")"s__Thermoanaerobacter pseudethanolicus", ("Thermoanaerobacter italicus (strain DSM 9252 / Ab9)", "Thermoanaerobacter mathranii subsp. mathranii (strain DSM 11426 / CCUG 53645 / CIP 108742 / A3)")"s__Thermoanaerobacter thermocopriae")"g__Thermoanaerobacter", ("Thermoanaerobacterium saccharolyticum (strain DSM 8691 / JW/SL-YS485)", "Thermoanaerobacterium thermosaccharolyticum (strain ATCC 7956 / DSM 571 / NCIMB 9385 / NCA 3814 / NCTC 13789 / WDCM 00135 / 2032)", "Thermoanaerobacterium xylanolyticum (strain ATCC 49914 / DSM 7097 / LX-11)")"g__Thermoanaerobacterium")"f__Thermoanaerobacteraceae")"c__Thermoanaerobacteria", ("Tepidanaerobacter acetatoxydans (strain DSM 21804 / JCM 16047 / Re1)", "Thermosediminibacter oceani (strain ATCC BAA-1034 / DSM 16646 / JW/IW-1228P)")"o__Thermosediminibacterales")"p__Firmicutes_A", ((((("Desulfitobacterium dichloroeliminans (strain LMG P-21439 / DCA1)", ("Desulfitobacterium hafniense (strain DSM 10664 / DCB-2)", "Desulfitobacterium hafniense (strain Y51)")"s__Desulfitobacterium hafniense")"g__Desulfitobacterium", ("Desulfosporosinus acidiphilus (strain DSM 22704 / JCM 16185 / SJ4)", "Desulfosporosinus meridiei (strain ATCC BAA-275 / DSM 13257 / KCTC 12902 / NCIMB 13706 / S10)", "Desulfosporosinus orientis (strain ATCC 19365 / DSM 765 / NCIMB 8382 / VKM B-1628 / Singapore I)")"g__Desulfosporosinus")"f__Desulfitobacteriaceae", "Syntrophobotulus glycolicus (strain DSM 8271 / FlGlyR)")"o__Desulfitobacteriales", "Heliobacterium modesticaldum (strain ATCC 51547 / Ice1)")"c__Desulfitobacteriia", ("Desulforudis audaxviator (strain MP104C)", ("Desulfofarcimen acetoxidans (strain ATCC 49208 / DSM 771 / KCTC 5769 / VKM B-1644 / 5575)", ("Desulfotomaculum nigrificans (strain DSM 14880 / VKM B-2319 / CO-1-SRB)", "Desulfotomaculum reducens (strain MI-1)", "Desulfotomaculum ruminis (strain ATCC 23193 / DSM 2154 / NCIMB 8452 / DL)")"g__Desulfotomaculum", "Desulfofundulus kuznetsovii (strain DSM 6115 / VKM B-1805 / 17)", "Pelotomaculum thermopropionicum (strain DSM 13744 / JCM 10971 / SI)")"o__Desulfotomaculales")"c__Desulfotomaculia", "Carboxydocella thermautotrophica", ("Moorella thermoacetica (strain ATCC 39073 / JCM 9320)", "Thermacetogenium phaeum (strain ATCC BAA-254 / DSM 26808 / PB)")"c__Moorellia", "Thermanaerosceptrum fracticalcis", ("Syntrophomonas wolfei subsp. wolfei (strain DSM 2245B / Goettingen)", "Syntrophothermus lipocalidus (strain DSM 12680 / TGB-C1)")"o__Syntrophomonadales", "Clostridia bacterium zrk5", "Thermincola potens (strain JR)", "Carboxydothermus hydrogenoformans (strain ATCC BAA-161 / DSM 6008 / Z-2901)")"p__Firmicutes_B", ("Clostridia bacterium AS04akNAM_38", (("Acidaminococcus fermentans (strain ATCC 25085 / DSM 20731 / CCUG 9996 / CIP 106432 / VR4)", "Acidaminococcus intestini (strain RyC-MR95)")"g__Acidaminococcus", ("Selenomonas sputigena (strain ATCC 35185 / DSM 20758 / VPI D19B-28)", "Selenomonas ruminantium subsp. lactilytica (strain NBRC 103574 / TAM6421)")"f__Selenomonadaceae", "Veillonella parvula (strain ATCC 10790 / DSM 2008 / CCUG 5123 / JCM 12972 / NCTC 11810 / Te3)")"c__Negativicutes")"p__Firmicutes_C", ("Dethiobacter alkaliphilus", "Natranaerobius thermophilus (strain ATCC BAA-1301 / DSM 18059 / JW/NM-WN-LF)", "Alkalicella caledoniensis")"p__Firmicutes_D", ("Firmicutes bacterium Bu02", "Firmicutes bacterium NC_groundwater_661_Ag_B-0.1um_63_60", "Clostridiales bacterium RBS10-35", ("Sulfobacillus acidophilus (strain ATCC 700253 / DSM 10332 / NAL)", "Sulfobacillus acidophilus (strain TPY)")"s__Sulfobacillus_A acidophilus", "Symbiobacterium thermophilum (strain T / IAM 14863)", "Thermaerobacter marianensis (strain ATCC 700841 / DSM 12885 / JCM 10246 / 7p75a)", "Firmicutes bacterium AS08sgBPME_412")"p__Firmicutes_E", ((("Halanaerobium hydrogeniformans", "Halanaerobium praevalens (strain ATCC 33744 / DSM 2228 / GSL)")"g__Halanaerobium", "Halothermothrix orenii (strain H 168 / OCM 544 / DSM 9562)")"o__Halanaerobiales", ("Acetohalobium arabaticum (strain ATCC 49924 / DSM 5501 / Z-7288)", "Halobacteroides halobius (strain ATCC 35273 / DSM 5150 / MD-1)")"o__Halobacteroidales")"c__Halanaerobiia", ("Limnochorda pilosa", "Firmicutes bacterium AS04akNAM_86", "Hydrogenispora ethanolica", "Firmicutes bacterium GB_MAG18_067")"p__Firmicutes_G", (("Fusobacterium nucleatum subsp. nucleatum (strain ATCC 25586 / DSM 15643 / BCRC 10681 / CIP 101130 / JCM 8532 / KCTC 2640 / LMG 13131 / VPI 4355)", "Ilyobacter polytropus (strain ATCC 51220 / DSM 2926 / LMG 16218 / CuHBu1)")"f__Fusobacteriaceae", ("Leptotrichia buccalis (strain ATCC 14201 / DSM 1135 / JCM 12969 / NCTC 10249 / C-1013-b)", "Sebaldella termitidis (strain ATCC 33386 / NCTC 11300)", "Streptobacillus moniliformis (strain ATCC 14647 / DSM 12112 / NCTC 10651 / 9901)")"f__Leptotrichiaceae")"o__Fusobacteriales", "PVC group bacterium (ex Bugula neritina AB1) AB1-3", ("Gemmatimonas aurantiaca (strain T-27 / DSM 14586 / JCM 11422 / NBRC 100505)", "Candidatus Glassbacteria bacterium RIFCSPLOWO2_12_FULL_58_11 none")"p__Gemmatimonadota", "Gemmatimonadetes bacterium ARS67", "Candidatus Goldbacteria bacterium HGW-Goldbacteria-1", "candidate division WS2 bacterium BS5B28", "Candidatus Hydrogenedens sp. RI_113", "Candidatus Dadabacteria bacterium J088", "Gemmatimonadetes bacterium SB0661_bin_27", "Candidatus Eisenbacteria bacterium Zod_Metabat.137", "Verrucomicrobia bacterium Zod_Metabat.1268", "bacterium MAG-57", "Nitrospirae bacterium NC_groundwater_240_Ag_S-0.2um_61_13", "Candidatus Tectomicrobia bacterium NC_groundwater_717_Ag_S-0.2um_59_8", "Candidatus Tectomicrobia bacterium NC_groundwater_748_Ag_S-0.65um_67_15", "Chlamydiae bacterium NC_groundwater_60_Pr7_S-0.65um_42_121", "Candidatus Desantisbacteria bacterium NC_groundwater_1497_Pr4_B-0.1um_33_3", "Candidatus Aureabacteria bacterium Zod_Metabat.1054", "Candidatus Coatesbacteria bacterium Zod_Metabat.53", "Oligoflexia bacterium Zod_Metabat.617", "Candidatus Dependentiae bacterium Go_SlDig_bin_425", "Candidatus Delongbacteria bacterium Go_SlDig_bin_59", "bacterium Modern_marine.mb.62", "bacterium BMS3Bbin03", "Calditrichaeota bacterium CLD2", "bacterium Fred_18-Q3-R57-64_MAXAC.288", ("Candidatus Latescibacteria bacterium B68_G9", "Candidatus Latescibacteria bacterium Zod_Metabat.481", "Candidatus Latescibacteria bacterium UWMA-0219", "Candidatus Latescibacteria bacterium ADurb.Bin168", "Gemmatimonadetes bacterium RS821")"p__Latescibacterota", "Candidatus Lindowbacteria bacterium RIFCSPLOWO2_12_FULL_62_27 none", ("Candidatus Margulisbacteria bacterium RAAC_38_40", "Candidatus Termititenax aidoneus NkOx7-01", "candidate division WOR-1 bacterium RIFOXYB2_FULL_45_9 none")"p__Margulisbacteria", ("Candidatus Marinimicrobia bacterium BS150m-G59", "Candidatus Marinimicrobia bacterium SuakinDeep_MAGBODY_4", "Candidatus Marinimicrobia bacterium MT.SAG.2", "Candidatus Marinimicrobia bacterium SI036_bin79")"p__Marinisomatota", "Candidatus Mcinerneyibacteriota bacterium ZodW_Metabat.255", "Candidatus Methylomirabilis oxyfera none", "Candidatus Vecturithrix granuli none", "Candidatus Muirbacterium halophilum BM706", ("Myxococcales bacterium AS27yjCOA_137", "Persicimonas caeni", "Deltaproteobacteria bacterium M_MaxBin.025", "Deltaproteobacteria bacterium NC_groundwater_736_Ag_S-0.65um_62_10", "Deltaproteobacteria bacterium NC_groundwater_1656_Pr3_B-0.1um_70_40", "Deltaproteobacteria bacterium Zod_Metabat.937", ((("Anaeromyxobacter dehalogenans (strain 2CP-1 / ATCC BAA-258)", "Anaeromyxobacter sp. (strain K)")"s__Anaeromyxobacter dehalogenans", "Anaeromyxobacter dehalogenans (strain 2CP-C)", "Anaeromyxobacter sp. (strain Fw109-5)")"g__Anaeromyxobacter", ("Corallococcus coralloides (strain ATCC 25202 / DSM 2259 / NBRC 100086 / M2)", ("Myxococcus fulvus (strain ATCC BAA-855 / HW-1)", "Myxococcus stipitatus (strain DSM 14675 / JCM 12634 / Mx s8)", "Myxococcus xanthus (strain DK1622)")"g__Myxococcus", "Stigmatella aurantiaca (strain DW4/3-1)")"f__Myxococcaceae")"o__Myxococcales", ("Haliangium ochraceum (strain DSM 14365 / JCM 11303 / SMP-2)", "Sorangium cellulosum (strain So ce56)")"c__Polyangia", "Myxococcales bacterium SURF_8", "Deltaproteobacteria bacterium NC_groundwater_1649_Pr3_B-0.1um_64_26", "Myxococcales bacterium EAC29", "Deltaproteobacteria bacterium NP119", "Deltaproteobacteria bacterium NC_groundwater_80_Ag_B-0.1um_71_39", "Deltaproteobacteria bacterium Fred_18-Q3-R57-64_BATAC.308", "Deltaproteobacteria bacterium NC_groundwater_1655_Pr3_B-0.1um_70_22")"p__Myxococcota", ("Deltaproteobacteria bacterium M1803", "Deltaproteobacteria bacterium Fred_18-Q3-R57-64_BAT3C.701")"p__Myxococcota_A", "candidate division NPL-UPA2 bacterium Unc8", ("Nitrospinae bacterium NC_groundwater_1753_Pr3_B-0.1um_50_18", "Nitrospinae bacterium nPCRbin9", "Nitrospina gracilis (strain 3/211)", "Nitrospinae bacterium NC_groundwater_1503_Pr4_B-0.1um_56_23", "Nitrospinae bacterium NC_groundwater_948_Pr1_S-0.2um_39_25")"p__Nitrospinota", "Nitrospinae bacterium RIFCSPLOWO2_12_FULL_45_22 none", ("Nitrospirae bacterium NC_groundwater_1760_Pr3_B-0.1um_42_52", "Nitrospirae bacterium NC_groundwater_1776_Pr3_B-0.1um_70_102", "Nitrospira moscoviensis", "Nitrospirae bacterium NC_groundwater_891_Pr1_S2p5_65_34", "Thermodesulfovibrio yellowstonii (strain ATCC 51303 / DSM 11347 / YP87)", "Nitrospirae bacterium NC_groundwater_1774_Pr3_B-0.1um_61_24")"p__Nitrospirota", ("Leptospirillum ferrooxidans (strain C2-3)", "Leptospirillum ferriphilum (strain ML-04)")"f__Leptospirillaceae", "bacterium H5_UNCL2", ("Candidatus Omnitrophica bacterium B17_G2", "Candidatus Omnitrophica bacterium NC_groundwater_666_Ag_B-0.1um_57_48")"p__Omnitrophota", ("candidate division WWE3 bacterium W9_Combined_metabat1_117", "Candidatus Kerfeldbacteria bacterium NC_groundwater_1953_Pr3_S-0.2um_48_12", "Candidatus Andersenbacteria bacterium NC_groundwater_813_Pr1_B-0.1um_46_36", "candidate division CPR2 bacterium GW2011_GWC2_39_35 none", "bacterium CG_4_10_14_0_2_um_filter_33_32", "candidate division CPR3 bacterium GWF2_35_18 none", "bacterium Kalu_18-Q3-R12-55_BAT3C.2_fly", "bacterium (Candidatus Torokbacteria) CG_4_10_14_0_2_um_filter_35_8", "Candidatus Peregrinibacteria bacterium Lyne_18-Q3-R50-59_MAXAC.411_cln", "Patescibacteria group bacterium MM_PC_MetaG.mb.169", "Candidatus Pacebacteria bacterium LF-bin-483", "Candidatus Microgenomates bacterium NC_groundwater_396_Ag_B-0.1um_42_16", "Candidatus Gracilibacteria bacterium 28_42_T64", "Patescibacteria group bacterium Modern_marine.mb.211", "candidate division Kazan bacterium GW2011_GWA1_50_15 none", "Candidatus Roizmanbacteria bacterium Kalu_18-Q3-R12-55_MAXAC.194_uni", "Candidatus Niyogibacteria bacterium NC_groundwater_707_Ag_S-0.2um_45_26", "Patescibacteria group bacterium Baikal-deep-G193", "Patescibacteria group bacterium E44_bin74", "Berkelbacteria bacterium GW2011_GWE1_39_12 none", "candidate division WWE3 bacterium RAAC2_WWE3_1")"p__Patescibacteria", ("Planctomycetes bacterium B129_G9", "Planctomycetes bacterium B143_G9", "Planctomycetes bacterium Aved_18-Q3-R54-62_MAXAC.457", "Kuenenia stuttgartiensis", "Planctomycetes bacterium E44_bin39", "Planctomycetes bacterium J058", "Planctomycetes bacterium SRT547", "Planctomycetes bacterium NC_groundwater_38_Pr7_B-0.1um_65_11", "Planctomycetes bacterium NC_groundwater_1472_Ag_S-0.65um_69_29", "Planctomycetes bacterium NC_groundwater_1474_Ag_S-0.65um_73_34", "Planctomycetes bacterium Zod_Metabat.792", "Planctomycetes bacterium NC_groundwater_1801_Pr3_B-0.1um_50_33", "Planctomycetes bacterium NC_groundwater_288_Ag_S-0.65um_63_14", "Phycisphaera mikurensis (strain NBRC 102666 / KCTC 22515 / FYK2301M01)", (("Isosphaera pallida (strain ATCC 43644 / DSM 9630 / IS1B)", "Singulisphaera acidiphila (strain ATCC BAA-1392 / DSM 18658 / VKM B-2454 / MOB10)")"f__Isosphaeraceae", ("Pirellula staleyi (strain ATCC 27377 / DSM 6068 / ICPB 4128)", "Rhodopirellula baltica (strain DSM 10527 / NCIMB 13988 / SH1)")"f__Pirellulaceae", ("Planctopirus limnophila (strain ATCC 43296 / DSM 3776 / IFAM 1008 / Mu 290)", "Rubinisphaera brasiliensis (strain ATCC 49424 / DSM 5305 / JCM 21570 / NBRC 103401 / IFAM 1448)")"f__Planctomycetaceae")"c__Planctomycetia", "Planctomycetes bacterium H5_PLA8", "Planctomycetes bacterium Poly30", "Planctomycetes bacterium NAT2", "Planctomycetes bacterium Fred_18-Q3-R57-64_MAXAC.456")"p__Planctomycetota", ("Candidatus Poribacteria bacterium Bin_402", "Candidatus Poribacteria bacterium PCPOR2b")"p__Poribacteria", ((("Acetobacter pasteurianus (strain NBRC 105184 / IFO 3283-01)", ("Acidiphilium cryptum (strain JF-5)", "Acidiphilium multivorum (strain DSM 11245 / JCM 8867 / NBRC 100883 / AIU 301)")"s__Acidiphilium multivorum", "Gluconacetobacter diazotrophicus (strain ATCC 49037 / DSM 5601 / CCUG 37298 / CIP 103539 / LMG 7603 / PAl5)", "Gluconobacter oxydans (strain 621H)", "Granulibacter bethesdensis (strain ATCC BAA-1260 / CGDNIH1)", "Komagataeibacter medellinensis (strain NBRC 3288 / BCRC 11682 / LMG 1693 / Kondo 51)")"f__Acetobacteraceae", ("Azospirillum lipoferum (strain 4B)", "Rhodospirillum centenum (strain ATCC 51521 / SW)")"f__Azospirillaceae", (("Asticcacaulis excentricus (strain ATCC 15261 / DSM 4724 / KCTC 12464 / NCIMB 9791 / VKM B-1370 / CB 48)", "Brevundimonas subvibrioides (strain ATCC 15264 / DSM 4735 / LMG 14903 / NBRC 16000 / CB 81)", ("Caulobacter segnis (strain ATCC 21756 / DSM 7131 / JCM 7823 / NBRC 15250 / LMG 17158 / TK0059)", "Caulobacter sp. (strain K31)", ("Caulobacter vibrioides (strain ATCC 19089 / CB15)", "Caulobacter vibrioides (strain NA1000 / CB15N)")"s__Caulobacter vibrioides")"g__Caulobacter", "Phenylobacterium zucineum (strain HLK1)")"f__Caulobacteraceae", ("Hirschia baltica (strain ATCC 49814 / DSM 5838 / IFAM 1418)", "Hyphomonas neptunium (strain ATCC 15444)")"f__Hyphomonadaceae", "Maricaulis maris (strain MCS10)", "Parvularcula bermudensis (strain ATCC BAA-594 / HTCC2503 / KCTC 12087)")"o__Caulobacterales", "Micavibrio aeruginosavorus (strain ARL-13)", "Parvibaculum lavamentivorans (strain DS-1 / DSM 13023 / NCIMB 13966)", ("Pelagibacter sp. (strain IMCC9063)", "Pelagibacter ubique (strain HTCC1062)")"f__Pelagibacteraceae", "Puniceispirillum marinum (strain IMCC1322)", (("Beijerinckia indica subsp. indica (strain ATCC 9039 / DSM 1715 / NCIMB 8712)", (("Methylorubrum extorquens (strain ATCC 14718 / DSM 1338 / JCM 2805 / NCIMB 9133 / AM1)", "Methylorubrum extorquens (strain CM4 / NCIMB 13688)", "Methylorubrum extorquens (strain DSM 6343 / CIP 106787 / DM4)", "Methylorubrum extorquens (strain PA1)")"s__Methylobacterium extorquens", "Methylobacterium nodulans (strain LMG 21967 / CNCM I-2342 / ORS 2060)", "Methylobacterium radiotolerans (strain ATCC 27329 / DSM 1819 / JCM 2831 / NBRC 15690 / NCIMB 10815 / 0-1)", "Methylobacterium sp. (strain 4-46)", "Methylorubrum populi (strain ATCC BAA-705 / NCIMB 13946 / BJ001)")"g__Methylobacterium", "Methylocella silvestris (strain DSM 15510 / CIP 108128 / LMG 27833 / NCIMB 13906 / BL2)", "Methylocystis sp. (strain SC2)")"f__Beijerinckiaceae", "Pelagibacterium halotolerans (strain DSM 22347 / JCM 15775 / CGMCC 1.7692 / B2)", (("Hyphomicrobium denitrificans (strain ATCC 51888 / DSM 1869 / NCIMB 11706 / TK 0415)", "Hyphomicrobium sp. (strain MC1)")"g__Hyphomicrobium", "Hyphomicrobium sulfonivorans")"f__Hyphomicrobiaceae", ("Agrobacterium fabrum (strain C58 / ATCC 33970)", "Agrobacterium vitis (strain S4 / ATCC BAA-846)", "Chelativorans sp. (strain BNC1)", ("Mesorhizobium australicum (strain HAMBI 3006 / LMG 24608 / WSM2073)", "Mesorhizobium ciceri biovar biserrulae (strain HAMBI 2942 / LMG 23838 / WSM1271)", "Mesorhizobium japonicum (strain LMG 29417 / CECT 9101 / MAFF 303099)")"g__Mesorhizobium", ("Rhizobium leguminosarum bv. trifolii (strain WSM2304)", "Rhizobium etli (strain CFN 42 / ATCC 51251)", "Rhizobium leguminosarum bv. trifolii (strain WSM1325)", "Rhizobium leguminosarum bv. viciae (strain 3841)", "Rhizobium etli (strain CIAT 652)", "Agrobacterium radiobacter (strain K84 / ATCC BAA-868)")"g__Rhizobium", ("Rhizobium fredii (strain HH103)", "Sinorhizobium fredii (strain NBRC 101917 / NGR234)", "Sinorhizobium medicae (strain WSM419)", ("Rhizobium meliloti (strain 1021)", "Sinorhizobium meliloti (strain AK83)", "Sinorhizobium meliloti (strain BL225C)", "Sinorhizobium meliloti (strain SM11)")"s__Sinorhizobium meliloti")"g__Sinorhizobium")"f__Rhizobiaceae", "Rhodomicrobium vannielii (strain ATCC 17100 / ATH 3.1.1 / DSM 162 / LMG 4299)", ("Polymorphum gilvum (strain LMG 25793 / CGMCC 1.9160 / SL003B-26A1)", "Pseudovibrio sp. (strain FO-BEG1)")"f__Stappiaceae", (("Afipia carboxidovorans (strain ATCC 49405 / DSM 1227 / KCTC 32145 / OM5)", "Afipia carboxidovorans (strain OM4)")"s__Afipia carboxidovorans", "Azorhizobium caulinodans (strain ATCC 43989 / DSM 5975 / JCM 20966 / LMG 6465 / NBRC 14845 / NCIMB 13405 / ORS 571)", "Blastochloris viridis", ("Bradyrhizobium sp. (strain BTAi1 / ATCC BAA-1182)", "Bradyrhizobium diazoefficiens (strain JCM 10833 / BCRC 13528 / IAM 13628 / NBRC 14792 / USDA 110)", "Bradyrhizobium sp. (strain ORS 278)")"g__Bradyrhizobium", ("Nitrobacter hamburgensis (strain DSM 10229 / NCIMB 13809 / X14)", "Nitrobacter winogradskyi (strain ATCC 25391 / DSM 10237 / CIP 104748 / NCIMB 11846 / Nb-255)")"g__Nitrobacter", ("Rhodopseudomonas palustris (strain BisA53)", "Rhodopseudomonas palustris (strain BisB18)", ("Rhodopseudomonas palustris (strain ATCC BAA-98 / CGA009)", "Rhodopseudomonas palustris (strain TIE-1)")"s__Rhodopseudomonas palustris_F", "Rhodopseudomonas palustris (strain DX-1)", "Rhodopseudomonas palustris (strain HaA2)", "Rhodopseudomonas palustris (strain BisB5)")"g__Rhodopseudomonas", "Starkeya novella (strain ATCC 8093 / DSM 506 / JCM 20403 / CCM 1077 / IAM 12100 / NBRC 12443 / NCIMB 10456)", "Xanthobacter autotrophicus (strain ATCC BAA-1158 / Py2)")"f__Xanthobacteraceae")"o__Rhizobiales", (("Bartonella bacilliformis (strain ATCC 35685 / NCTC 12138 / KC583)", "Bartonella vinsonii subsp. berkhoffii (strain Winnie)", "Bartonella clarridgeiae (strain CIP 104772 / 73)", "Bartonella grahamii (strain as4aup)", "Bartonella henselae (strain ATCC 49882 / DSM 28221 / Houston 1)", "Bartonella quintana (strain Toulouse)", "Bartonella tribocorum (strain CIP 105476 / IBS 506)")"g__Bartonella", ("Brucella abortus (strain 2308)", "Brucella abortus (strain S19)", "Brucella abortus biovar 1 (strain 9-941)", "Brucella canis (strain ATCC 23365 / NCTC 10854)", "Brucella melitensis (strain M5-90)", "Brucella melitensis biotype 1 (strain 16M / ATCC 23456 / NCTC 10094)", "Brucella melitensis biotype 2 (strain ATCC 23457)", "Brucella microti (strain CCM 4915)", "Brucella ovis (strain ATCC 25840 / 63/290 / NCTC 10512)", "Brucella suis (strain ATCC 23445 / NCTC 10510)", "Brucella suis biovar 1 (strain 1330)")"s__Brucella melitensis", "Liberibacter asiaticus (strain psy62)", "Brucella anthropi (strain ATCC 49188 / DSM 6882 / CCUG 24695 / JCM 21032 / LMG 3331 / NBRC 15819 / NCTC 12168 / Alc 37)")"f__Rhizobiaceae_A", ("Rhodovulum sulfidophilum", ("Cereibacter sphaeroides (strain ATCC 17025 / ATH 2.4.3)", ("Cereibacter sphaeroides (strain ATCC 17023 / DSM 158 / JCM 6121 / CCUG 31486 / LMG 2827 / NBRC 12203 / NCIMB 8253 / ATH 2.4.1.)", "Cereibacter sphaeroides (strain ATCC 17029 / ATH 2.4.9)", "Cereibacter sphaeroides (strain KD131 / KCTC 12085)")"s__Cereibacter_A sphaeroides")"g__Cereibacter_A", "Dinoroseobacter shibae (strain DSM 16493 / NCIMB 14021 / DFL 12)", "Ruegeria sp. (strain TM1040)", ("Ketogulonicigenium vulgare (strain WSH-001)", "Ketogulonicigenium vulgare (strain Y25)")"s__Ketogulonicigenium vulgare", "Oceanicola granulosus (strain ATCC BAA-861 / DSM 15982 / KCTC 12143 / HTCC2516)", "Paracoccus denitrificans (strain Pd 1222)", "Phaeobacter inhibens (strain DSM 17395)", "Rhodobacter capsulatus (strain ATCC BAA-309 / NBRC 16581 / SB1003)", "Jannaschia sp. (strain CCS1)", ("Roseobacter denitrificans (strain ATCC 33942 / OCh 114)", "Roseobacter litoralis (strain ATCC 49566 / DSM 6996 / JCM 21268 / NBRC 15278 / OCh 149)")"g__Roseobacter", "Ruegeria pomeroyi (strain ATCC 700808 / DSM 15171 / DSS-3)")"f__Rhodobacteraceae", ("Magnetospira sp. (strain QH-2)", "Magnetospirillum magneticum (strain AMB-1 / ATCC 700264)", "Rhodospirillum rubrum (strain ATCC 11170 / ATH 1.1.1 / DSM 467 / LMG 4362 / NCIMB 8255 / S1)")"o__Rhodospirillales", (((("Anaplasma marginale (strain Florida)", "Anaplasma marginale (strain St. Maries)")"s__Anaplasma marginale", "Anaplasma phagocytophilum (strain HZ)")"g__Anaplasma", ("Ehrlichia canis (strain Jake)", "Ehrlichia chaffeensis (strain ATCC CRL-10679 / Arkansas)", ("Ehrlichia ruminantium (strain Gardel)", "Ehrlichia ruminantium (strain Welgevonden)")"s__Ehrlichia ruminantium")"g__Ehrlichia", ("Neorickettsia risticii (strain Illinois)", "Neorickettsia sennetsu (strain ATCC VR-367 / Miyayama)")"g__Neorickettsia", (("Wolbachia pipientis wMel", "Wolbachia sp. subsp. Drosophila simulans (strain wRi)")"s__Wolbachia pipientis", "Wolbachia pipientis", "Wolbachia sp. subsp. Brugia malayi (strain TRS)", "Wolbachia pipientis subsp. Culex pipiens (strain wPip)")"g__Wolbachia")"f__Anaplasmataceae", "Midichloria mitochondrii (strain IricVA)", (("Orientia tsutsugamushi (strain Boryong)", "Orientia tsutsugamushi (strain Ikeda)")"s__Orientia tsutsugamushi", ("Rickettsia akari (strain Hartford)", "Rickettsia australis (strain Cutlack)", ("Rickettsia bellii (strain OSU 85-389)", "Rickettsia bellii (strain RML369-C)")"s__Rickettsia bellii", "Rickettsia canadensis (strain McKiel)", "Rickettsia felis (strain ATCC VR-1525 / URRWXCal2)", ("Rickettsia prowazekii (strain Madrid E)", "Rickettsia prowazekii (strain Rp22)")"s__Rickettsia prowazekii", ("Rickettsia amblyommatis (strain GAT-30V)", "Rickettsia massiliae (strain Mtu5)", "Rickettsia montanensis (strain OSU 85-930)", "Rickettsia rhipicephali (strain 3-7-female6-CWPP)")"s__Rickettsia rhipicephali", ("Rickettsia africae (strain ESF-5)", "Rickettsia conorii (strain ATCC VR-613 / Malish 7)", "Rickettsia japonica (strain ATCC VR-1363 / YH)", "Rickettsia parkeri (strain Portsmouth)", "Rickettsia peacockii (strain Rustic)", "Rickettsia philipii (strain 364D)", "Rickettsia rickettsii (strain Iowa)", "Rickettsia rickettsii (strain Sheila Smith)", "Rickettsia slovaca (strain 13-B)")"s__Rickettsia rickettsii", "Rickettsia typhi (strain ATCC VR-144 / Wilmington)")"g__Rickettsia")"f__Rickettsiaceae")"o__Rickettsiales", ("Erythrobacter litoralis (strain HTCC2594)", "Novosphingobium aromaticivorans (strain ATCC 700278 / DSM 12444 / CCUG 56034 / CIP 105152 / NBRC 16084 / F199)", "Rhizorhabdus wittichii (strain DSM 6014 / CCUG 31198 / JCM 15750 / NBRC 105917 / EY 4224 / RW1)", "Sphingobium japonicum (strain DSM 16413 / CCM 7287 / MTCC 6362 / UT26 / NBRC 101211 / UT26S)", ("Sphingopyxis alaskensis (strain DSM 13593 / LMG 18877 / RB2256)", "Sphingopyxis macrogoltabida")"g__Sphingopyxis", (("Zymomonas mobilis subsp. mobilis (strain ATCC 10988 / DSM 424 / LMG 404 / NCIMB 8938 / NRRL B-806 / ZM1)", "Zymomonas mobilis subsp. mobilis (strain ATCC 31821 / ZM4 / CP4)", "Zymomonas mobilis subsp. mobilis (strain NCIMB 11163 / B70)")"s__Zymomonas mobilis", "Zymomonas mobilis subsp. pomaceae (strain ATCC 29192 / DSM 22645 / JCM 10191 / CCUG 17912 / NBRC 13757 / NCIMB 11200 / NRRL B-4491 / Barker I)")"g__Zymomonas")"f__Sphingomonadaceae", "Tistrella mobilis (strain KA081020-065)")"c__Alphaproteobacteria", ((("Acidithiobacillus ferrooxidans (strain ATCC 23270 / DSM 14882 / CIP 104768 / NCIMB 8455)", "Acidithiobacillus ferrooxidans (strain ATCC 53993 / BNL-5-31)")"s__Acidithiobacillus ferrooxidans", "Acidithiobacillus caldus (strain SM-1)")"f__Acidithiobacillaceae", ("Laribacter hongkongensis (strain HLHK9)", ("Achromobacter xylosoxidans (strain A8)", "Verminephrobacter eiseniae (strain EF01-2)", ("Acidovorax avenae (strain ATCC 19860 / DSM 7227 / CCUG 15838 / JCM 20985 / LMG 2117 / NCPPB 1011)", "Acidovorax citrulli (strain AAC00-1)")"g__Acidovorax_A", "Advenella kashmirensis (strain DSM 17095 / LMG 22695 / WT001)", "Alicycliphilus denitrificans (strain DSM 14773 / CIP 107495 / K601)", ("Bordetella avium (strain 197N)", ("Bordetella bronchiseptica (strain ATCC BAA-588 / NCTC 13252 / RB50)", "Bordetella bronchiseptica (strain MO149)", "Bordetella parapertussis (strain 12822 / ATCC BAA-587 / NCTC 13253)", "Bordetella pertussis (strain ATCC 9797 / DSM 5571 / NCTC 10739 / 18323)", "Bordetella pertussis (strain CS)", "Bordetella pertussis (strain Tohama I / ATCC BAA-589 / NCTC 13251)")"s__Bordetella pertussis")"g__Bordetella", "Bordetella petrii (strain ATCC BAA-461 / DSM 12804 / CCUG 43448)", (("Burkholderia ambifaria (strain ATCC BAA-244 / AMMD)", "Burkholderia ambifaria (strain MC40-6)")"s__Burkholderia ambifaria", "Burkholderia cenocepacia (strain ATCC BAA-245 / DSM 16553 / LMG 16656 / NCTC 13227 / J2315 / CF5610)", ("Burkholderia cenocepacia (strain AU 1054)", "Burkholderia cenocepacia (strain HI2424)", "Burkholderia cenocepacia (strain MC0-3)")"s__Burkholderia cenocepacia_B", "Burkholderia gladioli (strain BSR3)", "Burkholderia glumae (strain BGR1)", "Burkholderia lata (strain ATCC 17760 / DSM 23089 / LMG 22485 / NCIMB 9086 / R18194 / 383)", ("Burkholderia mallei (strain ATCC 23344)", "Burkholderia mallei (strain NCTC 10229)", "Burkholderia mallei (strain NCTC 10247)", "Burkholderia mallei (strain SAVP1)", "Burkholderia pseudomallei (strain 1106a)", "Burkholderia pseudomallei (strain 1710b)", "Burkholderia pseudomallei (strain 668)", "Burkholderia pseudomallei (strain K96243)")"s__Burkholderia mallei", "Burkholderia multivorans (strain ATCC 17616 / 249)", "Burkholderia thailandensis (strain ATCC 700388 / DSM 13276 / CIP 106301 / E264)", "Burkholderia vietnamiensis (strain G4 / LMG 22486)")"g__Burkholderia", "Collimonas fungivorans (strain Ter331)", ("Delftia acidovorans (strain DSM 14801 / SPH-1)", "Delftia sp. (strain Cs1-4)")"s__Comamonas acidovorans", ("Cupriavidus metallidurans (strain ATCC 43123 / DSM 2839 / NBRC 102507 / CH34)", ("Cupriavidus necator (strain ATCC 17699 / DSM 428 / KCTC 22496 / NCIMB 10442 / H16 / Stanier 337)", "Cupriavidus necator (strain ATCC 43291 / DSM 13513 / CCUG 52238 / LMG 8453 / N-1)")"s__Cupriavidus necator", "Cupriavidus pinatubonensis (strain JMP 134 / LMG 1197)", "Cupriavidus taiwanensis (strain DSM 17343 / BCRC 17206 / CCUG 44338 / CIP 107171 / LMG 19424 / R1)")"g__Cupriavidus", ("Acidovorax ebreus (strain TPSY)", "Acidovorax sp. (strain JS42)")"s__Diaphorobacter nitroreducens", "Herbaspirillum seropedicae (strain SmR1)", ("Herminiimonas arsenicoxydans", "Janthinobacterium sp. (strain Marseille)")"g__Herminiimonas", "Ideonella sakaiensis (strain NBRC 110686 / TISTR 2288 / 201-F6)", "Leptothrix cholodnii (strain ATCC 51168 / LMG 8142 / SP-6)", "Methylibium petroleiphilum (strain ATCC BAA-1232 / LMG 22953 / PM1)", "Mycetohabitans rhizoxinica (strain DSM 19002 / CIP 109453 / HKI 454)", ("Paraburkholderia phymatum (strain DSM 17167 / CIP 108236 / LMG 21445 / STM815)", "Paraburkholderia phytofirmans (strain DSM 17436 / LMG 22146 / PsJN)", "Burkholderia sp. (strain CCGE1003)", "Paraburkholderia xenovorans (strain LB400)")"g__Paraburkholderia", ("Polaromonas naphthalenivorans (strain CJ2)", "Polaromonas sp. (strain JS666 / ATCC BAA-500)")"g__Polaromonas", ("Polynucleobacter asymbioticus (strain DSM 18221 / CIP 109841 / QLW-P1DMWA-1)", "Polynucleobacter necessarius subsp. necessarius (strain STIR1)")"g__Polynucleobacter", "Pusillimonas sp. (strain T7-7)", (("Ralstonia pickettii (strain 12D)", "Ralstonia pickettii (strain 12J)")"s__Ralstonia pickettii_B", ("Ralstonia solanacearum", "Ralstonia solanacearum (strain GMI1000)")"s__Ralstonia pseudosolanacearum", "Ralstonia solanacearum (strain Po82)")"g__Ralstonia", "Ramlibacter tataouinensis (strain ATCC BAA-407 / DSM 14655 / LMG 21543 / TTB310)", "Rhodoferax ferrireducens (strain ATCC BAA-621 / DSM 15236 / T118)", "Rubrivivax gelatinosus (strain NBRC 100245 / IL144)", "Taylorella equigenitalis (strain MCE9)", "Thiomonas intermedia (strain K12)", ("Variovorax paradoxus (strain S110)", "Variovorax paradoxus (strain EPS)")"g__Variovorax")"f__Burkholderiaceae", ("Chromobacterium violaceum (strain ATCC 12472 / DSM 30191 / JCM 1249 / NBRC 12614 / NCIMB 9131 / NCTC 9757)", "Pseudogulbenkiania sp. (strain NH8B)")"f__Chromobacteriaceae", ("Gallionella capsiferriformans (strain ES-2)", "Sideroxydans lithotrophicus (strain ES-1)")"f__Gallionellaceae", ("Methylobacillus flagellatus (strain KT / ATCC 51484 / DSM 6875)", "Methylotenera mobilis (strain JLW8 / ATCC BAA-1282 / DSM 17540)", ("Methylovorus glucosetrophus (strain SIP3-4)", "Methylovorus sp. (strain MP688)")"s__Methylovorus glucosotrophus")"f__Methylophilaceae", (("Neisseria gonorrhoeae (strain ATCC 700825 / FA 1090)", "Neisseria gonorrhoeae (strain NCCP11945)")"s__Neisseria gonorrhoeae", ("Neisseria meningitidis (strain alpha14)", "Neisseria meningitidis serogroup A (strain WUE 2594)", "Neisseria meningitidis serogroup A / serotype 4A (strain DSM 15465 / Z2491)", "Neisseria meningitidis serogroup B (strain G2136)", "Neisseria meningitidis serogroup B (strain M01-240149)", "Neisseria meningitidis serogroup B (strain M01-240355)", "Neisseria meningitidis serogroup B (strain M04-240196)", "Neisseria meningitidis serogroup B (strain MC58)", "Neisseria meningitidis serogroup B (strain NZ-05/33)", "Neisseria meningitidis serogroup B (strain alpha710)", "Neisseria meningitidis serogroup B / serotype 15 (strain H44/76)", "Neisseria meningitidis serogroup C (strain 053442)", "Neisseria meningitidis serogroup C (strain 8013)", "Neisseria meningitidis serogroup C / serotype 2a (strain ATCC 700532 / DSM 15464 / FAM18)")"s__Neisseria meningitidis")"g__Neisseria", (("Nitrosomonas europaea (strain ATCC 19718 / CIP 103999 / KCTC 2705 / NBRC 14298)", "Nitrosomonas eutropha (strain DSM 101675 / C91 / Nm57)", "Nitrosomonas sp. (strain Is79A3)")"g__Nitrosomonas", "Nitrosospira multiformis (strain ATCC 25196 / NCIMB 11849 / C 71)")"f__Nitrosomonadaceae", ("Accumulibacter phosphatis (strain UW-1)", "Aromatoleum aromaticum (strain EbN1)", "Azoarcus sp. (strain BH72)", "Dechloromonas aromatica (strain RCB)", "Azospira oryzae (strain ATCC BAA-33 / DSM 13638 / PS)", "Thauera sp. (strain MZ1T)")"f__Rhodocyclaceae", "Thiobacillus denitrificans (strain ATCC 25259)")"o__Burkholderiales", ("Cardiobacterium hominis (strain ATCC 15826 / DSM 8339 / NCTC 10426 / 6573)", "Dichelobacter nodosus (strain VCS1703A)")"f__Cardiobacteriaceae", (("Allochromatium vinosum (strain ATCC 17899 / DSM 180 / NBRC 103801 / NCIMB 10441 / D)", "Thiocystis violascens (strain ATCC 17096 / DSM 198 / 6111)")"f__Chromatiaceae", "Solemya velum gill symbiont")"o__Chromatiales", ("Coxiella burnetii (strain CbuG_Q212)", "Coxiella burnetii (strain CbuK_Q154)", "Coxiella burnetii (strain Dugway 5J108-111)", "Coxiella burnetii (strain RSA 331 / Henzerling II)", "Coxiella burnetii (strain RSA 493 / Nine Mile phase I)")"s__Coxiella burnetii", ("Thioalkalivibrio sulfidiphilus (strain HL-EbGR7)", "Thioalkalivibrio sp. (strain K90mix)")"o__Ectothiorhodospirales", ((("Aeromonas hydrophila subsp. hydrophila (strain ATCC 7966 / DSM 30187 / BCRC 13018 / CCUG 14551 / JCM 1027 / KCTC 2358 / NCIMB 9240 / NCTC 8049)", "Aeromonas salmonicida (strain A449)", "Aeromonas veronii (strain B565)")"g__Aeromonas", "Oceanimonas sp. (strain GK1 / IBRC-M 10197)", "Tolumonas auensis (strain DSM 9187 / TA4)")"f__Aeromonadaceae", (("Alteromonas macleodii (strain Black Sea 11)", ("Alteromonas macleodii (strain Balearic Sea AD45)", "Alteromonas macleodii (strain English Channel 673)")"s__Alteromonas macleodii", "Alteromonas mediterranea (strain DSM 17117 / CIP 110805 / LMG 28347 / Deep ecotype)", "Alteromonas naphthalenivorans")"g__Alteromonas", "Colwellia psychrerythraea (strain 34H / ATCC BAA-681)", "Idiomarina loihiensis (strain ATCC BAA-735 / DSM 15497 / L2-TR)", "Pseudoalteromonas atlantica (strain T6c / ATCC BAA-1087)", ("Pseudoalteromonas translucida (strain TAC 125)", "Pseudoalteromonas sp. (strain SM9913)")"g__Pseudoalteromonas")"f__Alteromonadaceae", ("Baumannia cicadellinicola subsp. Homalodisca coagulata", "Citrobacter rodentium (strain ICC168)", "Citrobacter koseri (strain ATCC BAA-895 / CDC 4225-83 / SGSC4696)", ("Cronobacter sakazakii (strain ATCC BAA-894)", "Cronobacter turicensis (strain DSM 18703 / CCUG 55852 / LMG 23827 / z3032)")"g__Cronobacter", ("Dickeya chrysanthemi (strain Ech1591)", "Dickeya dadantii (strain 3937)", "Musicola paradisiaca (strain Ech703)", "Dickeya zeae (strain Ech586)")"g__Dickeya", ("Edwardsiella ictaluri (strain 93-146)", ("Edwardsiella tarda (strain EIB202)", "Edwardsiella tarda (strain FL6-60)")"s__Edwardsiella piscicida")"g__Edwardsiella", ("Enterobacter cloacae subsp. cloacae (strain ATCC 13047 / DSM 30054 / NBRC 13535 / NCTC 10005 / WDCM 00083 / NCDC 279-56)", "Enterobacter asburiae (strain LF7a)")"g__Enterobacter", "Enterobacter lignolyticus (strain SCF1)", (("Erwinia amylovora (strain ATCC 49946 / CCPPB 0273 / Ea273 / 27-3)", "Erwinia amylovora (strain CFBP1430)")"s__Erwinia amylovora", "Erwinia billingiae (strain Eb661)", ("Erwinia pyrifoliae (strain DSM 12162 / Ep1/96)", "Erwinia pyrifoliae (strain DSM 12163 / CIP 106111 / Ep16/96)", "Erwinia sp. (strain Ejp617)")"s__Erwinia pyrifoliae", "Erwinia tasmaniensis (strain DSM 17950 / CFBP 7177 / CIP 109463 / NCPPB 4357 / Et1/99)")"g__Erwinia", (("Escherichia coli (strain 'clone D i14')", "Escherichia coli (strain 'clone D i2')", "Escherichia coli (strain 55989 / EAEC)", "Escherichia coli (strain ATCC 55124 / KO11FL)", "Escherichia coli (strain ATCC 8739 / DSM 1576 / NBRC 3972 / NCIMB 8545 / WDCM 00012 / Crooks)", "Escherichia coli (strain ATCC 9637 / CCM 2024 / DSM 1116 / LMG 11080 / NBRC 13500 / NCIMB 8666 / NRRL B-766 / W)", "Escherichia coli (strain B / BL21)", "Escherichia coli (strain B / BL21-DE3)", "Escherichia coli (strain B / REL606)", "Escherichia coli (strain K12 / DH10B)", "Escherichia coli (strain K12 / MC4100 / BW2952)", "Escherichia coli (strain SE11)", "Escherichia coli (strain SMS-3-5 / SECEC)", "Escherichia coli (strain UM146)", "Escherichia coli (strain UTI89 / UPEC)", "Escherichia coli O103:H2 (strain 12009 / EHEC)", "Escherichia coli O104:H4 (strain 2009EL-2071)", "Escherichia coli O111:H- (strain 11128 / EHEC)", "Escherichia coli O127:H6 (strain E2348/69 / EPEC)", "Escherichia coli O139:H28 (strain E24377A / ETEC)", "Escherichia coli O150:H5 (strain SE15)", "Escherichia coli O157:H7 (strain EC4115 / EHEC)", "Escherichia coli O157:H7 (strain TW14359 / EHEC)", "Escherichia coli O157:H7 str. EDL933", "Escherichia coli O17:K52:H18 (strain UMN026 / ExPEC)", "Escherichia coli O18:K1:H7 (strain IHE3034 / ExPEC)", "Escherichia coli O1:K1 / APEC", "Escherichia coli O26:H11 (strain 11368 / EHEC)", "Escherichia coli O44:H18 (strain 042 / EAEC)", "Escherichia coli O45:K1 (strain S88 / ExPEC)", "Escherichia coli O55:H7 (strain CB9615 / EPEC)", "Escherichia coli O6:H1 (strain CFT073 / ATCC 700928 / UPEC)", "Escherichia coli O6:K15:H31 (strain 536 / UPEC)", "Escherichia coli O78:H11 (strain H10407 / ETEC)", "Escherichia coli O7:K1 (strain IAI39 / ExPEC)", "Escherichia coli O8 (strain IAI1)", "Escherichia coli O81 (strain ED1a)", "Escherichia coli O83:H1 (strain NRG 857C / AIEC)", "Escherichia coli O9:H4 (strain HS)", "Escherichia coli OR:K5:H- (strain ABU 83972)", "Escherichia coli str. K-12 substr. MG1655", "Shigella boydii serotype 18 (strain CDC 3083-94 / BS512)", "Shigella boydii serotype 4 (strain Sb227)", "Shigella dysenteriae serotype 1 (strain Sd197)", "Shigella flexneri", "Shigella flexneri serotype 5b (strain 8401)", "Shigella flexneri serotype X (strain 2002017)", "Shigella sonnei (strain Ss046)")"s__Escherichia coli", "Escherichia coli O104:H4 str. LB226692", "Escherichia fergusonii (strain ATCC 35469 / DSM 13698 / CCUG 18766 / IAM 14443 / JCM 21226 / LMG 7866 / NBRC 102419 / NCTC 12128 / CDC 0568-73)")"g__Escherichia", "Hamiltonella defensa subsp. Acyrthosiphon pisum (strain 5AT)", ("Klebsiella aerogenes (strain ATCC 13048 / DSM 30053 / CCUG 1429 / JCM 1235 / KCTC 2190 / NBRC 13534 / NCIMB 10102 / NCTC 10006 / CDC 819-56)", "Klebsiella oxytoca (strain ATCC 8724 / DSM 4798 / JCM 20051 / NBRC 3318 / NRRL B-199 / KCTC 1686 / BUCSAV 143 / CCM 1901)", ("Klebsiella pneumoniae subsp. pneumoniae (strain ATCC 700721 / MGH 78578)", "Klebsiella pneumoniae subsp. pneumoniae (strain HS11286)")"s__Klebsiella pneumoniae", ("Klebsiella pneumoniae (strain 342)", "Klebsiella variicola (strain At-22)")"s__Klebsiella variicola")"g__Klebsiella", "Enterobacter sp. (strain 638)", "Moranella endobia (strain PCIT)", (("Pantoea ananatis (strain AJ13355)", "Pantoea ananatis (strain LMG 20103)")"s__Pantoea ananatis", "Pantoea sp. (strain At-9b)", "Pantoea vagans (strain C9-1)")"g__Pantoea", ("Pectobacterium carotovorum subsp. carotovorum (strain PC1)", "Pectobacterium atrosepticum (strain SCRI 1043 / ATCC BAA-672)", ("Pectobacterium parmentieri", "Pectobacterium parmentieri (strain WPP163)")"s__Pectobacterium parmentieri")"g__Pectobacterium", ("Photorhabdus asymbiotica subsp. asymbiotica (strain ATCC 43949 / 3105-77)", "Photorhabdus laumondii subsp. laumondii (strain DSM 15139 / CIP 105565 / TT01)")"g__Photorhabdus", "Proteus mirabilis (strain HI4320)", ("Providencia rettgeri (strain Dmel1)", "Providencia stuartii (strain MRSN 2154)")"g__Providencia", "Enterobacteriaceae bacterium (strain FGI 57)", ("Rahnella sp. (strain Y9602)", "Rahnella aquatilis (strain ATCC 33071 / DSM 4594 / JCM 1683 / NBRC 105701 / NCIMB 13365 / CIP 78.65)")"g__Rahnella", ("Salmonella arizonae (strain ATCC BAA-731 / CDC346-86 / RSK2980)", "Salmonella bongori (strain ATCC 43975 / DSM 13772 / NCTC 12419)", ("Salmonella agona (strain SL483)", "Salmonella choleraesuis (strain SC-B67)", "Salmonella dublin (strain CT_02021853)", "Salmonella enterica subsp. enterica serovar Typhi str. CT18", "Salmonella enteritidis PT4 (strain P125109)", "Salmonella gallinarum (strain 287/91 / NCTC 13346)", "Salmonella heidelberg (strain SL476)", "Salmonella newport (strain SL254)", "Salmonella paratyphi A (strain AKU_12601)", "Salmonella paratyphi A (strain ATCC 9150 / SARB42)", "Salmonella paratyphi B (strain ATCC BAA-1250 / SPB7)", "Salmonella paratyphi C (strain RKS4594)", "Salmonella pullorum (strain RKS5078 / SGSC2294)", "Salmonella schwarzengrund (strain CVM19633)", "Salmonella typhimurium (strain 14028s / SGSC 2262)", "Salmonella typhimurium (strain 4/74)", "Salmonella typhimurium (strain D23580)", "Salmonella typhimurium (strain LT2 / SGSC1412 / ATCC 700720)", "Salmonella typhimurium (strain SL1344)")"s__Salmonella enterica")"g__Salmonella", ("Serratia plymuthica (strain AS9)", "Serratia proteamaculans (strain 568)")"g__Serratia", "Serratia fonticola", "Shimwellia blattae (strain ATCC 29907 / DSM 4481 / JCM 1650 / NBRC 105725 / CDC 9005-74)", "Sodalis glossinidius (strain morsitans)", ("Xenorhabdus bovienii (strain SS-2004)", "Xenorhabdus nematophila (strain ATCC 19061 / DSM 3370 / CCUG 14189 / LMG 1036 / NCIMB 9965 / AN6)")"g__Xenorhabdus", (("Yersinia enterocolitica serotype O:8 / biotype 1B (strain NCTC 13174 / 8081)", "Yersinia enterocolitica subsp. palearctica serotype O:3 (strain DSM 13030 / CIP 106945 / Y11)", "Yersinia enterocolitica subsp. palearctica serotype O:9 / biotype 3 (strain 105.5R(r))")"s__Yersinia enterocolitica", ("Yersinia pestis (strain D106004)", "Yersinia pestis (strain D182038)", "Yersinia pestis (strain Pestoides F)", "Yersinia pestis (strain Z176003)", "Yersinia pestis CO92", "Yersinia pestis bv. Antiqua (strain Angola)", "Yersinia pestis bv. Antiqua (strain Antiqua)", "Yersinia pestis bv. Antiqua (strain Nepal516)", "Yersinia pestis bv. Medievalis (strain Harbin 35)", "Yersinia pseudotuberculosis serotype I (strain IP32953)", "Yersinia pseudotuberculosis serotype IB (strain PB1/+)", "Yersinia pseudotuberculosis serotype O:1b (strain IP 31758)", "Yersinia pseudotuberculosis serotype O:3 (strain YPIII)")"s__Yersinia pestis", "Yersinia ruckeri")"g__Yersinia")"f__Enterobacteriaceae", "Kangiella koreensis (strain DSM 16069 / KCTC 12182 / SW-125)", (("Actinobacillus pleuropneumoniae serotype 3 (strain JL03)", "Actinobacillus pleuropneumoniae serotype 5b (strain L20)", "Actinobacillus pleuropneumoniae serotype 7 (strain AP76)")"s__Actinobacillus lignieresii", ("Aggregatibacter actinomycetemcomitans serotype C (strain D11S-1)", "Aggregatibacter aphrophilus (strain NJ8700)")"g__Aggregatibacter", "Avibacterium paragallinarum", "Mannheimia succiniciproducens (strain MBEL55E)", "Actinobacillus succinogenes (strain ATCC 55618 / DSM 22257 / CCUG 43843 / 130Z)", "Gallibacterium anatis (strain UMN179)", "Glaesserella parasuis serovar 5 (strain SH0165)", ("Haemophilus influenzae (strain 10810)", "Haemophilus influenzae (strain 86-028NP)", "Haemophilus influenzae (strain ATCC 51907 / DSM 11121 / KW20 / Rd)", "Haemophilus influenzae (strain PittEE)", "Haemophilus influenzae (strain PittGG)", "Haemophilus influenzae (strain R2846 / 12)", "Haemophilus influenzae (strain R2866)")"s__Haemophilus influenzae", "Haemophilus ducreyi (strain 35000HP / ATCC 700724)", "Haemophilus parainfluenzae (strain T3T1)", ("Haemophilus somnus (strain 129Pt)", "Histophilus somni (strain 2336)")"s__Histophilus somni", ("Pasteurella multocida (strain HN06)", "Pasteurella multocida (strain Pm70)")"s__Pasteurella multocida")"f__Pasteurellaceae", "Psychromonas ingrahamii (strain 37)", ("Ferrimonas balearica (strain DSM 9799 / CCM 4581 / KCTC 23876 / PAT)", ("Shewanella amazonensis (strain ATCC BAA-1098 / SB2B)", ("Shewanella baltica (strain OS155 / ATCC BAA-1091)", "Shewanella baltica (strain OS185)", "Shewanella baltica (strain OS195)", "Shewanella baltica (strain OS223)", "Shewanella baltica (strain OS678)")"s__Shewanella baltica", "Shewanella denitrificans (strain OS217 / ATCC BAA-1090 / DSM 15013)", "Shewanella frigidimarina (strain NCIMB 400)", "Shewanella halifaxensis (strain HAW-EB4)", "Shewanella loihica (strain ATCC BAA-1088 / PV-4)", "Shewanella oneidensis (strain MR-1)", "Shewanella pealeana (strain ATCC 700345 / ANG-SQ1)", "Shewanella piezotolerans (strain WP3 / JCM 13877)", ("Shewanella putrefaciens (strain 200)", "Shewanella putrefaciens (strain CN-32 / ATCC BAA-453)", "Shewanella sp. (strain W3-18-1)")"s__Shewanella putrefaciens", "Shewanella sediminis (strain HAW-EB3)", ("Shewanella sp. (strain MR-4)", "Shewanella sp. (strain MR-7)")"s__Shewanella sp000014665", "Shewanella sp. (strain ANA-3)", "Shewanella violacea (strain JCM 10179 / CIP 106290 / LMG 19151 / DSS12)", "Shewanella woodyi (strain ATCC 51908 / MS32)")"g__Shewanella")"f__Shewanellaceae", ((("Aliivibrio fischeri (strain ATCC 700601 / ES114)", "Aliivibrio fischeri (strain MJ11)")"s__Aliivibrio fischeri", "Aliivibrio salmonicida (strain LFI1238)")"g__Aliivibrio", "Photobacterium profundum (strain SS9)", ("Vibrio anguillarum (strain ATCC 68554 / 775)", "Vibrio campbellii (strain ATCC BAA-1116 / BB120)", ("Vibrio cholerae serotype O1 (strain ATCC 39315 / El Tor Inaba N16961)", "Vibrio cholerae serotype O1 (strain ATCC 39541 / Classical Ogawa 395 / O395)", "Vibrio cholerae serotype O1 (strain M66-2)", "Vibrio cholerae serotype O1 (strain MJ-1236)")"s__Vibrio cholerae", "Vibrio antiquarius (strain Ex25)", "Vibrio furnissii (strain DSM 14383 / NCTC 11218 / WDCM 00186 / VL 6966)", "Vibrio nereis", "Vibrio parahaemolyticus serotype O3:K6 (strain RIMD 2210633)", "Vibrio sp. (strain N418)", "Vibrio atlanticus (strain LGP32)", ("Vibrio vulnificus (strain CMCP6)", "Vibrio vulnificus (strain MO6-24/O)", "Vibrio vulnificus (strain YJ016)")"s__Vibrio vulnificus")"g__Vibrio")"f__Vibrionaceae")"o__Enterobacterales", (("Blochmannia floridanus", "Blochmannia pennsylvanicus (strain BPEN)", "Blochmannia vafer (strain BVAF)")"g__Blochmannia", ("Buchnera aphidicola subsp. Cinara cedri (strain Cc)", "Buchnera aphidicola subsp. Baizongia pistaciae (strain Bp)", ("Buchnera aphidicola subsp. Acyrthosiphon pisum (strain 5A)", "Buchnera aphidicola subsp. Acyrthosiphon pisum (strain APS)", "Buchnera aphidicola subsp. Acyrthosiphon pisum (strain JF98)", "Buchnera aphidicola subsp. Acyrthosiphon pisum (strain JF99)", "Buchnera aphidicola subsp. Acyrthosiphon pisum (strain LL01)", "Buchnera aphidicola subsp. Acyrthosiphon pisum (strain Tuc7)")"s__Buchnera aphidicola_I", "Buchnera aphidicola subsp. Schlechtendalia chinensis", "Buchnera aphidicola subsp. Schizaphis graminum (strain Sg)")"g__Buchnera", "Riesia pediculicola (strain USDA)", "Wigglesworthia glossinidia brevipalpis", "Zinderia insecticola (strain CARI)")"f__Enterobacteriaceae_A", ("Francisella orientalis (strain Toba 04)", "Francisella philomiragia subsp. philomiragia (strain ATCC 25017 / FSC 153 / O#319-036)", ("Francisella cf. novicida (strain Fx1)", "Francisella tularensis subsp. holarctica (strain FTNF002-00 / FTA)", "Francisella tularensis subsp. holarctica (strain LVS)", "Francisella tularensis subsp. holarctica (strain OSU18)", "Francisella tularensis subsp. mediasiatica (strain FSC147)", "Francisella tularensis subsp. novicida (strain U112)", "Francisella tularensis subsp. tularensis (strain FSC 198)", "Francisella tularensis subsp. tularensis (strain NE061598)", "Francisella tularensis subsp. tularensis (strain SCHU S4 / Schu 4)", "Francisella tularensis subsp. tularensis (strain WY96-3418)")"s__Francisella tularensis")"g__Francisella", "Halothiobacillus neapolitanus (strain ATCC 23641 / c2)", (("Legionella longbeachae serogroup 1 (strain NSW150)", ("Legionella pneumophila (strain Corby)", "Legionella pneumophila (strain Lens)", "Legionella pneumophila (strain Paris)", "Legionella pneumophila serogroup 1 (strain 2300/99 Alcoy)", "Legionella pneumophila subsp. pneumophila (strain Philadelphia 1 / ATCC 33152 / DSM 7513)")"s__Legionella pneumophila")"g__Legionella", "Legionella spiritensis", "Tatlockia micdadei")"f__Legionellaceae", ("Cycloclasticus sp. (strain P1)", "Methylococcus capsulatus (strain ATCC 33009 / NCIMB 11132 / Bath)", ("Methylobacter tundripaludum (strain ATCC BAA-1195 / DSM 17260 / SV96)", "Methylomonas methanica (strain MC09)", "Methylotuvimicrobium alcaliphilum (strain DSM 19304 / NCIMB 14124 / VKM B-2133 / 20Z)")"f__Methylomonadaceae")"o__Methylococcales", "Salinisphaera hydrothermalis (strain C41B8)", ("Alkalilimnicola ehrlichii (strain ATCC BAA-1101 / DSM 17681 / MLHE-1)", "Halorhodospira halophila (strain DSM 244 / SL1)")"f__Halorhodospiraceae", (("Methylophaga frappieri (strain ATCC BAA-2434 / DSM 25690 / JAM7)", "Methylophaga nitratireducenticrescens")"g__Methylophaga", ("Nitrosococcus halophilus (strain Nc4)", "Nitrosococcus oceani (strain ATCC 19707 / BCRC 17464 / JCM 30415 / NCIMB 11848 / C-107)", "Nitrosococcus watsoni (strain C-113)")"g__Nitrosococcus")"o__Nitrosococcales", ("Ruthia magnifica subsp. Calyptogena magnifica", "Vesicomyosocius okutanii subsp. Calyptogena okutanii (strain HA)")"f__Thioglobaceae", (("Alcanivorax borkumensis (strain ATCC 700651 / DSM 11573 / NCIMB 13689 / SK2)", "Alcanivorax dieselolei (strain DSM 16502 / CGMCC 1.3690 / MCCC 1A00001 / B-5)")"g__Alcanivorax", ("Cellvibrio japonicus (strain Ueda107)", "Saccharophagus degradans (strain 2-40 / ATCC 43961 / DSM 17024)", "Simiduia agarivorans (strain DSM 21679 / JCM 13881 / BCRC 17597 / SA1)", "Teredinibacter turnerae (strain ATCC 39867 / T7901)")"f__Cellvibrionaceae", ("Chromohalobacter salexigens (strain ATCC BAA-138 / DSM 3043 / CIP 106854 / NCIMB 13768 / 1H11)", "Halomonas elongata (strain ATCC 33173 / DSM 2581 / NBRC 15536 / NCIMB 2198 / 1H9)", "Halomonas anticariensis (strain DSM 16096 / CECT 5854 / LMG 22089 / FP35)")"f__Halomonadaceae", ("Marinomonas mediterranea (strain ATCC 700492 / JCM 21426 / NBRC 103028 / MMB-1)", "Marinomonas sp. (strain MWYL1)")"g__Marinomonas", ((("Acinetobacter baumannii (strain 1656-2)", "Acinetobacter baumannii (strain AB0057)", "Acinetobacter baumannii (strain AB307-0294)", "Acinetobacter baumannii (strain ACICU)", "Acinetobacter baumannii (strain ATCC 17978 / CIP 53.77 / LMG 1025 / NCDC KC755 / 5377)", "Acinetobacter baumannii (strain AYE)", "Acinetobacter baumannii (strain SDF)", "Acinetobacter baumannii (strain TCDC-AB0715)")"s__Acinetobacter baumannii", "Acinetobacter baylyi (strain ATCC 33305 / BD413 / ADP1)", "Acinetobacter oleivorans (strain JCM 16667 / KCTC 23045 / DR1)", "Acinetobacter calcoaceticus (strain PHEA-2)")"g__Acinetobacter", (("Moraxella catarrhalis (strain BBH18)", "Moraxella catarrhalis (strain RH4)")"s__Moraxella catarrhalis", "Moraxella nonliquefaciens")"g__Moraxella", ("Psychrobacter arcticus (strain DSM 17307 / VKM B-2377 / 273-4)", "Psychrobacter cryohalolentis (strain ATCC BAA-1226 / DSM 17306 / VKM B-2378 / K5)", "Psychrobacter sp. (strain PRwf-1)")"g__Psychrobacter")"f__Moraxellaceae", "Neptuniibacter caesariensis", ("Hahella chejuensis (strain KCTC 2396)", ("Marinobacter adhaerens (strain DSM 23420 / HP15)", "Marinobacter nauticus (strain ATCC 700491 / DSM 11845 / VT8)")"g__Marinobacter")"f__Oleiphilaceae", ("Azotobacter vinelandii (strain DJ / ATCC BAA-1303)", (("Pseudomonas aeruginosa (strain ATCC 15692 / DSM 22644 / CIP 104116 / JCM 14847 / LMG 12228 / 1C / PRS 101 / PAO1)", "Pseudomonas aeruginosa (strain LESB58)", "Pseudomonas aeruginosa (strain UCBPP-PA14)")"s__Pseudomonas aeruginosa", "Pseudomonas aeruginosa (strain PA7)", "Pseudomonas knackmussii (strain DSM 6978 / LMG 23759 / B13)")"g__Pseudomonas", ("Pseudomonas stutzeri (strain ATCC 17588 / DSM 5190 / CCUG 11256 / JCM 5965 / LMG 11199 / NBRC 14165 / NCIMB 11358 / Stanier 221)", "Pseudomonas stutzeri (strain A1501)")"g__Pseudomonas_A", ("Pseudomonas agarici", "Pseudomonas savastanoi pv. phaseolicola (strain 1448A / Race 6)", "Pseudomonas syringae pv. tomato (strain ATCC BAA-871 / DC3000)", "Pseudomonas brassicacearum (strain NFM421)", "Pseudomonas entomophila (strain L48)", "Pseudomonas fulva (strain 12-X)", "Pseudomonas fluorescens (strain Pf0-1)", ("Pseudomonas putida (strain ATCC 47054 / DSM 6125 / CFBP 8728 / NCIMB 11950 / KT2440)", "Pseudomonas putida (strain ATCC 700007 / DSM 6899 / BCRC 17059 / F1)", "Pseudomonas putida (strain BIRD-1)")"s__Pseudomonas_E hunanensis", "Pseudomonas fluorescens (strain SBW25)", "Pseudomonas mendocina (strain NK-01)", "Pseudomonas mendocina (strain ymp)", "Pseudomonas fluorescens (strain ATCC BAA-477 / NRRL B-23932 / Pf-5)", "Pseudomonas putida (strain W619)", "Pseudomonas putida (strain GB-1)", "Pseudomonas syringae pv. syringae (strain B728a)")"g__Pseudomonas_E")"f__Pseudomonadaceae")"o__Pseudomonadales", (("Hydrogenovibrio crunogenus (strain DSM 25203 / XCL-2)", "Hydrogenovibrio marinus")"g__Hydrogenovibrio", "Thiomicrospira cyclica (strain DSM 14477 / JCM 11371 / ALM1)")"f__Thiomicrospiraceae", ("Frateuria aurantia (strain ATCC 33424 / DSM 6220 / KCTC 2777 / LMG 1558 / NBRC 3245 / NCIMB 13370)", ("Lysobacter enzymogenes", "Pseudoxanthomonas suwonensis (strain 11-1)", "Pseudoxanthomonas spadix (strain BD-a59)", ("Stenotrophomonas maltophilia (strain K279a)", "Stenotrophomonas maltophilia (strain R551-3)")"g__Stenotrophomonas", (("Xanthomonas campestris pv. campestris (strain 8004)", "Xanthomonas campestris pv. campestris (strain ATCC 33913 / DSM 3586 / NCPPB 528 / LMG 568 / P 25)", "Xanthomonas campestris pv. campestris (strain B100)")"s__Xanthomonas campestris", "Xanthomonas axonopodis pv. citri (strain 306)", ("Xanthomonas oryzae pv. oryzae (strain KACC10331 / KXO85)", "Xanthomonas oryzae pv. oryzae (strain MAFF 311018)", "Xanthomonas oryzae pv. oryzae (strain PXO99A)")"s__Xanthomonas oryzae", "Xanthomonas campestris pv. vesicatoria (strain 85-10)")"g__Xanthomonas", "Xanthomonas albilineans (strain GPE PC73 / CFBP 7063)", ("Xylella fastidiosa (strain 9a5c)", "Xylella fastidiosa (strain GB514)", "Xylella fastidiosa (strain M12)", "Xylella fastidiosa (strain M23)", "Xylella fastidiosa (strain Temecula1 / ATCC 700964)")"s__Xylella fastidiosa")"f__Xanthomonadaceae")"o__Xanthomonadales")"c__Gammaproteobacteria", "Magnetococcus marinus (strain ATCC BAA-1437 / JCM 17883 / MC-1)", "Mariprofundus aestuarium")"p__Proteobacteria", "bacterium Zod_Metabat.1116", ("candidate division Zixibacteria bacterium A-C077", "Candidatus Coatesbacteria bacterium Bin_172")"p__RBG-13-66-14", "Candidatus Riflebacteria bacterium nHGRbin4", "candidate division KSB1 bacterium B21_G16", "bacterium Zod_Metabat.896", "Candidatus Acididesulfobacter guangdongensis AP2", "Candidatus Schekmanbacteria bacterium NC_groundwater_1829_Pr3_B-0.1um_41_52", ("Spirochaetes bacterium Zod_Metabat.958", ("Brachyspira hyodysenteriae (strain ATCC 49526 / WA1)", "Brachyspira intermedia (strain ATCC 51140 / PWS/A)", "Brachyspira murdochii (strain ATCC 51284 / DSM 12563 / 56-150)", "Brachyspira pilosicoli (strain ATCC BAA-1826 / 95/1000)")"g__Brachyspira", "Brevinema andersonii", "Spirochaetes bacterium GWE1_32_154 none", "Spirochaetales bacterium AS27yjCOA_89", "Spirochaetes bacterium Zod_Metabat.1289", (((("Leptospira borgpetersenii serovar Hardjo-bovis (strain JB197)", "Leptospira borgpetersenii serovar Hardjo-bovis (strain L550)")"s__Leptospira borgpetersenii", ("Leptospira interrogans serogroup Icterohaemorrhagiae serovar Lai (strain 56601)", "Leptospira interrogans serogroup Icterohaemorrhagiae serovar Lai (strain IPAV)", "Leptospira interrogans serogroup Icterohaemorrhagiae serovar copenhageni (strain Fiocruz L1-130)")"s__Leptospira interrogans")"g__Leptospira", ("Leptospira biflexa serovar Patoc (strain Patoc 1 / ATCC 23582 / Paris)", "Leptospira biflexa serovar Patoc (strain Patoc 1 / Ames)")"s__Leptospira_A biflexa")"f__Leptospiraceae", "Turneriella parva (strain ATCC BAA-1111 / DSM 21527 / NCTC 11395 / H)")"c__Leptospirae", ((("Borrelia hermsii (strain HS1 / DAH)", ("Borrelia crocidurae (strain Achema)", "Borrelia duttonii (strain Ly)", "Borrelia recurrentis (strain A1)")"s__Borrelia recurrentis", "Borrelia turicatae (strain 91E135)")"g__Borrelia", ("Borreliella afzelii (strain PKo)", ("Borreliella burgdorferi (strain ATCC 35210 / DSM 4680 / CIP 102532 / B31)", "Borreliella burgdorferi (strain N40)", "Borreliella burgdorferi (strain ZS7)")"s__Borreliella burgdorferi", "Borrelia garinii subsp. bavariensis (strain ATCC BAA-2496 / DSM 23469 / PBi)")"g__Borreliella")"f__Borreliaceae", "Sediminispirochaeta smaragdinae (strain DSM 11293 / JCM 15392 / SEBR 4228)", "Spirochaeta africana (strain ATCC 700263 / DSM 8902 / Z-7692)", (("Sphaerochaeta globosa (strain ATCC BAA-1886 / DSM 22777 / Buddy)", "Sphaerochaeta pleomorpha (strain ATCC BAA-1885 / DSM 22778 / Grapes)")"g__Sphaerochaeta", "Sphaerochaeta coccoides (strain ATCC BAA-1237 / DSM 17374 / SPN1)")"f__Sphaerochaetaceae", ("Spirochaeta thermophila (strain ATCC 700085 / DSM 6578 / Z-1203)", "Spirochaeta thermophila (strain ATCC 49972 / DSM 6192 / RI 19.B1)")"g__Spirochaeta_A", (("Treponema primitia (strain ATCC BAA-887 / DSM 12427 / ZAS-2)", "Treponema caldarium (strain ATCC 51460 / DSM 7334 / H1)", "Treponema azotonutricium (strain ATCC BAA-888 / DSM 13862 / ZAS-9)")"f__Termitinemataceae", (("Treponema pallidum (strain Nichols)", "Treponema pallidum subsp. pallidum (strain Chicago)", "Treponema pallidum subsp. pallidum (strain SS14)", "Treponema pallidum subsp. pertenue (strain CDC2)", "Treponema pallidum subsp. pertenue (strain Samoa D)", "Treponema paraluiscuniculi (strain Cuniculi A)")"s__Treponema pallidum", "Treponema denticola (strain ATCC 35405 / DSM 14222 / CIP 103919 / JCM 8153 / KCTC 15104)", "Treponema succinifaciens (strain ATCC 33096 / DSM 2489 / 6091)", "Treponema brennaborense (strain DSM 12168 / CIP 105900 / DD5/3)")"f__Treponemataceae")"o__Treponematales")"c__Spirochaetia", "Spirochaetes bacterium COTS27", "Spirochaetes bacterium Go_SlDig_bin_244")"p__Spirochaetota", "Candidatus Sumerlaea chitinivorans BY40", ("Acetomicrobium mobile (strain ATCC BAA-54 / DSM 13181 / JCM 12221 / NGA)", "Aminobacterium colombiense (strain DSM 12261 / ALA-1)", "Thermanaerovibrio acidaminovorans (strain ATCC 49978 / DSM 6589 / Su883)", "Thermovirga lienii (strain ATCC BAA-1197 / DSM 17291 / Cas60314)")"o__Synergistales", "candidate division TA06 bacterium E44_bin18", "candidate division Zixibacteria bacterium SM23_81", "Candidatus Entotheonella factor none", "Thermodesulfobium acidiphilum", "Thermosulfidibacter takaii (strain DSM 17441 / JCM 13301 / NBRC 103674 / ABI70S6)", (("Kosmotoga olearia (strain ATCC BAA-1733 / DSM 21960 / TBF 19.5.1)", ("Defluviitoga tunisiensis", "Marinitoga piezophila (strain DSM 14283 / JCM 11233 / KA3)", "Petrotoga mobilis (strain DSM 10674 / SJ95)")"f__Petrotogaceae")"o__Petrotogales", ("Pseudothermotoga lettingae (strain ATCC BAA-301 / DSM 14385 / NBRC 107922 / TMO)", (("Fervidobacterium nodosum (strain ATCC 35602 / DSM 5306 / Rt17-B1)", "Fervidobacterium pennivorans (strain DSM 9078 / Ven5)")"g__Fervidobacterium", ("Thermosipho africanus (strain TCF52B)", "Thermosipho melanesiensis (strain DSM 12029 / CIP 104789 / BI429)")"g__Thermosipho")"f__Fervidobacteriaceae", (("Thermotoga maritima (strain ATCC 43589 / DSM 3109 / JCM 10099 / NBRC 100826 / MSB8)", "Thermotoga sp. (strain RQ2)")"s__Thermotoga maritima", "Thermotoga neapolitana (strain ATCC 49049 / DSM 4359 / NBRC 107923 / NS-E)", ("Thermotoga naphthophila (strain ATCC BAA-489 / DSM 13996 / JCM 10882 / RKU-10)", "Thermotoga petrophila (strain ATCC BAA-488 / DSM 13995 / JCM 10881 / RKU-1)")"s__Thermotoga petrophila")"g__Thermotoga")"o__Thermotogales")"c__Thermotogae", "Deltaproteobacteria bacterium EsbW_18-Q3-R4-48_MAXAC.279_cln", "Chlamydiae bacterium AS06rmzACSIP_427", "bacterium RGIG7520", "Nitrospinaceae bacterium SI073_bin188", "Candidatus Hydrogenedentes bacterium J006", ("Candidatus Desantisbacteria bacterium CG2_30_40_21", "bacterium OS_PC_MetaG.mb.171", "bacterium UBA9088", "bacterium UBA9089")"p__UBA9089", "bacterium ADurb.Bin236", "Candidatus Cloacimonetes bacterium NORP72", "bacterium KR13_S3.mb.88", "bacterium SP4379", "Candidatus Eisenbacteria bacterium M_DeepCast_400m_m1_028", ("Pontiella desulfatans", ("Methylacidiphilum infernorum (isolate V4)", ("Coraliomargarita akajimensis (strain DSM 45221 / IAM 15411 / JCM 23193 / KCTC 12865 / 04OKA010-24)", "Opitutus terrae (strain DSM 11246 / JCM 15787 / PB90-1)")"o__Opitutales", "Pedosphaera parvula (strain Ellin514)", "Akkermansia muciniphila (strain ATCC BAA-835 / DSM 22959 / JCM 33894 / BCRC 81048 / CCUG 64013 / CIP 107961 / Muc)")"c__Verrucomicrobiae")"p__Verrucomicrobiota", ("candidate division TA06 bacterium 32_111", "Candidatus Cloacimonetes bacterium E29_bin43", "candidate division WOR-3 bacterium Zod_Metabat.912", "candidate division WOR-3 bacterium Zod_Metabat.145", "candidate division WOR-3 bacterium Ch92")"p__WOR-3", "bacterium ADurb.Bin243", "candidate division Zixibacteria bacterium RBG-1 none")"Bacteria", ((("Entamoeba dispar (strain ATCC PRA-260 / SAW760)", ("ENTHI", "Entamoeba histolytica (strain ATCC 30459 / HM-1:IMSS / ABRM)")"Entamoeba histolytica", "Entamoeba nuttalli (strain P19)")"Entamoeba", (("Polysphondylium pallidum (strain ATCC 26659 / Pp 5 / PN500)", "Cavenderia fasciculata (strain SH3)")"Acytosteliales", (("Dictyostelium discoideum", "Dictyostelium purpureum")"Dictyostelium", "Tieghemostelium lacteum")"Dictyosteliales")"Dictyostelia")"Evosea", "Thecamonas trahens ATCC 50062", ("GUITH", "Guillardia theta (strain CCMP2712)")"Guillardia theta", (("Bodo saltans", (((("Leishmania donovani (strain BPK282A1)", "Leishmania infantum")"Leishmania donovani species complex", "Leishmania major strain Friedlin", "Leishmania mexicana (strain MHOM/GT/2001/U1103)", "Leishmania braziliensis")"Leishmania", ("Leptomonas pyrrhocoris", "Leptomonas seymouri")"Leptomonas")"Leishmaniinae", ("Trypanosoma vivax (strain Y486)", "Trypanosoma rangeli", "Trypanosoma congolense (strain IL3000)", "Trypanosoma cruzi (strain CL Brener)", "Trypanosoma brucei brucei (strain 927/4 GUTat10.1)")"Trypanosoma")"Trypanosomatidae")"Metakinetoplastina", "Naegleria gruberi strain NEG-M")"Discoba", "Emiliania huxleyi CCMP1516", (("Giardia intestinalis (strain ATCC 50581 / GS clone H7)", "Giardia intestinalis (strain ATCC 50803 / WB clone C6)", "Giardia intestinalis (strain P15)")"Giardia intestinalis", "Trichomonas vaginalis G3")"Metamonada", (("Monosiga brevicollis", "Salpingoeca rosetta (strain ATCC 50818 / BSB-021)")"Salpingoecidae", "Capsaspora owczarzaki (strain ATCC 30864)", (((("Neolecta irregularis (strain DAH-3)", "Pneumocystis murina (strain B123)", ("Schizosaccharomyces cryophilus (strain OY26 / ATCC MYA-4695 / CBS 11777 / NBRC 106824 / NRRL Y48691)", "Schizosaccharomyces japonicus (strain yFS275 / FY16936)", "Schizosaccharomyces octosporus (strain yFS286)", "Schizosaccharomyces pombe (strain 972 / ATCC 24843)")"Schizosaccharomyces", "Protomyces lactucaedebilis", "Saitoella complicata (strain BCRC 22490 / CBS 7301 / JCM 7358 / NBRC 10748 / NRRL Y-17804)")"Taphrinomycotina", ((("Dactylellina haptotyla (strain CBS 200.50)", "Arthrobotrys oligospora (strain ATCC 24927 / CBS 115.81 / DSM 1491)")"Orbiliaceae", ("Pyronema omphalodes (strain CBS 100304)", "Tuber melanosporum (strain Mel28)")"Pezizales", (((("Exophiala dermatitidis (strain ATCC 34100 / CBS 525.76 / NIH/UT8656)", "Exophiala mesophila")"Exophiala", "Endocarpon pusillum (strain Z07020 / HMAS-L-300199)")"Chaetothyriomycetidae", (((("Aspergillus brasiliensis (strain CBS 101740 / IMI 381727 / IBT 21946)", "Aspergillus carbonarius (strain ITEM 5010)", "Aspergillus novofumigatus (strain IBT 16806)", "Aspergillus parasiticus", "Aspergillus glaucus", (("ASPAC", "Aspergillus aculeatus (strain ATCC 16872 / CBS 172.66 / WB 5094)")"Aspergillus aculeatus", "Aspergillus flavus (strain ATCC 200026 / FGSC A1120 / IAM 13836 / NRRL 3357 / JCM 12722 / SRRC 167)", "Aspergillus niger", "Aspergillus oryzae (strain ATCC 42149 / RIB 40)", "Aspergillus terreus (strain NIH 2624 / FGSC A1156)")"Aspergillus subgen. Circumdati", ("Aspergillus clavatus (strain ATCC 1007 / CBS 513.65 / DSM 816 / NCTC 3887 / NRRL 1 / QM 1276 / 107)", "Neosartorya fischeri (strain ATCC 1020 / DSM 3700 / CBS 544.65 / FGSC A1164 / JCM 1740 / NRRL 181 / WB 181)", "Neosartorya fumigata (strain ATCC MYA-4609 / Af293 / CBS 101355 / FGSC A1100)")"Aspergillus subgen. Fumigati", ("Aspergillus calidoustus", ("EMEND", "Emericella nidulans (strain FGSC A4 / ATCC 38163 / CBS 112.46 / NRRL 194 / M139)")"Emericella nidulans")"Aspergillus subgen. Nidulantes", "Aspergillus tubingensis (strain CBS 134.48)", "Aspergillus violaceofuscus (strain CBS 115571)", "Petromyces alliaceus")"Aspergillus", (("Penicillium chrysogenum", "Penicillium rubens (strain ATCC 28089 / DSM 1075 / NRRL 1951 / Wisconsin 54-1255)")"Penicillium chrysogenum species complex", "Penicillium decumbens", "Penicillium digitatum (strain PHI26 / CECT 20796)", "Penicillium italicum", "Penicillium nalgiovense", "Penicillium patulum", "Penicillium roqueforti (strain FM164)")"Penicillium")"Aspergillaceae", ("Talaromyces islandicus", "Talaromyces stipitatus (strain ATCC 10500 / CBS 375.48 / QM 6759 / NRRL 1006)")"Talaromyces")"Eurotiales", (("Ajellomyces dermatitidis (strain ER-3 / ATCC MYA-2586)", ("Ajellomyces capsulatus (strain H143)", "Ajellomyces capsulatus (strain H88)", "Ajellomyces capsulatus (strain NAm1 / WU24)")"Ajellomyces capsulatus")"Ajellomycetaceae", ("Arthroderma otae (strain ATCC MYA-4605 / CBS 113480)", "Arthroderma gypseum (strain ATCC MYA-4604 / CBS 118893)", ("Arthroderma benhamiae (strain ATCC MYA-4681 / CBS 112371)", "Trichophyton interdigitale (strain MR816)", "Trichophyton rubrum (strain ATCC MYA-4607 / CBS 118892)")"Trichophyton")"Arthrodermataceae", (("Coccidioides immitis (strain RS)", "Coccidioides posadasii (strain RMSCC 757 / Silveira)")"Coccidioides", "Uncinocarpus reesii (strain UAMH 1704)")"Onygenaceae", ("Paracoccidioides brasiliensis (strain Pb18)", "Paracoccidioides lutzii (strain ATCC MYA-826 / Pb01)")"Paracoccidioides")"Onygenales")"Eurotiomycetidae")"Eurotiomycetes", "Xylona heveae (strain CBS 132557 / TC161)", (("Botryosphaeria parva (strain UCR-NP2)", "Coniosporium apollinis (strain CBS 100218)")"Dothideomycetes incertae sedis", (("Aureobasidium pullulans", "Aureobasidium subglaciale (strain EXF-2481)")"Aureobasidium", (("Dothistroma septosporum (strain NZE10 / CBS 128990)", "Passalora fulva", "Sphaerulina musiva (strain SO2202)", ("ZYMTR", "Zymoseptoria tritici (strain CBS 115943 / IPO323)")"Zymoseptoria tritici")"Mycosphaerellaceae", "Baudoinia panamericana (strain UAMH 10762)")"Mycosphaerellales")"Dothideomycetidae", ("Epicoccum nigrum", "Leptosphaeria maculans (strain JN3 / isolate v23.1.3 / race Av1-4-5-6-7-8)", ("PHAND", "Phaeosphaeria nodorum (strain SN15 / ATCC MYA-4574 / FGSC 10173)")"Phaeosphaeria nodorum", ("Alternaria alternata", ("Cochliobolus heterostrophus (strain C5 / ATCC 48332 / race O)", "Cochliobolus sativus (strain ND90Pr / ATCC 201652)")"Bipolaris", "Cochliobolus lunatus", "Pyrenophora tritici-repentis (strain Pt-1C-BFP)")"Pleosporaceae")"Pleosporineae")"Dothideomycetes", ((("Blumeria graminis", "Uncinula necator")"Erysiphaceae", ("Marssonina brunnea f. sp. multigermtubi (strain MB_m1)", "Glarea lozoyensis (strain ATCC 20868 / MF5171)", ("Botryotinia fuckeliana (strain B05.10)", "Sclerotinia sclerotiorum (strain ATCC 18683 / 1980 / Ss-1)")"Sclerotiniaceae")"Helotiales", "Scytalidium lignicola")"Leotiomycetes", (((("Colletotrichum gloeosporioides (strain Cg-14)", ("Colletotrichum graminicola", "Colletotrichum sublineola")"Colletotrichum graminicola species complex")"Colletotrichum", ("Verticillium alfalfae (strain VaMs.102 / ATCC MYA-4576 / FGSC 10136)", ("VERDA", "Verticillium dahliae (strain VdLs.17 / ATCC MYA-4575 / FGSC 10137)")"Verticillium dahliae")"Verticillium")"Glomerellales", (("Metarhizium acridum (strain CQMa 102)", "Metarhizium rileyi (strain RCEF 4871)")"Metarhizium", ("Cordyceps confragosa", "Beauveria bassiana", "Cordyceps militaris (strain CM01)")"Cordycipitaceae", ("Hypocrea atroviridis (strain ATCC 20476 / IMI 206040)", "Hypocrea jecorina", "Hypocrea virens (strain Gv29-8 / FGSC 10586)", "Trichoderma harzianum")"Trichoderma", ("Gibberella moniliformis (strain M3125 / FGSC 7600)", ("Fusarium oxysporum f. sp. cubense (strain race 1)", "Fusarium oxysporum f. sp. lycopersici (strain 4287 / CBS 123668 / FGSC 9935 / NRRL 34936)")"Fusarium oxysporum", ("Fusarium culmorum", "Fusarium poae", "Gibberella zeae")"Fusarium sambucinum species complex", ("Fusarium vanettenii (strain ATCC MYA-4622 / CBS 123669 / FGSC 9596 / NRRL 45880 / 77-13-4)", "Nectria haematococca")"Fusarium solani species complex")"Fusarium", "Purpureocillium lilacinum", "Stachybotrys chlorohalonata (strain IBT 40285)")"Hypocreales", "Pseudallescheria apiosperma")"Hypocreomycetidae", ("Cryphonectria parasitica", ("Magnaporthiopsis poae (strain ATCC 64411 / 73-15)", ("Magnaporthe grisea", "Magnaporthe oryzae (strain 70-15 / ATCC MYA-4617 / FGSC 8958)")"Pyricularia")"Magnaporthales", "Ophiostoma piceae (strain UAMH 11346)", ((("Chaetomium globosum (strain ATCC 6205 / CBS 148.51 / DSM 1962 / NBRC 6347 / NRRL 1970)", "Chaetomium thermophilum (strain DSM 1495 / CBS 144.50 / IMI 039719)")"Chaetomium", ("THETO", "Myceliophthora thermophila (strain ATCC 42464 / BCRC 31852 / DSM 1799)")"Thermothelomyces thermophilus")"Chaetomiaceae", (("Neurospora crassa (strain ATCC 24698 / 74-OR23-1A / CBS 708.71 / DSM 1257 / FGSC 987)", "Neurospora tetrasperma (strain FGSC 2509 / P0656)")"Neurospora", "Sordaria macrospora (strain ATCC MYA-333 / DSM 997 / K(L3346) / K-hell)")"Sordariaceae")"Sordariales")"Sordariomycetidae", ("Eutypa lata (strain UCR-EL1)", "Pestalotiopsis fici (strain W106-1 / CGMCC3.15140)", "Rosellinia necatrix")"Xylariales")"Sordariomycetes")"sordariomyceta")"leotiomyceta")"Pezizomycotina", ((((("Candida albicans (strain SC5314 / ATCC MYA-2876)", "Candida albicans (strain WO-1)")"Candida albicans", "Candida maltosa (strain Xu316)")"Candida", "Lodderomyces elongisporus (strain ATCC 11503 / CBS 2605 / JCM 1781 / NBRC 1676 / NRRL YB-4239)")"Candida/Lodderomyces clade", "Debaryomyces hansenii (strain ATCC 36239 / CBS 767 / BCRC 21394 / JCM 1990 / NBRC 0083 / IGC 2968)", "Meyerozyma guilliermondii (strain ATCC 6260 / CBS 566 / DSM 6381 / JCM 1539 / NBRC 10279 / NRRL Y-324)", "Pichia sorbitophila (strain ATCC MYA-4447 / BCRC 22081 / CBS 7064 / NBRC 10061 / NRRL Y-12695)", "Scheffersomyces stipitis (strain ATCC 58785 / CBS 6054 / NBRC 10063 / NRRL Y-11545)", "Spathaspora passalidarum (strain NRRL Y-27907 / 11-Y1)", "Candida tenuis")"Debaryomycetaceae", "Yarrowia lipolytica (strain CLIB 122 / E 150)", ("Clavispora lusitaniae (strain ATCC 42720)", "Candida auris")"Clavispora", (("Cyberlindnera fabianii", "Cyberlindnera jadinii (strain ATCC 18201 / CBS 1600 / BCRC 20928 / JCM 3617 / NBRC 0987 / NRRL Y-1542)")"Cyberlindnera", "Komagataella phaffii (strain GS115 / ATCC 20864)")"Phaffomycetaceae", ("Dekkera bruxellensis", "Ogataea parapolymorpha (strain ATCC 26012 / BCRC 20466 / JCM 22074 / NRRL Y-7560 / DL-1)")"Pichiaceae", (("Eremothecium cymbalariae (strain CBS 270.75 / DBVPG 7215 / KCTC 17166 / NRRL Y-17582)", "Ashbya gossypii (strain ATCC 10895 / CBS 109.51 / FGSC 9923 / NRRL Y-1056)")"Eremothecium", "Kazachstania naganishii (strain ATCC MYA-139 / BCRC 22969 / CBS 8797 / KCTC 17520 / NBRC 10181 / NCYC 3082 / Yp74L-3)", "Kluyveromyces lactis (strain ATCC 8585 / CBS 2359 / DSM 70799 / NBRC 1267 / NRRL Y-1140 / WM37)", ("Lachancea fermentati", "Lachancea thermotolerans (strain ATCC 56472 / CBS 6340 / NRRL Y-8284)")"Lachancea", "Candida glabrata (strain ATCC 2001 / CBS 138 / JCM 3761 / NBRC 0622 / NRRL Y-65)", ("Naumovozyma castellii (strain ATCC 76901 / BCRC 22586 / CBS 4309 / NBRC 1992 / NRRL Y-12630)", "Naumovozyma dairenensis (strain ATCC 10597 / BCRC 20456 / CBS 421 / NBRC 0211 / NRRL Y-12639)")"Naumovozyma", ("Saccharomyces cerevisiae (strain ATCC 204508 / S288c)", "Saccharomyces cerevisiae (strain AWRI796)", "Saccharomyces cerevisiae (strain FostersO)", "Saccharomyces cerevisiae (strain VIN 13)")"Saccharomyces cerevisiae", ("Tetrapisispora blattae (strain ATCC 34711 / CBS 6284 / DSM 70876 / NBRC 10599 / NRRL Y-10934 / UCD 77-7)", "Tetrapisispora phaffii (strain ATCC 24235 / CBS 4417 / NBRC 1672 / NRRL Y-8282 / UCD 70-5)")"Tetrapisispora", "Vanderwaltozyma polyspora (strain ATCC 22028 / DSM 70294 / BCRC 21397 / CBS 2163 / NBRC 10782 / NRRL Y-8283 / UCD 57-17)", "Zygosaccharomyces rouxii")"Saccharomycetaceae", "Diutina rugosa")"Saccharomycetales")"saccharomyceta")"Ascomycota", (((("Auricularia subglabra (strain TFB-10046 / SS5)", "Thanatephorus cucumeris (strain AG1-IA)", "Punctularia strigosozonata (strain HHB-11173)", ("GLOTR", "Gloeophyllum trabeum (strain ATCC 11539 / FP-39264 / Madison 617)")"Gloeophyllum trabeum", "Fomitiporia mediterranea (strain MF3/22)", ("Postia placenta (strain ATCC 44394 / Madison 698-R)", "Fomitopsis pinicola (strain FP-58527)", "Grifola frondosa", "Wolfiporia cocos (strain MD-104)", ("Phanerochaete chrysosporium", "Phlebiopsis gigantea")"Phanerochaetaceae", ("Dichomitus squalens (strain LYAD-421)", ("Pycnoporus cinnabarinus", "Trametes pubescens", "Trametes versicolor (strain FP-101664)")"Trametes")"Polyporaceae")"Polyporales", ("Heterobasidion annosum", "Stereum hirsutum (strain FP-91666)")"Russulales", "Serendipita indica (strain DSM 11827)")"Agaricomycetes incertae sedis", ((("Agaricus bisporus var. bisporus", "Agaricus bisporus var. burnettii (strain JB137-S8 / ATCC MYA-4627 / FGSC 10392)")"Agaricus bisporus", "Moniliophthora perniciosa (strain FA553 / isolate CP02)", ("Armillaria gallica", "Armillaria ostoyae")"Armillaria", ("COPCI", "Coprinopsis cinerea (strain Okayama-7 / 130 / ATCC MYA-4618 / FGSC 9003)")"Coprinopsis cinerea", ("SCHCO", "Schizophyllum commune (strain H4-8 / FGSC 9210)")"Schizophyllum commune", "Hypholoma sublateritium (strain FD-334 SS-4)", "Laccaria bicolor")"Agaricales", ("Coniophora puteana (strain RWD-64-598)", "Serpula lacrymans var. lacrymans (strain S7.3)")"Coniophorineae")"Agaricomycetidae")"Agaricomycetes", "Dacryopinax primogenitus (strain DJM 731)", (((("Cryptococcus gattii", "Cryptococcus gattii serotype B (strain R265)")"Cryptococcus gattii species complex", "Cryptococcus neoformans var. neoformans serotype D (strain JEC21 / ATCC MYA-565)")"Cryptococcus", "Tremella mesenterica")"Tremellales", "Trichosporon asahii var. asahii (strain CBS 8904)")"Tremellomycetes")"Agaricomycotina", (("Microbotryum lychnidis-dioicae (strain p1A1 Lamole / MvSl-1064)", ("Rhodosporidium toruloides", "Rhodotorula graminis (strain WP1)")"Rhodotorula")"Microbotryomycetes", "Mixia osmundae (strain CBS 9802 / IAM 14324 / JCM 22182 / KY 12970)", (("PUCGR", "Puccinia graminis f. sp. tritici (strain CRL 75-36-700-3 / race SCCL)")"Puccinia graminis", "Puccinia triticina (isolate 1-1 / race 1 (BBBD))")"Puccinia")"Pucciniomycotina", ("Tilletiaria anomala (strain ATCC 24038 / CBS 436.72 / UBC 951)", ("Malassezia globosa (strain ATCC MYA-4612 / CBS 7966)", "Malassezia sympodialis (strain ATCC 42132)")"Malassezia", ("Kalmanozyma brasiliensis (strain GHG001)", ("Ustilago hordei", "Ustilago maydis (strain 521 / FGSC 9021)")"Ustilago")"Ustilaginaceae")"Ustilaginomycotina", ("Wallemia ichthyophaga (strain EXF-994 / CBS 113033)", "Wallemia mellicola (strain ATCC MYA-4683 / CBS 633.66)", "Wallemia sebi")"Wallemia")"Basidiomycota")"Dikarya", ("Allomyces macrogynus (strain ATCC 38327)", ((("BATDE", "Batrachochytrium dendrobatidis (strain JAM81 / FGSC 10211)")"Batrachochytrium dendrobatidis", ("SPIPN", "Spizellomyces punctatus (strain DAOM BR117)")"Spizellomyces punctatus")"Chytridiomycetes", "Gonapodya prolifera (strain JEL478)", "Piromyces sp. (strain E2)")"Chytridiomycota incertae sedis", "Rozella allomycis (strain CSF55)", (("Enterocytozoon bieneusi (strain H348)", (("Nosema bombycis (strain CQ1 / CVCC 102059)", "Nosema ceranae (strain BRL01)")"Nosema", "Vittaforma corneae (strain ATCC 50505)")"Nosematidae", "Spraguea lophii (strain 42_110)", "Encephalitozoon cuniculi (strain GB-M1)")"Apansporoblastina", ("Edhazardia aedis (strain USNM 41457)", ("Nematocida parisii (strain ERTm3)", "Nematocida sp. 1 (strain ERTm2 / ATCC PRA-371)")"Nematocida")"Microsporidia incertae sedis", ("Trachipleistophora hominis", "Vavraia culicis (isolate floridensis)")"Pleistophoridae")"Microsporidia", ("Rhizophagus irregularis (strain DAOM 197198w)", ("Absidia glauca", (("MUCCI", "Mucor circinelloides f. circinelloides (strain 1006PhL)")"Mucor circinelloides", ("Rhizopus delemar (strain RA 99-880 / ATCC MYA-4621 / FGSC 9543 / NRRL 43880)", "Rhizopus microsporus", "Rhizopus oryzae")"Rhizopus")"Mucorineae", "Phycomyces blakesleeanus", "Syncephalastrum racemosum")"Mucorales")"Mucoromycota", "Conidiobolus coronatus (strain ATCC 28846 / CBS 209.66 / NRRL 28638)")"Fungi incertae sedis")"Fungi", "Creolimax fragrantissima", (((((("Branchiostoma floridae", "Branchiostoma lanceolatum")"Branchiostoma", (("Petromyzon marinus", "Eptatretus burgeri")"Cyclostomata", ((("Scyliorhinus torazame", "Chiloscyllium punctatum")"Galeoidea", "Callorhinchus milii")"Chondrichthyes", (("Lepisosteus oculatus", ("Anguilla anguilla", (((("Anabas testudineus", (("Seriola dumerili", "Echeneis naucrates")"Carangiformes", ("Cynoglossus semilaevis", "Scophthalmus maximus")"Pleuronectoidei")"Carangaria", ("Gasterosteus aculeatus", "Sparus aurata", ("Mola mola", ("Takifugu rubripes", "Tetraodon nigroviridis")"Tetraodontidae")"Tetraodontiformes")"Eupercaria", ((("Oryzias javanicus", "Oryzias latipes", "Oryzias melastigma")"Oryzias", (("Nothobranchius furzeri", "Kryptolebias marmoratus")"Aplocheiloidei", ("Cyprinodon variegatus", ("Gambusia affinis", ("Poecilia formosa", "Poecilia reticulata")"Poecilia", "Xiphophorus maculatus")"Poeciliinae")"Cyprinodontoidei")"Cyprinodontiformes")"Atherinomorphae", "Salarias fasciatus", ((("Astatotilapia calliptera", "Haplochromis burtoni")"Haplochromini", "Neolamprologus brichardi", ("Oreochromis aureus", "Oreochromis niloticus")"Oreochromis")"Pseudocrenilabrinae", "Amphilophus citrinellus")"Cichlidae", ("Amphiprion ocellaris", "Amphiprion percula")"Amphiprion")"Ovalentaria", "Hippocampus comes")"Percomorphaceae", "Gadus morhua")"Acanthomorphata", ("Esox lucius", ("Salmo salar", "Salmo trutta")"Salmo")"Protacanthopterygii")"Euteleosteomorpha", ((("Astyanax mexicanus", "Pygocentrus nattereri")"Characoidei", "Electrophorus electricus", "Ictalurus punctatus")"Characiphysae", ("Sinocyclocheilus grahami", "Danio rerio")"Cyprinoidei")"Otophysi")"Clupeocephala")"Teleostei")"Neopterygii", ("Latimeria chalumnae", (((("Ornithorhynchus anatinus", "Tachyglossus aculeatus")"Monotremata", ((("Procavia capensis", "Loxodonta africana", "Echinops telfairi")"Afrotheria", (((("Oryctolagus cuniculus", "Ochotona princeps")"Lagomorpha", ("Dipodomys ordii", (("Fukomys damarensis", "Heterocephalus glaber")"Bathyergidae", ("Cavia aperea", "Cavia porcellus")"Cavia", "Chinchilla lanigera", "Octodon degus")"Hystricomorpha", ("Jaculus jaculus", ("Cricetulus griseus", ("Mus musculus", "Rattus norvegicus")"Murinae", "Nannospalax galili")"Muroidea")"Myomorpha", "Ictidomys tridecemlineatus")"Rodentia")"Glires", (((((("Cercocebus atys", "Chlorocebus sabaeus", ("Macaca fascicularis", "Macaca mulatta", "Macaca nemestrina")"Macaca", "Mandrillus leucophaeus", "Papio anubis")"Cercopithecinae", ("Colobus angolensis palliatus", ("Rhinopithecus bieti", "Rhinopithecus roxellana")"Rhinopithecus")"Colobinae")"Cercopithecidae", ((("Gorilla gorilla gorilla", "Homo sapiens", ("Pan paniscus", "Pan troglodytes")"Pan")"Homininae", "Pongo abelii")"Hominidae", "Nomascus leucogenys")"Hominoidea")"Catarrhini", ("Aotus nancymaae", ("Callithrix jacchus", "Cebus imitator", "Saimiri boliviensis boliviensis")"Cebidae")"Platyrrhini")"Simiiformes", "Carlito syrichta")"Haplorrhini", (("Microcebus murinus", "Propithecus coquereli")"Lemuriformes", "Otolemur garnettii")"Strepsirrhini")"Primates", "Tupaia belangeri")"Euarchontoglires", (((("Bos indicus x Bos taurus", "Bos taurus")"Bos", ("Capra hircus", "Ovis aries")"Caprinae")"Bovidae", "Sus scrofa", "Vicugna pacos", ("Balaenoptera musculus", "Tursiops truncatus")"Cetacea")"Artiodactyla", ((("Canis lupus familiaris", "Vulpes vulpes")"Canidae", "Mustela putorius furo", ("Ailuropoda melanoleuca", ("Ursus americanus", "Ursus maritimus")"Ursus")"Ursidae")"Caniformia", ("Felis catus", "Suricata suricatta")"Feliformia")"Carnivora", ("Pteropus vampyrus", ("Rhinolophus ferrumequinum", "Myotis lucifugus")"Microchiroptera")"Chiroptera", ("Erinaceus europaeus", "Sorex araneus")"Eulipotyphla", (("Equus asinus asinus", "Equus caballus")"Equus", "Ceratotherium simum simum")"Perissodactyla", "Manis javanica")"Laurasiatheria")"Boreoeutheria", ("Dasypus novemcinctus", "Choloepus hoffmanni")"Xenarthra")"Eutheria", ("Sarcophilus harrisii", "Monodelphis domestica", ("Notamacropus eugenii", "Phascolarctos cinereus", "Vombatus ursinus")"Diprotodontia")"Metatheria")"Theria")"Mammalia", ((("Crocodylus porosus", ("Haliaeetus leucocephalus", "Falco tinnunculus", (("ANAPL", "Anas platyrhynchos platyrhynchos")"Anas platyrhynchos", ("Meleagris gallopavo", ("Gallus gallus", "Phasianus colchicus")"Phasianinae")"Phasianidae")"Galloanserae", ("Corvus moneduloides", "Ficedula albicollis", "Parus major", "Junco hyemalis", ("Taeniopygia guttata", "Serinus canaria", "Chloebia gouldiae")"Passeroidea")"Passeriformes", ("Strigops habroptila", "Melopsittacus undulatus")"Psittaciformes", ("Athene cunicularia", "Tyto alba")"Strigiformes")"Neognathae")"Archosauria", (("Chrysemys picta bellii", "Chelonoidis abingdonii")"Testudinoidea", "Pelodiscus sinensis")"Cryptodira")"Archelosauria", ("Sphenodon punctatus", (("Podarcis muralis", "Salvator merianae")"Laterata", ("Varanus komodoensis", "Anolis carolinensis", "Pseudonaja textilis")"Toxicofera")"Episquamata")"Lepidosauria")"Sauria")"Amniota", ("Bufo bufo", ("Xenopus tropicalis", "Xenopus laevis")"Xenopus")"Anura")"Tetrapoda")"Sarcopterygii")"Euteleostomi")"Gnathostomata")"Vertebrata", ("Ciona intestinalis", "Ciona savignyi")"Ciona")"Chordata", (("Asterias rubens", ("Acanthaster planci", "Patiria miniata")"Valvatida")"Asteroidea", ("Strongylocentrotus purpuratus", "Lytechinus variegatus")"Echinacea")"Eleutherozoa")"Deuterostomia", (((((("Pristionchus pacificus", ("Caenorhabditis brenneri", "Caenorhabditis briggsae", "Caenorhabditis elegans", "Caenorhabditis japonica", "Caenorhabditis remanei")"Caenorhabditis")"Rhabditina", ("Toxocara canis", (("Brugia malayi", "Loa loa", "Onchocerca volvulus", "Wuchereria bancrofti")"Onchocercidae", "Thelazia callipaeda")"Spiruromorpha")"Spirurina", ("Strongyloides ratti", "Meloidogyne hapla")"Tylenchina")"Rhabditida", ("Necator americanus", "Angiostrongylus costaricensis", (("Haemonchus contortus", "Haemonchus placei")"Haemonchus", "Nippostrongylus brasiliensis")"Trichostrongyloidea")"Strongylida")"Chromadorea", ("Romanomermis culicivorax", "Trichinella spiralis")"Dorylaimia")"Nematoda", ((((("Sarcoptes scabiei", "Tetranychus urticae")"Acariformes", ("Ixodes scapularis", "Varroa destructor")"Parasitiformes")"Acari", "Stegodyphus mimosarum")"Arachnida", ("Strigamia maritima", (("Daphnia pulex", ("Tigriopus californicus", "Lepeophtheirus salmonis")"Podoplea")"Crustacea", (("Orchesella cincta", "Folsomia candida")"Entomobryomorpha", ((("Bombyx mori", "Helicoverpa armigera", (("Danaus plexippus", "Heliconius melpomene", ("Melitaea cinxia", "Vanessa tameamea")"Nymphalinae")"Nymphalidae", "Papilio machaon")"Papilionoidea")"Obtectomera", ("Dendroctonus ponderosae", "Tribolium castaneum")"Cucujiformia", (("Megaselia scalaris", ((("Drosophila busckii", "Drosophila grimshawi", ((("Drosophila ananassae", "Drosophila bipectinata")"ananassae subgroup", "Drosophila elegans", "Drosophila eugracilis", "Drosophila ficusphila", ("Drosophila erecta", "Drosophila melanogaster", "Drosophila sechellia", "Drosophila simulans", "Drosophila yakuba")"melanogaster subgroup", "Drosophila kikkawai", "Drosophila rhopaloa", "Drosophila suzukii", "Drosophila takahashii")"melanogaster group", (("Drosophila guanche", "Drosophila obscura")"obscura subgroup", ("Drosophila miranda", "Drosophila persimilis", "Drosophila pseudoobscura pseudoobscura")"pseudoobscura subgroup")"obscura group", "Drosophila willistoni")"Sophophora", ("Drosophila hydei", ("Drosophila arizonae", "Drosophila mojavensis", "Drosophila navojoa")"mojavensis species complex")"repleta group", ("Drosophila novamexicana", "Drosophila virilis")"virilis group")"Drosophila", "Bactrocera dorsalis")"Acalyptratae", "Lucilia cuprina")"Schizophora")"Cyclorrhapha", ("Culicoides sonorensis", ((("Anopheles stephensi", "Anopheles gambiae")"Cellia", "Anopheles sinensis", "Anopheles darlingi")"Anopheles", (("Aedes aegypti", "Aedes albopictus")"Stegomyia", "Culex quinquefasciatus")"Culicinae")"Culicidae")"Culicomorpha")"Diptera", ((("Apis mellifera", "Bombus impatiens")"Apinae", ("Linepithema humile", "Ooceraea biroi", "Camponotus floridanus", ("Atta cephalotes", "Solenopsis invicta")"Myrmicinae", "Harpegnathos saltator")"Formicidae")"Aculeata", ("Nasonia vitripennis", "Trichogramma pretiosum")"Chalcidoidea")"Apocrita")"Endopterygota", ((("Cimex lectularius", "Rhodnius prolixus")"Cimicomorpha", ("Acyrthosiphon pisum", "Diaphorina citri")"Sternorrhyncha")"Hemiptera", "Pediculus humanus subsp. corporis")"Paraneoptera", "Zootermopsis nevadensis")"Neoptera")"Hexapoda")"Pancrustacea")"Mandibulata")"Arthropoda", "Hypsibius dujardini")"Panarthropoda", "Priapulus caudatus")"Ecdysozoa", (("Helobdella robusta", ("Capitella teleta", "Capitella sp. 1")"Capitella")"Annelida", "Lingula unguis", ("Crassostrea gigas", "Octopus bimaculoides", "Lottia gigantea")"Mollusca", ((("Echinococcus granulosus", "Echinococcus multilocularis")"Echinococcus", "Taenia multiceps")"Taeniidae", "Schmidtea mediterranea", "Schistosoma mansoni")"Platyhelminthes")"Lophotrochozoa")"Protostomia")"Bilateria", ("Nematostella vectensis", "Hydra vulgaris", "Thelohanellus kitauei")"Cnidaria", "Mnemiopsis leidyi", "Trichoplax adhaerens")"Eumetazoa", "Amphimedon queenslandica")"Metazoa", "Fonticula alba")"Opisthokonta", ((("CYAME", "Cyanidioschyzon merolae (strain 10D)")"Cyanidioschyzon merolae", "Galdieria sulphuraria")"Cyanidiaceae", "Chondrus crispus")"Rhodophyta", (((((("Plasmodium gallinaceum", "Plasmodium relictum")"Plasmodium (Haemamoeba)", ("Plasmodium falciparum (isolate 3D7)", "Plasmodium falciparum (isolate Camp / Malaysia)", "Plasmodium falciparum (isolate Dd2)", "Plasmodium falciparum (isolate HB3)", "Plasmodium falciparum (isolate NF54)", "Plasmodium falciparum (isolate Palo Alto / Uganda)")"Plasmodium falciparum", ("Plasmodium cynomolgi (strain B)", "Plasmodium fragile", "Plasmodium gonderi", "Plasmodium knowlesi (strain H)", "Plasmodium malariae", "Plasmodium vivax (strain Salvador I)")"Plasmodium (Plasmodium)", ("Plasmodium berghei (strain Anka)", "Plasmodium yoelii yoelii")"Plasmodium (Vinckeia)")"Plasmodium", (("Babesia bigemina", "Babesia bovis", "Babesia microti (strain RI)")"Babesia", ("Theileria annulata", "Theileria parva")"Theileria")"Piroplasmida")"Aconoidasida", ((("Cryptosporidium muris (strain RN66)", ("CRYPV", "Cryptosporidium parvum (strain Iowa II)")"Cryptosporidium parvum")"Cryptosporidium", ("Eimeria acervulina", "Eimeria maxima", "Eimeria tenella")"Eimeria", ("Hammondia hammondi", ("TOXGO", "Toxoplasma gondii (strain ATCC 50861 / VEG)")"Toxoplasma gondii")"Sarcocystidae")"Eimeriorina", "Gregarina niphandrodes")"Conoidasida")"Apicomplexa", (((("ICHMU", "Ichthyophthirius multifiliis (strain G5)")"Ichthyophthirius multifiliis", "Tetrahymena thermophila (strain SB210)")"Hymenostomatida", "Paramecium tetraurelia", "Pseudocohnilembus persalinus")"Oligohymenophorea", "Stylonychia lemnae")"Intramacronucleata", "Vitrella brassicaformis (strain CCMP3155)", "Symbiodinium microadriaticum", "Perkinsus marinus (strain ATCC 50983 / TXsc)")"Alveolata", ("Bigelowiella natans (strain CCMP2755)", "Plasmodiophora brassicae", "Reticulomyxa filosa")"Rhizaria", ("Blastocystis hominis", (("Phaeodactylum tricornutum (strain CCAP 1055/1)", ("Thalassiosira oceanica", "Thalassiosira pseudonana CCMP1335")"Thalassiosira")"Bacillariophyta", "Nannochloropsis gaditana (strain CCMP526)", "Ectocarpus siliculosus", "Aureococcus anophagefferens")"Ochrophyta", (("Hyaloperonospora arabidopsidis (strain Emoy2)", ("Phytophthora infestans (strain T30-4)", "Phytophthora nicotianae", ("PHYPR", "Phytophthora parasitica (strain INRA-310)")"Phytophthora parasitica", "Phytophthora ramorum", "Phytophthora sojae (strain P6497)")"Phytophthora", "Plasmopara halstedii")"Peronosporaceae", "Globisporangium ultimum (strain ATCC 200006 / CBS 805.95 / DAOM BR144)", ("Saprolegnia diclina (strain VS20)", "Saprolegnia parasitica (strain CBS 223.65)")"Saprolegnia")"Oomycota")"Stramenopiles")"Sar", (((("Ostreococcus tauri", "Ostreococcus lucimarinus (strain CCE9901)")"Ostreococcus", ("Micromonas commoda (strain RCC299 / NOUM17 / CCMP2709)", "Micromonas pusilla (strain CCMP1545)")"Micromonas")"Mamiellales", (("Chlamydomonas reinhardtii", "Volvox carteri")"Chlamydomonadales", "Chlorella variabilis")"core chlorophytes")"Chlorophyta", ("Klebsormidium flaccidum", ("Chara braunii", ("Physcomitrium patens", "Marchantia polymorpha", (((("Picea glauca", "Picea sitchensis")"Picea", "Pinus taeda")"Pinaceae", ("Amborella trichopoda", (("Zostera marina", ("Asparagus officinalis", (((("Oryza brachyantha", "Oryza glaberrima", "Oryza longistaminata", "Oryza nivara", "Oryza punctata", "Oryza rufipogon", ("Oryza sativa subsp. indica", "Oryza sativa subsp. japonica")"Oryza sativa")"Oryza", ("Brachypodium distachyon", ("Hordeum vulgare subsp. vulgare", (("AEGTA", "Aegilops tauschii subsp. strangulata")"Aegilops tauschii", ("Triticum aestivum", "Triticum turgidum subsp. durum", "Triticum urartu")"Triticum")"Triticinae")"Triticeae")"Pooideae")"BOP clade", ("Eragrostis tef", (("Miscanthus sinensis", "Sorghum bicolor", "Zea mays")"Andropogoneae", ("Setaria italica", "Setaria viridis")"Setaria")"Panicoideae")"PACMAD clade")"Poaceae", "Musa acuminata subsp. malaccensis")"commelinids")"Petrosaviidae")"Liliopsida", "Papaver somniferum", (("Beta vulgaris subsp. vulgaris", "Chenopodium quinoa")"Chenopodiaceae", "Kalanchoe fedtschenkoi", ("Actinidia chinensis var. chinensis", ("Daucus carota subsp. sativus", ("Helianthus annuus", "Cynara cardunculus var. scolymus")"Asteraceae")"campanulids", ("Coffea canephora", "Erythranthe guttata", (("Nicotiana attenuata", "Nicotiana tabacum")"Nicotiana", ("Capsicum annuum", ("Solanum lycopersicum", "Solanum tuberosum")"Solanum")"Solanoideae")"Solanaceae")"lamiids")"asterids", (("Cucumis sativus", ((("Medicago truncatula", "Lotus japonicus")"Hologalegina", ("Cajanus cajan", "Glycine max", "Phaseolus vulgaris", "Phaseolus angularis")"Phaseoleae")"NPAAA clade", "Lupinus angustifolius")"50 kb inversion clade", "Quercus lobata", ("Manihot esculenta", "Populus trichocarpa")"Malpighiales", ("Cannabis sativa", (("Prunus dulcis", "Prunus persica")"Prunus", "Rosa chinensis")"Rosaceae")"Rosales")"fabids", (("Arabis alpina", ("Brassica rapa subsp. pekinensis", "Brassica napus", "Brassica oleracea var. oleracea")"Brassica", ("Arabidopsis lyrata", "Arabidopsis thaliana")"Arabidopsis", "Eutrema salsugineum")"Brassicaceae", ("Theobroma cacao", "Corchorus capsularis", ("Gossypium arboreum", "Gossypium hirsutum", "Gossypium raimondii")"Gossypium")"Malvaceae", "Eucalyptus grandis", "Citrus clementina")"malvids", "Vitis vinifera")"rosids")"Pentapetalae")"Mesangiospermae")"Magnoliopsida")"Spermatophyta", "Selaginella moellendorffii")"Tracheophyta")"Embryophyta")"Streptophytina")"Streptophyta")"Viridiplantae")"Eukaryota")"LUCA";'''
            ham = pyham.Ham(newick, orthoxml.decode(), use_internal_name=True, orthoXML_as_string=True)

            rh = ham.get_list_top_level_hogs()[0]

            fam_gt = ham2gt(rh, rh.hog_id.split('_')[0])

            j = gt2json(fam_gt)

            j['HOG'] = context['hog'].keyword

        except ValueError as e:
            raise Http404(e.message)


        return JsonResponse(j, safe=False)

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
    if settings.OMA_INSTANCE_NAME in ("full", "test", "testing"):
        template = "home.html"
    else:
        template = "home-{}.html".format(settings.OMA_INSTANCE_NAME)

    context = {'nr_genomes': len(utils.id_mapper['OMA']._genome_keys),
               'nr_proteins': utils.id_resolver.max_entry_nr,
               'nr_groups': utils.db.get_nr_oma_groups(),
               'nr_hogs': utils.db.get_nr_toplevel_hogs(),
               'release': utils.db.get_release_name(),
               'mailinglist_enabled': 'mailman_subscribe' in settings.INSTALLED_APPS,
               }
    if hasattr(settings, "PROVIDE_SCHEMA_DOT_ORG") and settings.PROVIDE_SCHEMA_DOT_ORG:
        context['use_schema_dot_org'] = True
        try:
            context['standalone_version'] = misc.get_omastandalone_versions(1)[0]
        except IndexError:
            pass

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

def go_enrichment(request):
    return render(request, "go_enrichment.html", {'form': forms.GoEnrichmentForm})

def go_enrichment_result(request, data_id=None):
    return render(request, "go_enrichment_result.html", {'data': data_id})

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

def token_search(request):

    function_mapper = {
        search.XRefSearch: ["description", "proteinid", "xref"],
        search.TaxSearch: ["taxon", "species", "taxid"],
        search.HogIDSearch: ["hog"],
        search.GOSearch: ["go"],
        search.DomainSearch: ["domain"],
        search.ECSearch: ["ec"],
        search.SequenceSearch: ["sequence"],
        search.OmaGroupSearch: ["og", 'fingerprint'],
    }

    def generate_type(prefix):

        for fn, prefixes in function_mapper.items():
            if prefix.lower() in prefixes:
                return fn

    context = {
        'results': None,
        'search': None,
        'search_raw': None,
        'search_organised': None,
        'data_entry': [],
        'data_group': [],
        'data_genomes': [],
        'max_proteins_shown':  35,
        'max_groups_shown':  1000,
        'max_genomes_shown':  False,
        'meta': {
            'taxon_found': 0,
            'entries_found': 0,
            'groups_found': 0,
        },
    }

    if request.method == 'POST':
        t0 = time.time()
        if 'submit_contact_suggestion' in request.POST:
            msg = EmailMessage(request.POST.get('query'), request.POST.get('message'), to=['contact@omabrowser.org'], from_email=request.POST.get('email'))
            msg.content_subtype = "html"
            msg.send()
            return redirect('search_suggestion_thanks')

        ## Process tokens
        try:
            raw_tokens = json.loads(request.POST.get("hidden_query", ""))
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Cannot parse query")
        tokens = [generate_type(z['prefix'])(utils.db, z['query']) for z in raw_tokens]
        context['search'] = json.dumps(raw_tokens)  # this can be reuse by js directly
        context['search_raw'] = raw_tokens

        context['search_organised'] = {
            'Protein': [],
            'Taxon': [],
            'HOG': [],
            'OMA_Group': [],
            'wildcard': [],
            'Taxon_count': 0,
            'Others': 0,
            'wildcard_count': 0
        }
        wild_card = ['sequence']
        for t in raw_tokens:
            if t['prefix'] in wild_card:
                context['search_organised']['wildcard'].append(t)
                context['search_organised']['wildcard_count'] +=1
            else:
                context['search_organised'][t['type']].append(t)

                if t['type'] == 'Taxon':
                    context['search_organised']['Taxon_count'] += 1
                else:
                    context['search_organised']['Others'] += 1
        logger.debug(f"search-prep: {time.time() - t0}sec")
        ## Only run the search if tokens
        if tokens:
            t1 = time.time()
            context['results'] = search.search(tokens, entry_limit=context['max_proteins_shown'])
            logger.debug(f"search pyoma: {time.time() - t1}")

            t1 = time.time()
            # quick access
            E = context['results'].entries
            G = context['results'].groups
            S = context['results'].species
            A = context['results'].ancestral_genomes
            T = context['search_organised']

            context['meta']['entries_found'] = len(E) if E else 0
            context['meta']['groups_found'] = len(G) if G else 0
            context['meta']['taxon_found'] = (len(S) if S else 0) + (len(A) if A else 0)

            # Prepare entry results
            if E:
                t2 = time.time()
                entries_all = list(E.values())
                if len(entries_all) > context['max_proteins_shown']:
                    # if we found a main isoform marked all the alternative to be removed
                    isoforms = []
                    for e in entries_all:
                        if e.is_main_isoform:
                            for ai in e.alternative_isoforms:
                                isoforms.append(ai.entry_nr)

                    for p in entries_all:
                        p.importance_score = 0

                        if '_' in p.canonicalid:
                            p.importance_score += 10

                        if p.oma_group != 0:
                            p.importance_score += 1

                        if p.oma_hog != 0:
                            p.importance_score += 1

                        if p.entry_nr in isoforms:
                            p.importance_score = -1

                    sorted_entries = sorted(entries_all, key=lambda x: x.importance_score, reverse=True)
                    entries = sorted_entries[:context['max_proteins_shown']]
                else:
                    entries = entries_all

                # redirect to entry page is only searching for protein and get one match
                if (len(entries) == 1 and not T['OMA_Group'] and not T['HOG'] and not T['wildcard']):
                    return redirect('pairs', entries[0].entry_nr)

                # looking at entries founded by protein for mode and aligned part

                for tok in tokens:
                    if isinstance(tok, search.SequenceSearch):
                        for key, entry_aligned in tok.get_matched_seqs().items():
                            es = [i for i in entries if i.entry_nr == key]
                            if len(es) == 0:
                                continue
                            e = es[0]
                            if type(entry_aligned.alignment) is tuple:
                                a = entry_aligned.alignment[0][0]
                            else:
                                a = str(entry_aligned.alignment, 'utf-8')
                            e.sequence = {"sequence": entry_aligned.sequence, 'align': a}

                logger.debug(" post-entry w/o json: {}sec".format(time.time()-t2))
                t2 = time.time()
                # Build json data for table
                context['data_entry'] = json.dumps(EntrySearchJson().as_json(entries))
                logger.debug(" post-entry json: {}sec".format(time.time() - t2))

            # Prepare groups results
            if G:
                t2 = time.time()
                hogs = []
                ogs = []

                for group in G.values():
                    if isinstance(group, models.HOG):
                        group.fingerprint = None
                        group.type = 'HOG'
                        hogs.append(group)
                    elif isinstance(group, models.OmaGroup):
                        group.level = 'God' # todo ?
                        group.type = 'OMA_Group'
                        ogs.append(group)
                    else:
                        logger.error("Search groups: {} can't be assign as HOG or OmaGroup".format(group))

                # redirect to hog page is only searching for hog and get one match
                if len(hogs) == 1 and len(ogs) == 0 and not T['OMA_Group'] and not T['Protein'] and not T['wildcard']:
                    return redirect('hog_viewer',  hogs[0].hog_id)

                # redirect to omagroup page if only searching for og and get one match
                if len(hogs) == 0 and len(ogs) == 1 and not T['HOG'] and not T['Protein'] and not T['wildcard']:
                    return redirect('omagroup_members', ogs[0].group_nbr)

                logger.debug(" post-group w/o json: {}sec".format(time.time() - t2))
                t2 = time.time()
                context['data_group'] = json.dumps(HOGSearchJson().as_json(hogs) + OGSearchJson().as_json(ogs))
                logger.debug(" post-group json: {}sec".format(time.time() - t2))

            # Prepare genomes results
            if S or A:
                t2 = time.time()

                def augment_ancestral_genomes(ag): #todo better
                    ag.uniprot_species_code = ''
                    ag.species_and_strain_as_dict = ag.sciname
                    if not hasattr(ag, 'common_name'):
                        ag.common_name = ''
                    ag.last_modified = ''
                    ag.nr_entries = ag.nr_genes
                    ag.type = "Ancestral"
                    return ag


                # easy peasy
                number_species = len(S) if S else 0
                number_ancestral = len(A) if A else 0

                # redirect to genome page is only searching for genome and get one match
                if (number_species == 1 and number_ancestral == 0 and not T['OMA_Group'] and not T['HOG'] and not T['wildcard'] and not T['Protein']):
                    return redirect('genome_info', list(S.values())[0].uniprot_species_code)

                # redirect to ancestral genome page is only searching for genome and get one match
                if (number_species == 0 and number_ancestral == 1 and not T['OMA_Group'] and not T['HOG'] and not T[
                    'wildcard'] and not T['Protein']):
                    return redirect('ancestralgenome_info', list(A.values())[0].ncbi_taxon_id)

                species_augmented = list(S.values())
                for s_aug in species_augmented:
                    s_aug.type = "Extant"

                logger.debug(" post-species w/o json: {}sec".format(time.time() - t2))
                t2 = time.time()
                # build json for genomes tables
                result_list = species_augmented + [augment_ancestral_genomes(ag) for ag in A.values()]
                result_list.sort(key=lambda g: (-g.match_score, g.sciname))
                context['data_genomes'] = json.dumps(GenomeModelJsonMixin().as_json(result_list))
                logger.debug(" post-species json: {}sec".format(time.time() - t2))

            # Prepare details per term
            E_details = []
            G_details = []
            S_details = []

            max_entries_founded = 0

            for to in tokens:

                count_entries = to.count_entries()

                if (count_entries > max_entries_founded): max_entries_founded = count_entries
                E_details.append("{} {}: {} proteins".format(to.term, function_mapper[type(to)], count_entries))
                G_details.append("{} {}: {} groups".format(to.term, function_mapper[type(to)], to.count_groups()))
                S_details.append("{} {}: {} extant species".format(to.term, function_mapper[type(to)], to.count_species()))
                S_details.append("{} {}: {} ancestral species".format(to.term, function_mapper[type(to)], to.count_ancestral_genomes()))
            context['max_entries_founded'] = max_entries_founded
            context['E_details'] = E_details
            context['G_details'] = G_details
            context['S_details'] = S_details
            logger.debug(f"search-post-pyoma: {time.time() - t1}sec")
        logger.debug(f"overall search: {time.time()-t0}sec")

    return render(request, 'search_token.html', context)

#<editor-fold desc="Search Widget">



class EntrySearchJson(JsonModelMixin):
    json_fields = {'omaid': 'protid', 'genome.kingdom': 'kingdom',
                   'genome.species_and_strain_as_dict': 'taxon',
                   'canonicalid': 'xrefid', 'oma_group': None,
                   'hog_family_nr': 'roothog', 'xrefs': None,
                   'description': None,
                   "sequence" : "sequence"}



class GenomeModelJsonMixin(JsonModelMixin):
    json_fields = {'uniprot_species_code': None,
                   "species_and_strain_as_dict": 'sciname',
                   'ncbi_taxon_id': "ncbi",
                   "common_name": None,
                   "nr_entries": "prots",
                   "kingdom": None,
                   "last_modified": None,
                   "type": "type"}

class GenomeModelJsonTableMixin(JsonModelMixin):
    json_fields = {'uniprot_species_code': None,
                   "species_and_strain_as_dict": 'sciname',
                   'ncbi_taxon_id': "ncbi",
                   "common_name": None,
                   "nr_entries": "prots",
                   "nr_genes": None,
                   "kingdom": None,
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
        'fingerprint': 'fingerprint'}


class OGSearchJson(JsonModelMixin):

    json_fields = {
        'group_nbr': 'group_nr',
        'level': 'level',
        'nr_member_genes': 'size',
        'type': 'type',
        'fingerprint': 'fingerprint'}


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
            og["type"] = 'OMA_group'
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

                    # check if query is in found match (e.g if search "DHE5_YEAST" we prefer keep this in url than "12")
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
        :param redirect_valid: if a perfect matched if found we directly goes to the related page
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
        :param redirect_valid: if a perfect matched if found we directly goes to the related page
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
