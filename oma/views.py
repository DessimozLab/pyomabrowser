# -*- coding: utf-8 -*-

from __future__ import print_function, division

import shlex
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
from django.core.urlresolvers import reverse
from django.core.mail import EmailMessage
from django.template import Context
from django.template.loader import render_to_string, get_template

from collections import OrderedDict
import tweepy
import logging
import itertools
import os
import re
import time
import glob
import json

from . import tasks
from . import utils
from . import misc
from . import forms
from .models import FileResult
from pyoma.browser import db, models

logger = logging.getLogger(__name__)


class EntryCentricMixin(object):
    def get_entry(self, entry_id):
        """resolve any ID and return an entry or a 404 if it is unknown"""
        try:
            entry_nr = utils.id_resolver.resolve(entry_id)
        except (db.InvalidId, db.AmbiguousID):
            raise Http404('requested id is unknown')
        entry = utils.db.entry_by_entry_nr(entry_nr)
        return models.ProteinEntry(utils.db, entry)


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
                        if isinstance(obj, classmethod):
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

    context = {'positions': positions, 'windows': windows,
               'md': md_geneinfos, 'o_md': o_md_geneinfos, 'colors': colors,
               'stripes': stripes, 'nr_vps': len(orthologs),
               'entry': entry,
               'tab': 'synteny', 'xrefs': xrefs
    }
    return render(request, 'synteny.html', context)


class PairsBase(ContextMixin, EntryCentricMixin):
    """Base class to collect data for pairwise orthologs."""
    def get_context_data(self, entry_id, **kwargs):
        context = super(PairsBase, self).get_context_data(**kwargs)
        entry = self.get_entry(entry_id)
        vps_raw = sorted(utils.db.get_vpairs(entry.entry_nr), key=lambda x: x['RelType'])
        close_paralogs = utils.db.get_within_species_paralogs(entry.entry_nr)
        vps = []
        for rel in itertools.chain(vps_raw, close_paralogs):
            pw_relation = models.ProteinEntry.from_entry_nr(utils.db, rel['EntryNr2'])
            pw_relation.reltype = rel['RelType']
            if len(rel['RelType']) == 3:
                pw_relation.reltype += " ortholog"
            vps.append(pw_relation)

        entry.reltype = 'self'
        if entry._entry['AltSpliceVariant'] in (0, entry.entry_nr):
            entry.alt_splicing_variant = entry.omaid
        else:
            entry.alt_splicing_variant = utils.id_mapper['OMA'].map_entry_nr(entry._entry['AltSpliceVariant'])

        longest_seq = 0
        if len(vps) > 0:
            longest_seq = max(e.sequence_length for e in vps)
        context.update(
            {'entry': entry,
             'vps': vps, 'nr_vps': len(vps_raw), 'tab': 'orthologs',
             'longest_seq': longest_seq})
        return context


class PairsJson(PairsBase, JsonModelMixin, View):
    json_fields = {'omaid': 'protid', 'genome.kingdom': 'kingdom',
                   'genome.species_and_strain_as_dict': 'taxon',
                   'canonicalid': 'xrefid', 'reltype': None}

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        data = list(self.to_json_dict(context['vps']))
        return JsonResponse(data, safe=False)


class PairsView(TemplateView, PairsBase):
    template_name = "pairs.html"


class PairsViewFasta(FastaView, PairsBase):
    """returns a fasta represenation of all the pairwise orthologs"""
    def get_fastaheader(self, memb):
        return ' | '.join(
                [memb.omaid, memb.canonicalid, memb.reltype,
                 '[{}]'.format(memb.genome.sciname)])

    def render_to_response(self, context, **kwargs):
        return self.render_to_fasta_response(itertools.chain([context['entry']], context['vps']))


class FamBase(ContextMixin, EntryCentricMixin):

    def get_context_data(self, entry_id, **kwargs):
        context = super(FamBase, self).get_context_data(**kwargs)
        entry = self.get_entry(entry_id)
        fam_members = [models.ProteinEntry(utils.db, z) for z in
                       utils.db.member_of_fam(utils.db.hog_family(entry.entry_nr))]
        context.update({'entry': entry, 'fam_members': fam_members})
        return context


class FamGeneDataJson(FamBase, JsonModelMixin, View):
    json_fields = {'entry_nr': 'id', 'omaid': 'protid', 'sequence_length': None,
                   'genome.species_and_strain_as_dict': 'taxon',
                   'canonicalid': 'xrefid', 'gc_content': None}

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        data = [x for x in self.to_json_dict(context['fam_members'])]
        response = JsonResponse(data, safe=False)
        response['Access-Control-Allow-Origin'] = '*'
        return response


class InfoBase(ContextMixin, EntryCentricMixin):
    def get_context_data(self, entry_id, **kwargs):
        context = super(InfoBase, self).get_context_data(**kwargs)
        entry = self.get_entry(entry_id)
        context.update({'entry': entry})
        return context


class InfoView(InfoBase, TemplateView):
    template_name = "info.html"

    def get_context_data(self, entry_id, **kwargs):
        context = super(InfoView, self).get_context_data(entry_id, **kwargs)
        context['nr_vps'] = utils.db.count_vpairs(context['entry'].entry_nr)
        context['tab'] = 'info'
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
        context.update(
            {'entry': entry, 'nr_vps': utils.db.count_vpairs(entry.entry_nr),
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
            raise Http404(str(e))
        response = HttpResponse(content_type='text/plain')
        response.write(orthoxml)
        response['Access-Control-Allow-Origin'] = '*'
        return response


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


@method_decorator(never_cache, name='dispatch')
class HOGsMSA(AsyncMsaMixin, HOGsBase, TemplateView):
    template_name = "hog_msa.html"

    def get_context_data(self, entry_id, level, **kwargs):
        context = super(HOGsMSA, self).get_context_data(entry_id, level)
        context.update(self.get_msa_results('hog', context['entry'].entry_nr, level))
        return context


class HOGsVis(EntryCentricMixin, TemplateView):
    template_name = "hog_vis.html"
    show_internal_labels = True

    def get_context_data(self, entry_id, idtype='OMA', **kwargs):
        context = super(HOGsVis, self).get_context_data(**kwargs)
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


class HogVisWithoutInternalLabels(HOGsVis):
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


class HOGDomainsJson(HOGDomainsBase, View):
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
    return render(request, "genome_suggestion.html", {'form': form})


class Release(TemplateView):
    template_name = 'release.html'

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


class GenomeModelJsonMixin(JsonModelMixin):
    json_fields = {'uniprot_species_code': None,
                   "species_and_strain_as_dict": 'sciname',
                   'ncbi_taxon_id': "ncbi",
                   "common_name": None,
                   "nr_entries": "prots", "kingdom": None,
                   "last_modified": None}


class GenomesJson(GenomeModelJsonMixin, View):
    def get(self, request, *args, **kwargs):
        genome_key = utils.id_mapper['OMA']._genome_keys
        lg = [models.Genome(utils.db, utils.db.id_mapper['OMA'].genome_table[utils.db.id_mapper['OMA']._entry_off_keys[e - 1]]) for e in genome_key]
        data = list(self.to_json_dict(lg))
        return JsonResponse(data, safe=False)


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
    return render(request, "export_marker.html", context={'max_nr_genomes': 200})


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
    return render(request, "function_projection_upload.html",
                  {'form': form, 'max_upload_size': form.fields['file'].max_upload_size / (2**20)})


class EntrySearchJson(JsonModelMixin):
    json_fields = {'omaid': 'protid', 'genome.kingdom': 'kingdom',
                   'genome.species_and_strain_as_dict': 'taxon',
                   'canonicalid': 'xrefid', 'oma_group': None,
                   'hog_family_nr': 'roothog', 'xrefs': None,
                   'description': None}


class Searcher(View):
    _allowed_functions = ['id', 'group', 'sequence', 'species', 'fulltext']

    def search_id(self, request, query):
        context = {'query': query, 'search_method': 'id'}
        try:
            entry_nr = utils.id_resolver.resolve(query)
            return redirect('entry_info', entry_nr)
        except db.AmbiguousID as ambiguous:
            logger.info("query {} maps to {} entries".format(query, len(ambiguous.candidates)))
            entries = [models.ProteinEntry.from_entry_nr(utils.db, entry) for entry in ambiguous.candidates]
        except db.InvalidId as e:
            entries = []
            context['message'] = "Could not find any protein matching '{}'".format(query)
        context['data'] = json.dumps(EntrySearchJson().as_json(entries))
        return render(request, 'disambiguate_entry.html', context=context)

    def search_group(self, request, query):
        try:
            group_nr = utils.db.resolve_oma_group(query)
            return redirect('omagroup', group_nr)
        except db.AmbiguousID as ambiguous:
            logger.info('search_group results in ambiguous match: {}'.format(ambiguous))
            context = {'query': query, 'search_method': 'group',
                       'data': json.dumps([utils.db.oma_group_metadata(grp) for grp in ambiguous.candidates])}
            return render(request, "disambiguate_group.html", context=context)

    def search_species(self, request, query):
        try:
            species = utils.id_mapper['OMA'].identify_genome(query)
            return redirect('/cgi-bin/gateway.pl?f=DisplayOS&p1={}'
                            .format(species['UniProtSpeciesCode'].decode()))
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

    def check_term_for_entry_nr(self, term):
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
                    return self._genome_entries_from_taxonomy(utils.db.tax.get_subtaxonomy_rooted_at(id_))
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

    def search_fulltext(self, request, query):
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

    def get(self, request):
        try:
            func = request.GET.get('type', 'id').lower()
            query = request.GET.get('query', '')
            if func not in self._allowed_functions:
                raise ValueError('invalid query type')
            meth = getattr(self, "search_"+func)
            return meth(request, query)
        except ValueError as e:
            return HttpResponseBadRequest(str(e))

    def post(self, request):
        try:
            func = request.POST.get('type', 'id').lower()
            query = request.POST.get('query', '')
            if func not in self._allowed_functions:
                return HttpResponseBadRequest()
            meth = getattr(self, "search_"+func)
            return meth(request, query)
        except ValueError as e:
            return HttpResponseBadRequest(str(e))


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
    template_name = "current.html"
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
    template_name = "archives.html"

    def get_release_data(self, release):
        res = {}
        if release is not None:
            res['id'] = release
            res['name'] = self._name_from_release(release)
            res['date'] = res['name'].replace(' ', '')
        return res

    def download_root(self, context):
        return "/" + context['release'].get('id', '')


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


class OMAGroupBase(ContextMixin):
    def get_context_data(self, group_id, **kwargs):
        context = super(OMAGroupBase, self).get_context_data(**kwargs)
        try:
            context['members'] = [utils.ProteinEntry(e) for e in utils.db.oma_group_members(group_id)]
            context.update(utils.db.oma_group_metadata(context['members'][0].oma_group))
        except db.InvalidId as e:
            raise Http404(e)
        return context


class OMAGroupFasta(FastaView, OMAGroupBase):
    def get_fastaheader(self, memb):
        return ' | '.join([memb.omaid, memb.canonicalid, "OMAGroup:{:05d}".format(memb.oma_group), '[{}]'.format(memb.genome.sciname)])

    def render_to_response(self, context):
        return self.render_to_fasta_response(context['members'])


class OMAGroupJson(OMAGroupBase, JsonModelMixin, View):
    json_fields = {'omaid': 'protid', 'genome.kingdom': 'kingdom',
                   'genome.species_and_strain_as_dict': 'taxon',
                   'canonicalid': 'xrefid', 'description': None}

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        data = list(self.to_json_dict(context['members']))
        return JsonResponse(data, safe=False)


class OMAGroup(OMAGroupBase, TemplateView):
    template_name = "omagroup.html"

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
