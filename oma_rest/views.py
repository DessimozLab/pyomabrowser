import functools
import json as _json
import operator
import itertools
import os
import time
from  datetime import datetime
import networkx as nx
import numpy
import pyoma.browser.exceptions
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

from .tasks import go_enrichment

try:
    from Bio.Alphabet import IUPAC
except ImportError:
    IUPAC = None
import collections

from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet
from rest_framework.generics import CreateAPIView, RetrieveAPIView, GenericAPIView
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, ParseError, ValidationError
from rest_framework.settings import api_settings
from rest_framework import status
from rest_framework_csv.renderers import CSVRenderer
from distutils.util import strtobool
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from packaging.version import Version as _Version

from . import models as rest_models
from . import serializers
from .renderers import NewickRenderer, NewickTextNhRenderer, PhyloXMLRenderer, PhyloXMLLegacyRenderer
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes
from .pagination import PaginationMixin, LazyPagedPytablesQuery
from .renderers import TSVRenderer

from oma import utils, misc, tasks as oma_tasks
from oma.models import FileResult
from oma.views import AsyncJobMixin as _AsyncJobMixin
from pyoma.browser import models, db
from pyoma.browser.idmapper import NoSearchXrefIdMapper
import logging


class _ProfileJobHelper(_AsyncJobMixin):
    job_model = FileResult
    task = oma_tasks.compute_similar_profile

from collections import Counter
from rest_framework.decorators import action, api_view

logger = logging.getLogger(__name__)

def resolve_protein_from_id_or_raise(id):
    try:
        return utils.id_resolver.resolve(id)
    except db.InvalidId:
        raise NotFound("requested id '{}' is unknown".format(id))
    except db.AmbiguousID:
        raise NotFound("requested id '{}' is not unique".format(id))


_ENTRY_ID_PARAM = OpenApiParameter(
    'entry_id',
    location=OpenApiParameter.PATH,
    type={"oneOf": [{"type": "string"},{"type": "integer"}]},
    description='A unique protein identifier: entry number (integer), OMA ID (e.g. HUMAN00001), or canonical ID (e.g. P12345).',
)

_HOG_ID_PARAM = OpenApiParameter(
    'hog_id',
    location=OpenApiParameter.PATH,
    type={"oneOf": [{"type": "string"},{"type": "integer"}]},
    description='A unique HOG identifier starting with "HOG:" (e.g. HOG:0001221.1a), or a protein identifier. If a protein identifier is specified, the most specific HOG to which the protein belongs is then used.',
    pattern=r'^(HOG:[A-Z]*[0-9]+(\..+)?|[A-Z0-9]+[0-9]+)$',
)

_OMA_GROUP_PARAM = OpenApiParameter(
    'group_id',
    location=OpenApiParameter.PATH,
    type=str,
    description='A unique OMA group identifier: group number, fingerprint, or a member protein ID.',
)

_GENOME_ID_PARAM = OpenApiParameter(
    'genome_id',
    location=OpenApiParameter.PATH,
    type={"oneOf": [{"type": "string"},{"type": "integer"}]},
    description='A unique genome identifier: NCBI taxon ID or UniProt species code (e.g. HUMAN).',
)

_LEVEL_PARAM = OpenApiParameter(
    'level',
    location=OpenApiParameter.QUERY,
    type=str,
    required=False,
    description='Taxonomic level to restrict the query. The special value "root" uses the deepest level of the HOG.',
)

_SYNTENY_LEVEL_PARAM = OpenApiParameter(
    'level',
    location=OpenApiParameter.QUERY,
    type=str,
    required=True,
    description=(
        'Taxonomic level at which to retrieve ancestral synteny. '
        'Can be a numeric taxid, scientific name, or UniProt mnemonic species code '
        'for extant genomes.'
    ),
)

_SYNTENY_EVIDENCE_PARAM = OpenApiParameter(
    'evidence',
    location=OpenApiParameter.QUERY,
    type=str,
    enum=['linearized', 'parsimonious', 'any'],
    required=False,
    description=(
        'Evidence filter for the ancestral synteny graph. '
        'Values: "linearized" (default) < "parsimonious" < "any".'
    ),
)

_SYNTENY_BREAK_CIRCULAR_CONTIGS_PARAM = OpenApiParameter(
    'break_circular_contigs',
    location=OpenApiParameter.QUERY,
    type=bool,
    required=False,
    default=True,
    description=(
        'Break circular contigs at their weakest edge. '
        'Default: yes. Has no effect if evidence is not "linearized".'
    ),
)


# Create your views here.
class ProteinEntryViewSet(ViewSet):
    serializer_class = serializers.ProteinEntryDetailSerializer
    lookup_field = 'entry_id'

    @extend_schema(
        request={'application/json': {
            'type': 'object',
            'required': ['ids'],
            'properties': {
                'ids': {
                    'type': 'array',
                    'items': {'oneOf': [{'type': 'string'}, {'type': 'integer'}]},
                    'maxItems': 1000,
                    'description': 'List of protein identifiers (entry numbers, OMA IDs, or canonical IDs)',
                    'example': [1, 'HUMAN5231', 523, 122, 'P12345'],
                }
            }
        }},
        responses=serializers.XRef2ProteinDetailSerializer(many=True),
    )
    @action(detail=False, methods=['post'])
    def bulk_retrieve(self, request, format=None):
        """Retrieve the information available for multiple protein IDs at once.

        The POST request must contain a json-encoded list of up to 1000 protein IDs.
        In case the ID is not unique or unknown, an empty element is returned for
        that query element.

        **Changed in version 1.7**: the endpoint now returns a list of (query_id, target)
        tuples instead of a plain list of proteins.  Clients that need the old behaviour
        can pin the version with `Accept: application/json; version=1.6`.
        """
        MAX_SIZE = 1000
        if 'ids' not in request.data:
            raise NotFound("No results found")
        if len(request.data['ids']) > MAX_SIZE:
            raise ParseError("POST request exceeded max number of ids. Please limit to {}".format(MAX_SIZE))

        proteins = []
        requested_version = tuple(map(int, request.version.split('.')))

        for entry_id in request.data['ids']:
            try:
                entry_nr = utils.id_resolver.resolve(entry_id)
                pe = models.ProteinEntry.from_entry_nr(utils.db, entry_nr)
                if requested_version < (1, 7):
                    proteins.append(pe)
                else:
                    proteins.append({'query_id': entry_id, 'target': models.ProteinEntry.from_entry_nr(utils.db, entry_nr)})
            except (db.InvalidId, db.AmbiguousID):
                if requested_version >= (1, 7):
                    proteins.append({'query_id': entry_id, 'target': None})
        serializer_cls = serializers.XRef2ProteinDetailSerializer if requested_version >= (1, 7) else serializers.ProteinEntryDetailSerializer
        serializer = serializer_cls(instance=proteins, many=True, context={'request': request})
        return Response(serializer.data)

    @extend_schema(
        parameters=[_ENTRY_ID_PARAM],
    )
    def retrieve(self, request, entry_id: str|int, format=None):
        """Retrieve the information available for a protein entry."""
        entry_nr = resolve_protein_from_id_or_raise(entry_id)
        protein = models.ProteinEntry.from_entry_nr(utils.db, entry_nr)
        serializer = serializers.ProteinEntryDetailSerializer(
            instance=protein, context={'request': request})
        return Response(serializer.data)

    @extend_schema(
        parameters=[
            _ENTRY_ID_PARAM,
            OpenApiParameter(
                'rel_type',
                location=OpenApiParameter.QUERY,
                type=str,
                required=False,
                enum=['1:1', '1:n', 'm:1', 'm:n'],
                description='Filter for orthologs of a specific relationship type only (e.g. "1:1"). If not specified, all orthologs are returned.',
            ),
        ],
        responses=serializers.OrthologsListSerializer(many=True),
    )
    @action(detail=True)
    def orthologs(self, request, entry_id: str|int, format=None):
        """List of all the identified pairwise orthologues for a protein.

        Filtering specific subtypes of orthology is possible by specifying the
        rel_type query parameter.
        """
        rel_type = request.query_params.get('rel_type', None)
        p_entry_nr = resolve_protein_from_id_or_raise(entry_id)
        data = utils.db.get_vpairs(int(p_entry_nr))
        content = []
        for row in data:
            ortholog = models.ProteinEntry.from_entry_nr(utils.db, int(row['EntryNr2']))
            ortholog.rel_type = row['RelType']
            ortholog.distance = row['Distance']
            ortholog.score = row['Score']
            if rel_type is not None:
                if rel_type == ortholog.rel_type:
                    content.append(ortholog)
            else:
                content.append(ortholog)
        serializer = serializers.OrthologsListSerializer(instance=content, many=True, context={'request': request})
        return Response(serializer.data)

    @extend_schema(
        parameters=[_ENTRY_ID_PARAM],
        responses=serializers.OrthologsListRelTypeSerializer(many=True),
    )
    @action(detail=True)
    def hog_derived_orthologs(self, request, entry_id: str|int, format=None):
        """List of the orthologs derived from the HOG for a given protein."""
        p_entry_nr = resolve_protein_from_id_or_raise(entry_id)
        data = utils.db.get_hog_induced_pairwise_orthologs(p_entry_nr)
        content = []
        for e in data:
            ortholog = models.ProteinEntry(utils.db, e)
            ortholog.rel_type = e['RelType'].decode()
            content.append(ortholog)
        serializer = serializers.OrthologsListRelTypeSerializer(instance=content, many=True, context={'request': request})
        return Response(serializer.data)

    @extend_schema(
        parameters=[_ENTRY_ID_PARAM],
        responses=serializers.ProteinEntrySerializer(many=True),
    )
    @action(detail=True)
    def homoeologs(self, request, entry_id: str|int, format=None):
        """List of all the homoeologs for a given protein.

        Only applicable to proteins from polyploid genomes.
        """
        entry_nr = resolve_protein_from_id_or_raise(entry_id)
        protein = models.ProteinEntry.from_entry_nr(utils.db, int(entry_nr))
        if not protein.genome.is_polyploid:
            raise NotFound("query protein does not belong to a polyploid genome")
        homoeologs = []
        for row in utils.db.get_within_species_paralogs(int(entry_nr)):
            if row['RelType'] != "homeolog":
                continue
            hom = models.ProteinEntry.from_entry_nr(utils.db, int(row['EntryNr2']))
            homoeologs.append(hom)
        serializer = serializers.ProteinEntrySerializer(instance=homoeologs, many=True, context={'request': request})
        return Response(serializer.data)

    @extend_schema(
        parameters=[_ENTRY_ID_PARAM],
    )
    @action(detail=True)
    def gene_ontology(self, request, entry_id: str|int, format=None):
        """Gene ontology information available for a protein."""
        p_entry_nr = resolve_protein_from_id_or_raise(entry_id)
        data = utils.db.get_gene_ontology_annotations(int(p_entry_nr))
        annotations = [models.GeneOntologyAnnotation(utils.db, m) for m in data]
        annotations = sorted(annotations, key=lambda x: [x.aspect, -x.ic])
        serializer = serializers.GeneOntologySerializer(instance=annotations, many=True)
        return Response(serializer.data)

    @extend_schema(deprecated=True,
                   parameters=[_ENTRY_ID_PARAM],
                   responses=serializers.GeneOntologySerializer(many=True))
    @action(detail=True)
    def ontology(self, request, entry_id: str|int, format=None):
        """Deprecated: use gene_ontology endpoint instead."""
        return self.gene_ontology(request, entry_id, format=format)

    @extend_schema(
        parameters=[_ENTRY_ID_PARAM],
        responses={200: serializers.ProteinDomainsSerializer},
    )
    @action(detail=True)
    def domains(self, request, entry_id=None, format=None):
        """List of the domains present in a protein."""
        entry_nr = resolve_protein_from_id_or_raise(entry_id)
        entry = utils.db.entry_by_entry_nr(entry_nr)
        domains = utils.db.get_domains(entry['EntryNr'])
        response = misc.encode_domains_to_dict(entry, domains, utils.domain_source)
        return Response(response)

    @extend_schema(
        parameters=[_ENTRY_ID_PARAM],
        responses=serializers.IsoformProteinSerializer(many=True),
    )
    @action(detail=True)
    def isoforms(self, request, entry_id=None, format=None):
        """List of isoforms for a protein.

        The result contains a list of proteins with information on their locus
        and exon structure for all isoforms recorded in OMA belonging to the
        gene of the query protein.
        """
        entry_nr = resolve_protein_from_id_or_raise(entry_id)
        proteins = [models.ProteinEntry(utils.db, e)
                    for e in utils.db.get_splicing_variants(entry_nr)]
        serializer = serializers.IsoformProteinSerializer(
            instance=proteins, many=True, context={'request': request})
        return Response(serializer.data)

    @extend_schema(
        parameters=[
            _ENTRY_ID_PARAM,
            OpenApiParameter(
                'filter',
                location=OpenApiParameter.QUERY,
                type=str,
                required=False,
                enum=['all', 'exact', 'maindb'],
                default='all',
                description=(
                    'Filter cross-references by type:\n\n'
                    '- **all** *(default)*: no filter, return all cross-references\n'
                    '- **exact**: only entries with an identical sequence\n'
                    '- **maindb**: restrict to major databases only '
                    '(GeneName, UniProtKB, Ensembl, RefSeq, EntrezGene, SourceID)'
                ),
            ),
        ],
        responses=serializers.XRefSerializer(many=True),
    )
    @action(detail=True)
    def xref(self, request, entry_id=None, format=None):
        """List of cross-references for a protein."""
        entry_nr = resolve_protein_from_id_or_raise(entry_id)
        filter_name = self.request.query_params.get('filter', 'all').lower()
        if filter_name == 'all':
            mapper = utils.id_mapper['XRef']
        elif filter_name == 'maindb':
            mapper = utils.id_mapper['GeneNameAndMainDbIdMapper']
        elif filter_name == 'exact':
            mapper = utils.id_mapper['XRefNoApproximateIdMapper']
        else:
            raise ParseError(f'invalid argument for parameter filter: {filter_name}')
        xrefs = mapper.map_entry_nr(entry_nr)
        for ref in xrefs:
            ref['entry_nr'] = entry_nr
            ref['omaid'] = utils.id_mapper['OMA'].map_entry_nr(entry_nr)
        serializer = serializers.XRefSerializer(instance=xrefs, many=True)
        return Response(serializer.data)



class OmaGroupViewSet(PaginationMixin, ViewSet):
    lookup_field = 'group_id'

    @extend_schema(responses=serializers.GroupListSerializer(many=True))
    def list(self, request, format=None):
        """List of all the OMA Groups in the current release."""
        nr_groups = utils.db.get_nr_oma_groups()
        data = [rest_models.OMAGroup(GroupNr=i) for i in range(1, nr_groups + 1)]
        page = self.paginator.paginate_queryset(data, request)
        serializer = serializers.GroupListSerializer(page, many=True, context={'request': request})
        return self.paginator.get_paginated_response(serializer.data)

    @extend_schema(parameters=[_OMA_GROUP_PARAM], responses=serializers.OmaGroupSerializer)
    def retrieve(self, request, group_id=None, format=None):
        """Retrieve the information available for a given OMA group."""
        try:
            # get members in case it is a group id or fingerprint
            memb = utils.db.oma_group_members(group_id)
        except db.AmbiguousID:
            raise NotFound("{} is not a unique id".format(group_id))
        except db.InvalidId as ex:
            try:
                # let's try if group_id is a member protein id
                entry_nr = utils.id_resolver.resolve(group_id)
                prot = models.ProteinEntry.from_entry_nr(utils.db, entry_nr)
                if prot.oma_group == 0:
                    return Response({})
                return self.retrieve(request, prot.oma_group)
            except db.InvalidId:
                raise NotFound(str(ex))

        if len(memb) == 0:
            group = []
        else:
            members = [models.ProteinEntry(utils.db, m) for m in memb]
            data = utils.db.oma_group_metadata(members[0].oma_group)
            fingerprint = data['fingerprint']
            kw = data['keywords']
            group = rest_models.OMAGroup(GroupNr=data['group_nr'], members=members,
                                         fingerprint=fingerprint, description=kw)

        serializer = serializers.OmaGroupSerializer(
            instance=group, context={'request': request})
        return Response(serializer.data)

    @extend_schema(parameters=[_OMA_GROUP_PARAM], responses=serializers.RelatedGroupsSerializer(many=True))
    @action(detail=True)
    def close_groups(self, request, group_id=None, format=None):
        """Retrieve the sorted list of closely related groups for a given OMA group."""
        try:
            # get members in case its a group id or fingerprint
            group_member = utils.db.oma_group_members(group_id)
        except db.InvalidId:
            try:
                # let's try if group_id is a member protein id
                entry_nr = utils.id_resolver.resolve(group_id)
                prot = models.ProteinEntry.from_entry_nr(utils.db, entry_nr)
                if prot.oma_group == 0:
                    return Response([])
                return self.close_groups(request, prot.oma_group)
            except db.InvalidId:
                raise NotFound(group_id)

        members = [models.ProteinEntry(utils.db, e) for e in group_member]
        if len(members) == 0:
            return Response([])
        group_nr = members[0].oma_group

        # count the groups' hits and return in form of a list instead of a dictionary
        group_cnts = Counter()
        for group_member in members:
            # get all the verified pairs
            vpairs = utils.db.get_vpairs(group_member.entry_nr)
            # vpairs into instances of the ProteinEntry model
            for row in vpairs:
                entry_nr = row[1]
                ortholog = models.ProteinEntry.from_entry_nr(utils.db, int(entry_nr))
                if ortholog.oma_group != 0 and ortholog.oma_group != group_nr:
                    group_cnts[ortholog.oma_group] += 1

        close_groups = []
        for grp, hits in group_cnts.most_common():
            close_groups.append(rest_models.OMAGroup(GroupNr=grp, hits=hits))
        page = self.paginator.paginate_queryset(close_groups, request)
        serializer = serializers.RelatedGroupsSerializer(
            instance=page, many=True, context={'request': request})
        return self.paginator.get_paginated_response(serializer.data)


class HOGViewSet(PaginationMixin, ViewSet):
    lookup_field = 'hog_id'
    lookup_value_regex = r'[^/]+'
    serializer_class = serializers.HOGsListSerializer

    def _hog_id_from_entry(self, entry_id):
        entry_nr = resolve_protein_from_id_or_raise(entry_id)
        protein = utils.ProteinEntry(entry_nr)
        if len(protein.oma_hog) == 0:
            raise NotFound("{} is not part of any HOG.".format(entry_id))
        return protein.oma_hog

    def _validate_hogid(self, hogid):
        try:
            fam = utils.db.parse_hog_id(hogid)
            return fam
        except db.OutdatedHogId as e:
            try:
                cand = utils.hogid_forward_mapper.map_hogid(e.outdated_hog_id)
            except AttributeError:
                cand = {}
            candidates = [{"hog_id": hogid, "jaccard": jaccard} for hogid, jaccard in cand.items()]
            raise rest_models.IdGoneException(e.outdated_hog_id, candidates)
        except ValueError as e:
            raise NotFound(e)

    def _get_level_and_get_roothog_if_root_as_level(self, hog_id):
        level = self.request.query_params.get('level', None)
        if level is not None:
            if level.lower() == "root":
                level = None
                hog_id = utils.db.format_hogid(utils.db.parse_hog_id(hog_id))
            elif not self._check_level_is_valid(level):
                if not self._check_level_less_stringent(level):
                    raise NotFound('Invalid or unknown level parameter for this HOG')
                logger.warning("selected level %s is not fully intended to use for HOG queries. Certain things may break. Please report!", level)
        return level, hog_id

    def _check_level_is_valid(self, level):
        return level.encode('utf-8') in utils.db.tax.all_hog_levels

    def _check_level_less_stringent(self, level):
        return level.encode('utf-8') in utils.db.tax.tax_table["Name"]

    def _identify_lca_hog_id_from_proteins(self, proteins):
        hog_id = os.path.commonprefix([p.oma_hog for p in proteins])
        if hog_id.find('.') >= 0:
            for k in range(len(hog_id) - 1, hog_id.find('.') - 1, -1):
                if not (hog_id[k].isdigit() or hog_id[k] == '.'):
                    break
            hog_id = hog_id[0:k + 1]
        return hog_id

    def _get_best_matching_hog_or_raise(self, hog_id, level):
        if level is None:
            hog = utils.db.get_hog(hog_id)
        else:
            hogs = list(utils.db.iter_hogs_at_level(hog_id=hog_id, level=level))
            if len(hogs) != 1:
                raise NotFound("hog_id / level combination does not identify a unique HOG.")
            hog = hogs[0]
        return hog

    @extend_schema(
        parameters=[
            _LEVEL_PARAM,
            OpenApiParameter(
                'compare_with',
                location=OpenApiParameter.QUERY,
                type=str,
                required=False,
                description=(
                    'Compare the HOGs at the given level with those at this parent level, '
                    'annotating all HOGs with the evolutionary events that occurred between the two points.'
                ),
            )
        ],
        responses=serializers.HOGsCompareListSerializer(many=True))
    def list(self, request, format=None):
        """List of all the HOGs identified by OMA.

        Optionally filter by a specific taxonomic level using the `level` query parameter.
        Use `compare_with` (a parent level) to annotate HOGs with evolutionary events
        that occurred between the two levels.
        """
        level, _ = self._get_level_and_get_roothog_if_root_as_level(utils.db.format_hogid(1))
        if level is not None:
            compare_level = self.request.query_params.get('compare_with', None)
            if compare_level is not None:
                if not self._check_level_is_valid(compare_level):
                    raise ValueError("Invalid level for \"compare_level\" parameter.")
            hogs = utils.db.get_all_hogs_at_level(level, compare_with=compare_level)
            if compare_level is None:
                queryset = [rest_models.HOG(hog_id=h['ID'].decode(),
                                            level=h['Level'].decode(),
                                            completeness_score=h['CompletenessScore'],
                                            nr_genes=h['NrMemberGenes'])
                            for h in hogs]
                serializer_cls = serializers.HOGsListSerializer
            else:
                queryset = [rest_models.HOG(hog_id=h['ID'].decode(),
                                            level=h['Level'].decode(),
                                            completeness_score=h['CompletenessScore'],
                                            event=h['Event'].decode(),
                                            nr_genes=h['NrMemberGenes'])
                            for h in hogs]
                serializer_cls = serializers.HOGsCompareListSerializer
        else:
            # list of all the rootlevel hogs
            nr_hogs = utils.db.get_nr_toplevel_hogs()
            queryset = [rest_models.HOG(hog_id=utils.db.format_hogid(i), level="root") for i in range(1, nr_hogs + 1)]
            serializer_cls = serializers.HOGsListSerializer
        page = self.paginator.paginate_queryset(queryset, request)
        serializer = serializer_cls(page, many=True, context={'request': request})
        return self.paginator.get_paginated_response(serializer.data)

    @extend_schema(operation_id='hog_retrieve', parameters=[_HOG_ID_PARAM,_LEVEL_PARAM], responses=serializers.HOGsLevelDetailSerializer(many=True))
    def retrieve(self, request, hog_id: str|int):
        """Retrieve the detail available for a given HOG.

        Returns the deepest level (root level) as well as the list of all the taxonomic
        levels the HOG spans. Optionally restrict to a specific level with the `level`
        query parameter. The special level "root" returns the root HOG level.

        The result includes parent and child HOGs connected by duplication events,
        and alternative levels (no duplication between them).
        """
        if hog_id[:4] != "HOG:":
            # hog_id == member
            hog_id = self._hog_id_from_entry(hog_id)
        fam_nr = self._validate_hogid(hog_id)
        level, hog_id = self._get_level_and_get_roothog_if_root_as_level(hog_id)
        if level is None:
            hog_lev_iter = utils.db.get_hdf5_handle().get_node("/HogLevel").where('(ID==hog_id)')
            lev2score = {row['Level'].decode(): row['CompletenessScore'] for row in hog_lev_iter}
            if 'LUCA' in lev2score:
                level = 'LUCA'
            else:
                pe = next(utils.db.iter_members_of_hog_id(hog_id))
                lin = pe.genome.lineage
                for level in lin[::-1]:
                    if level in lev2score:
                        break
            result_data = [rest_models.HOG(hog_id=hog_id, level=level, completeness_score=lev2score[level])]
        else:
            subhogs = utils.db.get_subhogs_at_level(fam_nr, level)
            result_data = []
            for hog in subhogs:
                h = hog['ID'].decode()
                if hog_id.startswith(h) or h.startswith(hog_id):
                    result_data.append(rest_models.HOG(hog_id=h, level=level, completeness_score=hog['CompletenessScore']))

        querys = {q.hog_id: i for i, q in enumerate(result_data)}
        parents = [collections.defaultdict(set)] * len(result_data)
        children = [collections.defaultdict(set)] * len(result_data)
        same = [set([])] * len(result_data)
        for row in utils.db.get_hdf5_handle().get_node('/HogLevel').where('Fam == fam_nr'):
            cur_id = row['ID'].decode()
            cur_lev = row['Level'].decode()
            if cur_id in querys:
                if cur_lev != level:
                    same[querys[cur_id]].add(cur_lev)
                continue
            for q, i in querys.items():
                if q.find(cur_id) == 0:
                    parents[i][cur_id].add(cur_lev)
                elif cur_id.find(q) == 0:
                    children[i][cur_id].add(cur_lev)

        for i in range(len(result_data)):
            if len(same[i]) > 0:
                result_data[i].alternative_levels = list(same[i])
            result_data[i].parent_hogs = [rest_models.HOG(hog_id=hog, alternative_levels=list(levs))
                                          for hog, levs in parents[i].items()]
            result_data[i].children_hogs = [rest_models.HOG(hog_id=hog, alternative_levels=list(levs))
                                            for hog, levs in children[i].items()]
        serializer = serializers.HOGsLevelDetailSerializer(result_data, many=True, context={'request': request})
        return Response(serializer.data)

    @extend_schema(parameters=[_HOG_ID_PARAM,_LEVEL_PARAM], responses=serializers.HOGMembersListSerializer)
    @action(detail=True)
    def members(self, request, hog_id=str|int, format=None):
        """Retrieve a list of all the protein members for a given hog_id.

        The hog_id parameter uses an encoding of the inferred duplication events
        along the evolution of the family using the LOFT schema
        (see https://doi.org/10.1186/1471-2105-8-83).

        The hog_id changes only after duplication events and hence the ID remains
        the same for potentially many taxonomic levels. If no level parameter is
        provided, this endpoint returns the deepest level containing this specific ID.

        The special level "root" always returns the members of the root HOG together
        with its deepest level.
        """
        if hog_id[:4] != "HOG:":
            hog_id = self._hog_id_from_entry(hog_id)
        fam_nr = self._validate_hogid(hog_id)
        level, hog_id = self._get_level_and_get_roothog_if_root_as_level(hog_id)
        if level is not None:
            members = [utils.ProteinEntry(entry) for entry in utils.db.hog_members_from_hog_id(hog_id, level)]
            hog_id = self._identify_lca_hog_id_from_proteins(members)
        else:
            condition = '(Fam == fam_nr) & (ID == hog_id)'
            levs = frozenset(
                [hog['Level'].decode() for hog in utils.db.get_hdf5_handle().get_node('/HogLevel').where(condition)])
            members = [utils.ProteinEntry(entry) for entry in utils.db.member_of_hog_id(hog_id)]
            if 'LUCA' in levs:
                level = 'LUCA'
            else:
                lin = members[0].genome.lineage
                for level in lin[::-1]:
                    if level in levs:
                        break

        data = {'hog_id': hog_id, 'level': level,
                'members': members}
        serializer = serializers.HOGMembersListSerializer(instance=data, context={'request': request})
        return Response(serializer.data)

    @extend_schema(
        parameters=[
            _HOG_ID_PARAM,
            OpenApiParameter(
                'max_results',
                location=OpenApiParameter.QUERY,
                type=int,
                required=False,
                description='Number of similar HOGs to return. Must be a positive integer ≤ 50. Default: 10.',
            ),
        ],
        responses=serializers.HOGsSimilarProfileSerializer,
    )
    @action(detail=True)
    def similar_profile_hogs(self, request, hog_id=None, format=None):
        """Returns the HOGs with the most similar phylogenetic profiles.

        Profiles are based on the number of duplications, losses and retained genes
        along the phylogenetic tree, computed at the deepest level only. Sub-HOG IDs
        return the same result as the root HOG.

        Similar profile search is only useful for large HOGs (≥100 species). For
        smaller query HOGs the result will be empty.
        """
        if hog_id[:4] != "HOG:":
            hog_id = self._hog_id_from_entry(hog_id)
        fam_nr = self._validate_hogid(hog_id)
        try:
            nr_profiles = float(self.request.query_params.get('max_results', "10"))
            if not (1 <= nr_profiles <= 50):
                raise ParseError("max_results must be positive value <= 50")
        except ValueError:
            raise ParseError("max_results must be positive value <= 50")

        from django.conf import settings

        def _build_response(file_data):
            species = file_data["species"]
            nr_species = len(species)
            ref_entry = next((p for p in file_data["profile"] if p["id"] == "Reference"), None)
            query_in_species = [species[z] for z in range(nr_species) if ref_entry and ref_entry["profile"][z] > 0]
            sim_hogs = []
            if ref_entry:
                sim_hogs.append(rest_models.HOG(hog_id=hog_id, in_species=query_in_species, jaccard_similarity=1.0))
            for entry in [p for p in file_data["profile"] if p["id"] != "Reference"][:int(nr_profiles)]:
                in_sp = [species[z] for z in range(nr_species) if entry["profile"][z] > 0]
                sim_hogs.append(rest_models.HOG(
                    hog_id=utils.db.format_hogid(int(entry["id"])),
                    in_species=in_sp,
                    jaccard_similarity=entry["jaccard"],
                ))
            sim_hogs.sort(key=lambda h: -(h.jaccard_similarity or 0))
            return rest_models.HOG(hog_id=hog_id, similar_profile_hogs=sim_hogs, in_species=query_in_species)

        def _read_result(j):
            with open(os.path.join(settings.MEDIA_ROOT, j.result.name)) as f:
                return _build_response(_json.load(f))

        # Submit or retrieve the cached job (profiler worker keeps Profiler in memory)
        job = _ProfileJobHelper().get_or_create_job(
            extra_fields={"result_type": "similar_profile"},
            fam_nr=fam_nr,
        )

        if job.state == FileResult.STATE_DONE:
            serializer = serializers.HOGsSimilarProfileSerializer(_read_result(job), context={'request': request})
            return Response(serializer.data)

        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            time.sleep(2)
            job.refresh_from_db()
            if job.state == FileResult.STATE_DONE:
                data = _read_result(job)
                serializer = serializers.HOGsSimilarProfileSerializer(data, context={'request': request})
                return Response(serializer.data)
            if job.state in (FileResult.STATE_ERROR, FileResult.STATE_TIMEOUT):
                return Response({'detail': 'Profile computation failed.'}, status=500)

        return Response({'detail': 'Profile computation timed out.'}, status=503)

    @extend_schema(parameters=[_HOG_ID_PARAM,_LEVEL_PARAM])
    @action(detail=True)
    def gene_ontology(self, request, hog_id: str, format=None):
        """Gene ontology annotations for an ancestral gene (i.e. HOG).

        If a level is provided, the endpoint returns annotations with respect to
        that level. The special level "root" always returns annotations for the
        root HOG at its deepest level.
        """
        if hog_id[:4] != "HOG:":
            hog_id = self._hog_id_from_entry(hog_id)
        fam_nr = self._validate_hogid(hog_id)
        level, hog_id = self._get_level_and_get_roothog_if_root_as_level(hog_id)
        hog = self._get_best_matching_hog_or_raise(hog_id, level)
        data = utils.db.get_ancestral_gene_ontology_annotations(hog['Level'], hog['ID'])
        #TODO: fix with better GOA model that allows for both extend and ancestral annotations
        hack_models = [utils.GeneOntologyAnnotation(x) for x in data]
        hack_models = sorted(hack_models, key=lambda x: (x.aspect, -x.ic))
        serializer = serializers.AncestralGeneOntologySerializer(instance=hack_models, many=True)
        return Response(serializer.data)

_SYNTENY_NODE_SCHEMA = {
    'type': 'object',
    'properties': {
        'id': {'type': 'string', 'description': 'HOG identifier (e.g. HOG:0001234.1a) for ancestral genes, or OMA ID (e.g. HUMAN00007) for extant genes.'},
    },
    'additionalProperties': True,
}

_SYNTENY_GRAPH_SCHEMA = {
    'type': 'object',
    'properties': {
        'nodes': {
            'type': 'array',
            'items': _SYNTENY_NODE_SCHEMA,
        },
        'links': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'source': {'type': 'string', 'description': 'ID of the source node.'},
                    'target': {'type': 'string', 'description': 'ID of the target node.'},
                    'weight': {'type': 'integer', 'description': 'Number of genomes supporting this adjacency.'},
                },
                'required': ['source', 'target', 'weight'],
            },
        },
    },
    'required': ['nodes', 'links'],
}


class SyntenyViewSet(ViewSet):
    lookup_field = 'hog_id'
    lookup_value_regex = r'[^/]+'

    @extend_schema(parameters=[_SYNTENY_LEVEL_PARAM, _SYNTENY_EVIDENCE_PARAM, _SYNTENY_BREAK_CIRCULAR_CONTIGS_PARAM],
                   responses={200: {'type': 'array', 'items': _SYNTENY_GRAPH_SCHEMA}})
    def list(self, request, format=None):
        """List all the ancestral or extant contigs of a genome.

        Each contig is a graph with all the ancestral genes (HOGs) or extant genes
        and their neighbors as edges (order of genes on scaffolds/chromosomes).

        The return value is a list of graph objects with 'nodes' and 'links' attributes::

            {"nodes": [{"id":"HOG:C0594134.1a", ...}, ...],
             "links": [{"weight":15,"source":"HOG:C0594134.1a","target":"HOG:C0594135.3c"}, ...]}

        For extant genes, IDs are OMA IDs (e.g. HUMAN00007).
        """
        level = self.request.query_params.get('level', None)
        if level is None:
            raise ParseError("level parameter is required")
        evidence = self.request.query_params.get('evidence', "linearized")
        break_circular_contigs = strtobool(self.request.query_params.get('break_circular_contigs', 'True'))
        try:
            extant_genome = utils.db.id_mapper['OMA'].identify_genome(level)
            graph = utils.db.get_extant_synteny_graph(extant_genome['UniProtSpeciesCode'].decode())
        except db.UnknownSpecies:
            try:
                graph = utils.db.get_syntenic_hogs(level=level, evidence=evidence)
            except db.DBConsistencyError:
                raise NotFound(f"Ancestral Synteny for {level} does not exist")
            except ValueError as e:
                raise ValidationError(e)

        contigs = []
        for cc in sorted(nx.connected_components(graph), key=len, reverse=True):
            contig = graph.subgraph(cc)
            if evidence == "linearized" and break_circular_contigs and len(contig) <= len(contig.edges):
                min_edge = sorted(contig.edges.data(), key=lambda e: e[2]['weight'])[0][:2]
                cont = contig.copy()
                cont.remove_edge(*min_edge)
                contig = cont
            g = nx.node_link_data(contig, edges="links")
            for k in ('directed', 'multigraph', 'graph'):
                g.pop(k, None)
            contigs.append(g)
        return Response(contigs)

    @extend_schema(
        parameters=[
            _HOG_ID_PARAM,
            _SYNTENY_LEVEL_PARAM,
            _SYNTENY_EVIDENCE_PARAM,
            _SYNTENY_BREAK_CIRCULAR_CONTIGS_PARAM,
            OpenApiParameter(
                'context',
                location=OpenApiParameter.QUERY,
                type=int,
                required=False,
                description='Size of the graph around the query HOG (max edge distance). Default: 2.',
            )
        ],
        responses={200: _SYNTENY_GRAPH_SCHEMA})
    def retrieve(self, request, hog_id):
        """Returns the ancestral synteny graph around a reference HOG at a given taxonomic level."""
        level = self.request.query_params.get('level', None)
        evidence = self.request.query_params.get('evidence', "any")
        size = int(self.request.query_params.get('context', 2))
        break_circular_contigs = strtobool(self.request.query_params.get('break_circular_contigs', 'True'))

        graph = None
        if not hog_id.startswith('HOG:') and level is None:
            try:
                enr = utils.db.id_resolver.resolve(hog_id)
                genome = utils.db.id_mapper['OMA'].genome_of_entry_nr(enr)
                graph = utils.db.get_extant_synteny_graph(genome['UniProtSpeciesCode'].decode(), center_entry=enr, window=size)
            except db.InvalidId:
                raise NotFound(f"Not a valid extant protein: {hog_id}")
        elif level is not None:
            try:
                extant_genome = utils.db.id_mapper['OMA'].identify_genome(level)
                graph = utils.db.get_extant_synteny_graph(extant_genome['UniProtSpeciesCode'].decode(), center_entry=hog_id, window=size)
            except db.UnknownSpecies:
                pass
            except db.InvalidId:
                raise NotFound(f"Not a valid extant protein {hog_id} for {level}.")
        # if graph is assigned, we're dealing with an extant species, otherwise, lets check
        # the ancestral levels
        if graph is None:
            try:
                hog = utils.db.get_hog(hog_id=hog_id, level=level)
            except ValueError:
                raise NotFound(f"Invalid hog_id {hog_id}")
            try:
                graph = utils.db.get_syntenic_hogs(hog_id=hog['ID'], level=hog['Level'].decode(), evidence=evidence, steps=size)
            except db.DBConsistencyError:
                raise NotFound(f"Ancestral Synteny for {hog['Level']} around {hog_id} not found.")
            except ValueError as e:
                raise ValidationError(e)

        if evidence == "linearized" and break_circular_contigs and len(graph) <= len(graph.edges):
            min_edge = sorted(graph.edges.data(), key=lambda e: e[2]['weight'])[0][:2]
            cont = graph.copy()
            cont.remove_edge(*min_edge)
            graph = cont

        graph_as_dict = nx.node_link_data(graph, edges="links")
        for k in ('directed', 'multigraph', 'graph'):
            graph_as_dict.pop(k, None)
        return Response(graph_as_dict)


class APIVersion(ViewSet):
    @extend_schema(responses={200: {'type': 'object', 'properties': {
        'oma_version': {'type': 'string'}, 'api_version': {'type': 'string'}}}})
    def list(self, request, format=None):
        """Returns the version information of the api and
        the underlying oma browser database release."""
        return Response({'oma_version': utils.db.get_release_name(),
                         'api_version': api_settings.DEFAULT_VERSION})


class XRefsViewSet(ViewSet):
    serializer_class = serializers.XRefSerializer
    lookup_field = 'entry_id'

    def _order_xrefs(self, xrefs, key='entry_nr'):
        if isinstance(key, str):
            return sorted(xrefs, key=operator.itemgetter(key))
        else:
            return sorted(xrefs, key=operator.itemgetter(*key))

    def _remove_redundant_xrefs(self, xrefs):
        xrefs = self._order_xrefs(xrefs, ('xref', 'entry_nr', 'source'))
        res = []
        for k, grp in itertools.groupby(xrefs, key=operator.itemgetter('xref', 'entry_nr')):
            res.append(next(grp))
        return res

    @extend_schema(
        parameters=[
            OpenApiParameter(
                'search',
                location=OpenApiParameter.QUERY,
                type=str,
                required=False,
                description='Pattern to search for. Must be at least 3 characters long.',
            ),
        ]
    )
    def list(self, request, format=None):
        """List all the cross-references that match a certain pattern.

        The search pattern must be at least 3 characters long to return any results.
        """
        pattern = request.query_params.get('search', None)
        res = []
        if pattern is not None and len(pattern) >= 3:
            make_genome = functools.partial(models.Genome, utils.db)
            enr_to_genome = utils.id_mapper['OMA'].genome_of_entry_nr
            xref_mapper = utils.id_mapper['XRef']
            try:
                for ref in xref_mapper.search_xref(pattern, match_any_substring=True):
                    res.append({'entry_nr': ref['EntryNr'],
                                'omaid': utils.id_mapper['OMA'].map_entry_nr(ref['EntryNr']),
                                'source': xref_mapper.source_as_string(ref['XRefSource']),
                                'seq_match': xref_mapper.verification_as_string(ref['Verification']),
                                'xref': ref['XRefId'].decode(),
                                'genome': make_genome(enr_to_genome(ref['EntryNr']))})
                res = self._remove_redundant_xrefs(res)
            except pyoma.browser.exceptions.TooUnspecificQuery as e:
                raise ValidationError(detail="Query too unspecific. Matches >{} elements".format(e.hits))
        serializer = serializers.XRefSerializer(instance=res, many=True, context={'request': request})
        return Response(serializer.data)


class GenomeViewSet(PaginationMixin, ViewSet):
    lookup_field = 'genome_id'
    serializer_class = serializers.GenomeInfoSerializer

    def list(self, request, format=None):
        """List of all the genomes present in the current release."""
        make_genome = functools.partial(models.Genome, utils.db)
        genomes = [make_genome(g) for g in utils.id_mapper['OMA'].genome_table]
        page = self.paginator.paginate_queryset(genomes, request)
        serializer = serializers.GenomeInfoSerializer(instance=page, many=True, context={'request': request})
        return self.paginator.get_paginated_response(serializer.data)

    @extend_schema(parameters=[_GENOME_ID_PARAM], responses=serializers.GenomeDetailSerializer)
    def retrieve(self, request, genome_id: str|int, format=None):
        """Retrieve the information available for a given genome."""
        try:
            g = models.Genome(utils.db, utils.id_mapper['OMA'].identify_genome(genome_id))
        except db.UnknownSpecies as e:
            raise NotFound(e)
        serializer = serializers.GenomeDetailSerializer(instance=g, context={'request': request})
        return Response(serializer.data)

    @extend_schema(parameters=[_GENOME_ID_PARAM], responses=serializers.ProteinEntrySerializer(many=True))
    @action(detail=True)
    def proteins(self, request, genome_id: str|int):
        """Retrieve the list of all the protein entries available for a genome."""
        try:
            g = models.Genome(utils.db, utils.id_mapper['OMA'].identify_genome(genome_id))
            entries = utils.db.all_proteins_of_genome(g.uniprot_species_code)
            prots = [models.ProteinEntry(utils.db, e) for e in entries]
        except db.UnknownSpecies as e:
            raise NotFound(e)
        page = self.paginator.paginate_queryset(prots, request)
        serializer = serializers.ProteinEntrySerializer(page, many=True, context={'request': request})
        return self.paginator.get_paginated_response(serializer.data)

    @extend_schema(parameters=[_GENOME_ID_PARAM], responses=serializers.ProteinEntrySerializer(many=True))
    @action(detail=True)
    def genes(self, request, genome_id=None):
        """Retrieve the list of all the genes available for a genome.

        This corresponds to the list of main isoforms for genomes with multiple
        isoforms, or all proteins for the others.
        """
        try:
            g = models.Genome(utils.db, utils.id_mapper['OMA'].identify_genome(genome_id))
            entries = utils.db.main_isoforms(g.uniprot_species_code)
            prots = [models.ProteinEntry(utils.db, e) for e in entries]
        except db.UnknownSpecies as e:
            raise NotFound(e)
        page = self.paginator.paginate_queryset(prots, request)
        serializer = serializers.ProteinEntrySerializer(page, many=True, context={'request': request})
        return self.paginator.get_paginated_response(serializer.data)


class PairwiseRelationAPIView(PaginationMixin, APIView):
    renderer_classes = tuple(api_settings.DEFAULT_RENDERER_CLASSES) + (CSVRenderer, TSVRenderer)

    def _get_entry_range(self, genome, chr):
        if chr is None:
            return genome.entry_nr_offset + 1, genome.entry_nr_offset + len(genome)
        else:
            try:
                low = genome.chromosomes[chr][0]
                high = genome.chromosomes[chr][-1]
                return low, high
            except IndexError:
                # this means the chr does not exist
                return 0, 0

    def finalize_response(self, request, response, *args, **kwargs):
        super().finalize_response(request, response, *args, **kwargs)
        file_renderers = ('csv', 'tsv')
        """renderers that return files and should be an attachment with a filename"""

        # this renderer should download a file
        if response.accepted_renderer.format in file_renderers:
            filename = 'OMA-Pairs'
            filename += "_" + kwargs['genome_id1'] + "-" + kwargs['genome_id2']
            # add a timestamp
            filename += '_' + datetime.now().strftime('%Y-%m-%d_%H%M%S')
            # file extension
            filename += '.' + response.accepted_renderer.format
            # add the header
            response['content-disposition'] = 'attachment; filename=' + filename

        return response

    def get_renderer_context(self):
        context = super().get_renderer_context()
        xrefs, _ = self._get_requested_xrefs_and_mapper()
        context['header'] = (('entry_1.omaid',) + tuple(f"entry_1.xrefs.{x}" for x in xrefs) +
                             ('entry_2.omaid',) + tuple(f"entry_2.xrefs.{x}" for x in xrefs) +
                             ('rel_type', 'oma_group'))
        labels = (('OMAid_1',) + tuple(f"{x}_1" for x in xrefs) +
                  ('OMAid_2', ) + tuple(f"{x}_2" for x in xrefs) +
                  ("RelType", "OmaGroup"))
        context['labels'] = {h: l for h, l in zip(context['header'], labels)}
        return context

    def _get_requested_xrefs_and_mapper(self):
        xref_mapper = None
        crossref = self.request.query_params.getlist('xrefs')
        if len(crossref) == 1:
            crossref = list(map(str.strip, crossref[0].split(',')))
        if len(crossref) > 0:
            xref_mapper = NoSearchXrefIdMapper(utils.db, sources=crossref)
            crossref = [xref_mapper.xrefEnum(z) for z in xref_mapper.idtype]
        return crossref, xref_mapper

    @extend_schema(
        parameters=[
            OpenApiParameter(
                'genome_id1',
                location=OpenApiParameter.PATH,
                type=str,
                description='A unique identifier for the first genome: NCBI taxon ID or UniProt species code.',
            ),
            OpenApiParameter(
                'genome_id2',
                location=OpenApiParameter.PATH,
                type=str,
                description='A unique identifier for the second genome: NCBI taxon ID or UniProt species code.',
            ),
            OpenApiParameter(
                'chr1',
                location=OpenApiParameter.QUERY,
                type=str,
                required=False,
                description='Chromosome ID in the first genome to restrict the relation list.',
            ),
            OpenApiParameter(
                'chr2',
                location=OpenApiParameter.QUERY,
                type=str,
                required=False,
                description='Chromosome ID in the second genome to restrict the relation list.',
            ),
            OpenApiParameter(
                'type',
                location=OpenApiParameter.QUERY,
                type=str,
                enum=["vps", "hogs"],
                default="hogs",
                required=False,
                description='Type of ortholog pairs to use: "vps" or "hogs" (default).',
            ),
            OpenApiParameter(
                'xrefs',
                location=OpenApiParameter.QUERY,
                type={'type': 'array', 'items': {
                    'type': 'string',
                    'enum': [
                        'UniProtKB/SwissProt',
                        'UniProtKB/TrEMBL',
                        'EntrezGene',
                        'SourceID',
                        'SourceAC',
                        'Ensembl Gene',
                        'RefSeq',
                    ],
                }},
                explode=True,  # ?xrefs=UniProtKB/SwissProt&xrefs=EntrezGene
                required=False,
                description=(
                        'One or more cross-reference sources to include. '
                        'Repeat the parameter for multiple values: '
                        '`?xrefs=UniProtKB/SwissProt&xrefs=EntrezGene`. '
                        'Default: no cross-references, only OMA IDs.'
                ),
            ),
            OpenApiParameter(
                'rel_type',
                location=OpenApiParameter.QUERY,
                type=str,
                enum=["1:1", "1:n", "m:1", "m:n"],
                required=False,
                description='Limit relations to a specific type, e.g. "1:1".',
            ),
        ],
        responses=serializers.PairwiseRelationSerializer(many=True),
    )
    def get(self, request, genome_id1, genome_id2, format=None):
        """List the pairwise relations among two genomes.

        The relations are orthologs when the genomes differ, and close paralogs or
        homoeologs when they are the same. Use query parameters chr1/chr2 to restrict
        to a specific chromosome in either genome.
        """
        rel_type = request.query_params.get('rel_type', None)
        try:
            genome1 = models.Genome(utils.db, utils.db.id_mapper['OMA'].identify_genome(genome_id1))
            genome2 = models.Genome(utils.db, utils.db.id_mapper['OMA'].identify_genome(genome_id2))
        except db.UnknownSpecies as e:
            raise NotFound(e)

        chr1 = request.query_params.get('chr1', None)
        chr2 = request.query_params.get('chr2', None)
        range1 = self._get_entry_range(genome1, chr1)
        range2 = self._get_entry_range(genome2, chr2)
        logger.debug("EntryRanges: ({0[0]},{0[1]}), ({1[0]},{1[1]})".format(range1, range2))

        crossref, xref_mapper = self._get_requested_xrefs_and_mapper()
        if len(crossref) > 0:
            xrefs1 = xref_mapper.xreftab_to_dict(xref_mapper.map_entry_nr_range(range1[0], range1[1] + 1))
            xrefs2 = xref_mapper.xreftab_to_dict(xref_mapper.map_entry_nr_range(range2[0], range2[1] + 1))
        else:
            xrefs1, xrefs2 = {}, {}

        def build_ext_ProteinEntries_dict(entries, allxrefs):
            res = {}
            for entry in entries:
                p = models.ProteinEntry(utils.db, entry)
                setattr(p, 'xrefs', allxrefs.get(p.entry_nr))
                res[p.entry_nr] = p
            return res
        entries1 = build_ext_ProteinEntries_dict(utils.db.main_isoforms(genome1.uniprot_species_code), xrefs1)
        entries2 = build_ext_ProteinEntries_dict(utils.db.main_isoforms(genome2.uniprot_species_code), xrefs2)

        tab_name = 'VPairs' if genome1.uniprot_species_code != genome2.uniprot_species_code else 'within'
        rel_tab = utils.db.get_hdf5_handle().get_node('/PairwiseRelation/{}/{}'.format(
            genome1.uniprot_species_code, tab_name))

        def obj_factory(data):
            rel = models.PairwiseRelation(utils.db, data, entry1=entries1.get(data['EntryNr1']), entry2=entries2.get(data['EntryNr2']))
            if ((chr1 is None or chr1 == rel.entry_1.chromosome) and
                    (chr2 is None or chr2 == rel.entry_2.chromosome)):
                if rel_type is None or rel_type == rel.rel_type:
                    return rel
            return None

        logger.info("negotiated format: %s", request.accepted_renderer.format)

        query = '(EntryNr1 >= {0[0]}) & (EntryNr1 <= {0[1]}) ' \
                '& (EntryNr2 >= {1[0]}) & (EntryNr2 <= {1[1]})'.format(range1, range2)
        queryset = LazyPagedPytablesQuery(rel_tab, query=query, obj_factory=obj_factory)
        page = self.paginator.paginate_queryset(queryset, request)
        serializer = serializers.PairwiseRelationSerializer(instance=page, many=True, context={'request': request})
        return self.paginator.get_paginated_response(serializer.data)


@extend_schema(exclude=True)
class MinimalPairwiseRelation(APIView):

    def get(self, request, genome_id1, genome_id2, format=None):
        """Retrieve minimal version of pairs for a genome pair."""
        try:
            genome1 = models.Genome(utils.db, utils.db.id_mapper['OMA'].identify_genome(genome_id1))
            genome2 = models.Genome(utils.db, utils.db.id_mapper['OMA'].identify_genome(genome_id2))
        except db.UnknownSpecies as e:
            raise NotFound(e)
        tab_name = 'VPairs' if genome1.uniprot_species_code != genome2.uniprot_species_code else 'within'
        range2 = genome2.entry_nr_offset + 1, genome2.entry_nr_offset + len(genome2)
        rel_tab = utils.db.get_hdf5_handle().get_node('/PairwiseRelation/{}/{}'.format(
            genome1.uniprot_species_code, tab_name))
        rels = [[int(row['EntryNr1']), int(row['EntryNr2'])] for row in rel_tab.read_where('(EntryNr2>={0}) & (EntryNr2<={1})'.format(range2[0], range2[1]))]
        return Response({'pairs': rels})


_TAXONOMY_RESPONSES = {
    (200, 'application/json'): OpenApiResponse(
        response=OpenApiTypes.OBJECT,
        description=(
            'Default dictionary representation of the tree, or a JSON wrapper '
            'when combined with `?type=newick` → `{"root_taxon": {...}, "newick": "..."}` '
            'or `?type=phyloxml` → `{"root_taxon": {...}, "phyloxml": "..."}`.'
        ),
    ),
    (200, 'application/x-newick'): OpenApiResponse(
        response=OpenApiTypes.STR,
        description='Newick/NHX format tree as plain text.',
    ),
    (200, 'text/x-nh'): OpenApiResponse(
        response=OpenApiTypes.STR,
        description='Newick format tree as plain text (alias for `application/x-newick`).',
    ),
    (200, 'application/vnd.phyloxml+xml'): OpenApiResponse(
        response=OpenApiTypes.STR,
        description='PhyloXML format tree as plain text.',
    ),
    (200, 'application/xml'): OpenApiResponse(
        response=OpenApiTypes.STR,
        description='PhyloXML format tree as plain text (alias for `application/vnd.phyloxml+xml`).',
    ),
}


@extend_schema_view(
    list=extend_schema(
        operation_id='taxonomy_list',
        parameters=[
            OpenApiParameter(
                'type',
                location=OpenApiParameter.QUERY,
                type=str,
                enum=["dictionary", "newick", "phyloxml"],
                required=False,
                description=(
                    'Override the response format, takes precedence over the `Accept` header.\n\n'
                    '- **dictionary** *(default)*: nested JSON object\n'
                    '- **newick**: JSON wrapper `{"root_taxon": {...}, "newick": "..."}` '
                    '— use this when you need the newick string embedded in a JSON response. '
                    'For a raw newick string, use `Accept: application/x-newick` (or `?format=newick`) instead.\n'
                    '- **phyloxml**: JSON wrapper `{"root_taxon": {...}, "phyloxml": "..."}`. '
                    'For a raw PhyloXML string use `Accept: application/vnd.phyloxml+xml` instead.\n\n'
                    '> **Changed in 1.11:** `?type=phyloxml` previously returned raw PhyloXML text; '
                    'it now returns a JSON wrapper `{"root_taxon": {...}, "phyloxml": "..."}`. '
                    'To retrieve raw PhyloXML, use `Accept: application/vnd.phyloxml+xml`.'
                ),
            ),
            OpenApiParameter(
                'members',
                location=OpenApiParameter.QUERY,
                type=str,
                required=False,
                description=(
                    'Comma-separated list of members to compute an induced taxonomy. '
                    'IDs can be NCBI taxon IDs or UniProt species codes (must be consistent).'
                ),
            ),
            OpenApiParameter(
                'collapse',
                location=OpenApiParameter.QUERY,
                type=bool,
                required=False,
                description='Whether to collapse taxonomic levels with a single child. Default: yes.',
            ),
            OpenApiParameter(
                'newick_leaf_label',
                location=OpenApiParameter.QUERY,
                type=str,
                required=False,
                description='Data to store in newick leaf nodes: "sciname" (default) or "species_code".',
            ),
            OpenApiParameter(
                'newick_internal_label',
                location=OpenApiParameter.QUERY,
                type=str,
                required=False,
                description='Data to store in newick internal nodes: "sciname" (default), "taxid", or "None".',
            ),
            OpenApiParameter(
                'newick_quote_labels',
                location=OpenApiParameter.QUERY,
                type=bool,
                required=False,
                description='Whether to quote labels in the newick tree. Default: no (spaces replaced by "_").',
            ),
        ],
        responses=_TAXONOMY_RESPONSES,
    ),
    retrieve=extend_schema(
        operation_id='taxonomy_retrieve',
        parameters=[
            OpenApiParameter(
                'root_id',
                location=OpenApiParameter.PATH,
                type=str,
                description='Taxon ID, scientific name, or 5-letter UniProt species code for the root level.',
            ),
            OpenApiParameter(
                'type',
                location=OpenApiParameter.QUERY,
                type=str,
                required=False,
                description=(
                    'Override the response format, takes precedence over the `Accept` header.\n\n'
                    '- **dictionary** *(default)*: nested JSON object\n'
                    '- **newick**: JSON wrapper `{"root_taxon": {...}, "newick": "..."}`. '
                    'For a raw newick string use `Accept: application/x-newick` (or `?format=newick`) instead.\n'
                    '- **phyloxml**: JSON wrapper `{"root_taxon": {...}, "phyloxml": "..."}`. '
                    'For a raw PhyloXML string use `Accept: application/vnd.phyloxml+xml` instead.\n\n'
                    '> **Changed in 1.11:** `?type=phyloxml` previously returned raw PhyloXML text; '
                    'it now returns a JSON wrapper `{"root_taxon": {...}, "phyloxml": "..."}`. '
                    'To retrieve raw PhyloXML, use `Accept: application/vnd.phyloxml+xml`.'
                ),
            ),
            OpenApiParameter(
                'collapse',
                location=OpenApiParameter.QUERY,
                type=bool,
                required=False,
                description='Whether to collapse taxonomic levels with a single child. Default: yes.',
            ),
        ],
        responses=_TAXONOMY_RESPONSES,
    ),
)
class TaxonomyViewSet(ViewSet):
    lookup_field = 'root_id'
    renderer_classes = [
        *api_settings.DEFAULT_RENDERER_CLASSES,
        NewickRenderer, NewickTextNhRenderer,
        PhyloXMLRenderer, PhyloXMLLegacyRenderer,
    ]

    # Maps ?type= query param values to canonical internal names.
    # ?format= is handled by DRF's standard content negotiation (renderer.format).
    _TYPE_PARAM_ALIASES = {
        'newick': 'newick', 'nk': 'newick', 'nhx': 'newick',
        'phyloxml': 'phyloxml',
        'dictionary': 'dictionary', 'json': 'dictionary',
    }

    # Maps negotiated Accept media type to canonical internal names.
    _MEDIA_TYPE_TO_FORMAT = {
        'application/x-newick': 'newick',
        'text/x-nh': 'newick',
        'application/vnd.phyloxml+xml': 'phyloxml',
        'application/xml': 'phyloxml',
    }

    def _resolve_format(self, request):
        """Return the canonical format string.

        ``?type=`` takes precedence (backward-compatible explicit selector,
        also supports a JSON wrapper response for newick via
        ``?type=newick`` + ``Accept: application/json``).
        Otherwise falls back to the negotiated media type, then 'dictionary'.
        """
        explicit = request.query_params.get('type')
        if explicit is not None:
            fmt = self._TYPE_PARAM_ALIASES.get(explicit.lower())
            if fmt is None:
                raise ParseError(
                    f"Invalid type='{explicit}'. "
                    f"Choose from: {', '.join(self._TYPE_PARAM_ALIASES)}."
                )
            return fmt
        return self._MEDIA_TYPE_TO_FORMAT.get(request.accepted_media_type, 'dictionary')

    def list(self, request, format=None):
        """Retrieve the taxonomic tree available in the current release.

        By default returns a dictionary representation of the full tree. Use
        `members` to get the induced subtree for a subset of species.

        The API by default returns a nested JSON object representing the
        taxonomy tree. Use the `type` query parameter or even better, the
        `Accept` header, to override this behavior:

        |type (query param) | Accept header | return value |
        |-------------------|---------------|--------------|
        |   [ not set ]       | text/x-nh     | raw newick tree |
        | ?type=newick      | text/x-nh     | raw newick tree |
        |   [ not set ]       | application/x-newick | raw newick tree |
        | ?type=newick      | application/json | `{"root_taxon": {...}, "newick": "..."}` |
        |   [ not set ]     | application/xml  | raw phyloxml tree |
        |   [ not set ]     | application/vnd.phyloxml+xml | raw phyloxml tree |
        | ?type=phyloxml    | application/xml  | raw phyloxml tree |
        | ?type=phyloxml    | application/json | `{"root_taxon": {...}, "phyloxml": "..."}` |
        | ?type=dictionary  | application/json | nested JSON object |
        |  [ not set ]      | application/json | nested JSON object |


        Use the `type` parameter (or an ``Accept`` header) to request newick
        or phyloxml formats. Use `members` to get the induced taxonomy for a
        subset of species.
        """
        # e.g. members = YEAST,ASHGO
        members = request.query_params.getlist('members', None)  # read as a string
        type = self._resolve_format(request)
        collapse = strtobool(request.query_params.get('collapse', 'True'))
        tax_obj = utils.db.tax
        if members is not None and len(members) > 0:
            members = [m.strip() for m in itertools.chain.from_iterable(ml.split(',') for ml in members)]   # as the query param is passed as a string
            members_list = []
            if not members[0].isdigit():
                if all(map(lambda x: len(x) == 5, members)):
                    members = list(map(str.upper, members))
                    for ncbi, genome in tax_obj.genomes.items():
                        if genome.uniprot_species_code in members:
                            members_list.append(ncbi)
                else:
                    for level in tax_obj.tax_table:
                        if level['Name'].decode() in members:
                            members_list.append(int(level['NCBITaxonId']))
            else:
                # handling the case user gave a list of NCBI taxon ids
                try:
                    members_list = [int(z) for z in members]
                except ValueError:
                    raise ParseError("not all passed members are numeric")

            try:
                tx = tax_obj.get_induced_taxonomy(members=members_list, augment_parents=True, collapse=collapse)
            except db.InvalidTaxonId as e:
                raise ParseError(str(e))
        else:
            tx = tax_obj

        root = tx._get_root_taxon()
        root_data = {'name': root['Name'].decode(), 'taxon_id': int(root['NCBITaxonId'])}
        if type == 'newick':
            leaf = request.query_params.get('newick_leaf_label', "sciname").lower()
            internal = request.query_params.get('newick_internal_label', "sciname").lower()
            if internal == "none":
                internal = None
            quoted_internal = strtobool(request.query_params.get('newick_quote_labels', "no"))
            try:
                data = {'root_taxon': root_data,
                        'newick': tx.newick(quoted=quoted_internal, leaf=leaf, internal=internal),
                       }
            except ValueError as e:
                raise ParseError(str(e))
            serializer = serializers.TaxonomyNewickSerializer(instance=data)
            return Response(serializer.data)
        elif type == "phyloxml":
            if request.version and _Version(request.version) < _Version('1.11'):
                return HttpResponse(tx.as_phyloxml(), content_type='application/vnd.phyloxml+xml')
            data = {"root_taxon": root_data, "phyloxml": tx.as_phyloxml().decode()}
            serializer = serializers.TaxonomyPhyloXMLSerializer(instance=data)
            return Response(serializer.data)
        else:
            data = tx.as_dict()
            return Response(data)

    def retrieve(self, request, root_id, format=None):
        """Retrieve the subtree rooted at the taxonomic level indicated."""
        type = self._resolve_format(request)

        try:
            taxon_id = int(root_id)
        except ValueError:
            if len(root_id) == 5:
                try:
                    g = utils.db.id_mapper['OMA'].genome_from_UniProtCode(root_id.upper())
                    return self.retrieve(request, g['NCBITaxonId'], format=format)
                except db.UnknownSpecies:
                    pass
            elif root_id.upper() == 'LUCA':
                return self.list(request, format=format)

            taxonomy_tab = utils.db.get_hdf5_handle().root.Taxonomy
            taxon_id = taxonomy_tab.read_where('Name==root_id', field='NCBITaxonId')
            if len(taxon_id) != 1:
                raise NotFound("root level '{}' not found".format(root_id))
            return self.retrieve(request, int(taxon_id), format=format)

        def get_children(id):
            children = utils.db.tax._direct_children_taxa(id)
            if len(children) > 0:
                for child in children:
                    child_id = child['NCBITaxonId']
                    subtree.append(child_id)
                    get_children(child_id)
            return subtree

        subtree = [taxon_id]
        branch = get_children(taxon_id)

        collapse = strtobool(request.query_params.get('collapse', 'True').lower())
        induced_tax = utils.db.tax.get_induced_taxonomy(members=branch, collapse=collapse)

        if type == 'newick':
            root_taxon = induced_tax._taxon_from_numeric(taxon_id)
            root_data = {'name': root_taxon['Name'].decode(), 'taxon_id': int(root_taxon['NCBITaxonId'])}
            data = {'root_taxon': root_data, 'newick': induced_tax.newick()}
            serializer = serializers.TaxonomyNewickSerializer(instance=data)
            return Response(serializer.data)
        elif type == 'phyloxml':
            root_taxon = induced_tax._taxon_from_numeric(taxon_id)
            root_data = {'name': root_taxon['Name'].decode(), 'taxon_id': int(root_taxon['NCBITaxonId'])}
            if request.version and _Version(request.version) < _Version('1.11'):
                return HttpResponse(induced_tax.as_phyloxml(), content_type='application/vnd.phyloxml+xml')
            data = {'root_taxon': root_data, 'phyloxml': induced_tax.as_phyloxml().decode()}
            serializer = serializers.TaxonomyPhyloXMLSerializer(instance=data)
            return Response(serializer.data)
        else:
            data = induced_tax.as_dict()
            return Response(data)


class IdentifiySequenceAPIView(APIView):

    @extend_schema(
        parameters=[
            OpenApiParameter(
                'query',
                location=OpenApiParameter.QUERY,
                type=str,
                required=True,
                description='The amino acid sequence to search for.',
            ),
            OpenApiParameter(
                'search',
                location=OpenApiParameter.QUERY,
                type=str,
                enum=["exact", "approxmimate", "mixed"],
                default="mixed",
                required=False,
                description=(
                    'Search strategy which is applied: \n\n'
                    '- **exact**: the query sequence must match exactly the sequence in the database.\n'
                    '- **approximate**: the query sequence must match at least partially the sequence in the database. This requires more time to complete.\n'
                    '- **mixed** (*default*): first tries exact matching; falls back to approximate if no exact match is found.\n'
                ),
            ),
            OpenApiParameter(
                'full_length',
                location=OpenApiParameter.QUERY,
                type=bool,
                required=False,
                default=False,
                description=(
                    'For exact matches, whether the query must match the full target sequence. '
                    'Default: false (partial matches are also reported).'
                ),
            ),
        ],
        responses=serializers.SequenceSearchResultSerializer,
    )
    def get(self, request, format=None):
        """Identify a protein by its amino acid sequence."""
        query_seq = request.query_params.get('query', '')
        strategy = request.query_params.get('search', 'mixed').lower()
        if strategy not in ('approximate', 'exact', 'mixed'):
            raise ParseError("search parameter invalid. Must be one of 'approximate', 'exact', 'mixed'.")
        only_full_length = strtobool(request.query_params.get('full_length', 'False'))
        map_result = self.identify_sequence(query_seq, strategy=strategy, only_full_length=only_full_length)
        serializer = serializers.SequenceSearchResultSerializer(instance=map_result, context={'request': request})
        return Response(serializer.data)

    def identify_sequence(self, seq, strategy, only_full_length):
        seq_searcher = utils.db.seq_search
        seq = seq_searcher._sanitise_seq(seq)
        if len(seq) < 5:
            raise ParseError('too shot query sequence')
        res = {'query': seq.decode()}

        if strategy in ('exact', 'mixed'):
            exact_matches = seq_searcher.exact_search(seq,
                                                      only_full_length=only_full_length,
                                                      is_sanitised=True)
            res.update(
                {'targets': [models.ProteinEntry.from_entry_nr(utils.db, enr) for enr in exact_matches],
                 'identified_by': 'exact match'}
            )

        if strategy == 'approximate' or (strategy == 'mixed' and len(exact_matches) == 0):
            approx = seq_searcher.approx_search(seq, is_sanitised=True)
            targets = []
            for enr, align_results in approx:
                if align_results['score'] < 70:
                    break
                protein = models.ProteinEntry.from_entry_nr(utils.db, enr)
                protein.alignment_score = align_results['score']
                protein.alignment = [x[0] for x in align_results['alignment']]
                targets.append(protein)
            res.update({'targets': targets, 'identified_by': 'approximate match'})
        return res


class PropagateFunctionAPIView(APIView):

    @extend_schema(
        parameters=[
            OpenApiParameter(
                'query',
                location=OpenApiParameter.QUERY,
                type=str,
                required=True,
                description='The amino acid sequence to annotate (minimum 10 amino acids).',
            ),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, format=None):
        """Annotate a sequence with GO functions based on all annotations in OMA.

        The sequence is expected to be a simple string of amino acids passed as a
        query parameter. GO annotations are projected from OMA's orthologs.
        """
        query_seq = request.query_params.get('query', '')
        query_seq = utils.db.seq_search._sanitise_seq(query_seq)
        if len(query_seq) < 10:
            raise ParseError('The query sequence must be at least 10 amino acids long.')

        if IUPAC is not None:
            seq = Seq(query_seq.decode(), IUPAC.protein)
        else:
            seq = Seq(query_seq.decode())
        seq_list = [SeqRecord(seq, id='unknown', annotations={"molecule_type": "protein"})]
        projector = db.FastMapper(utils.db)
        annotations = []
        for anno in projector.iter_projected_goannotations(seq_list):
            for key in ("DB_Object_Symbol", "DB_Object_ID", "Taxon_ID", "Gene_Product_Form_ID", "Annotation_Extension"):
                anno.pop(key)
            anno['GO_name'] = utils.db.gene_ontology.term_by_id(anno['GO_ID']).name
            annotations.append(anno)
        return Response(annotations)


class SharedAncestrySummaryAPIView(APIView):

    @extend_schema(
        parameters=[
            OpenApiParameter(
                'genome_id1',
                location=OpenApiParameter.PATH,
                type=str,
                description='A unique identifier for the first genome: NCBI taxon ID or UniProt species code.',
            ),
            OpenApiParameter(
                'genome_id2',
                location=OpenApiParameter.PATH,
                type=str,
                description='A unique identifier for the second genome: NCBI taxon ID or UniProt species code.',
            ),
            OpenApiParameter(
                'type',
                location=OpenApiParameter.QUERY,
                type=str,
                required=False,
                description='Type of orthology information to use: "hogs" (default) or "vps".',
            ),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, genome_id1, genome_id2, format=None):
        """Returns the fraction of shared ancestry between two species of interest."""
        try:
            genome1 = models.Genome(utils.db, utils.db.id_mapper['OMA'].identify_genome(genome_id1))
            genome2 = models.Genome(utils.db, utils.db.id_mapper['OMA'].identify_genome(genome_id2))
        except db.UnknownSpecies as e:
            raise NotFound(e)
        orthology_type = request.query_params.get('type', 'hogs').lower()
        root = None
        if orthology_type == 'vps':
            nr_genes_with_orthologs = self._by_vps(genome1, genome2)
        elif orthology_type == 'hogs':
            nr_genes_with_orthologs, root = self._by_hogs(genome1, genome2)
        else:
            raise ParseError("type parameter invalid. Must be one of 'hogs' or 'vps'.")
        details = [{'species': g.uniprot_species_code,
                    'nr_genes': g.nr_genes,
                    'nr_orthologs': nr_genes_w_orthologs}
                   for g, nr_genes_w_orthologs in zip((genome1, genome2), nr_genes_with_orthologs)]
        res = {'fraction': sum(z['nr_orthologs']/z['nr_genes'] for z in details) / len(details),
               'details': details}
        if root is not None:
            res['mrca'] = {'taxon_id': int(root['NCBITaxonId']), 'name': root['Name'].decode()}
        return Response(res)

    def _by_hogs(self, g1, g2):
        subtax = utils.tax.get_induced_taxonomy([g1.ncbi_taxon_id, g2.ncbi_taxon_id], augment_parents=True)
        root = subtax._get_root_taxon()
        level = root['Name']
        hogs = numpy.sort(utils.db.get_all_hogs_at_level(level)['ID'])

        def genes_in_ancestral_hogs(genome):
            genes_allinfo = utils.db.main_isoforms(genome.uniprot_species_code)
            genes = genes_allinfo['OmaHOG']
            idx = hogs.searchsorted(genes, side='right')
            existed = numpy.fromiter(map(lambda i, gene: gene.startswith(hogs[i-1]), idx, genes),
                                     dtype=bool)
            return genes_allinfo[existed]

        return (len(genes_in_ancestral_hogs(g1)), len(genes_in_ancestral_hogs(g2))), root

    def _by_vps(self, g1, g2):
        vp_tab = utils.db.get_hdf5_handle().get_node('/PairwiseRelation/{}/VPairs'.format(g1.uniprot_species_code))
        range1 = g1.entry_nr_offset + 1, g1.entry_nr_offset + len(g1)
        range2 = g2.entry_nr_offset + 1, g2.entry_nr_offset + len(g2)
        query = '(EntryNr1 >= {0[0]}) & (EntryNr1 <= {0[1]}) ' \
                '& (EntryNr2 >= {1[0]}) & (EntryNr2 <= {1[1]})'.format(range1, range2)
        genes1, genes2 = set([]), set([])
        for pw in vp_tab.where(query):
            genes1.add(pw['EntryNr1'])
            genes2.add(pw['EntryNr2'])
        return len(genes1), len(genes2)

class CreateAsyncJobAPIView(CreateAPIView):
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED, headers=headers)

    def get_success_headers(self, data):
        try:
            return {'Location': str(data['status_url'])}
        except (TypeError, KeyError):
            return {}


@method_decorator(never_cache, name='dispatch')
class StatusAsyncJobAPIView(RetrieveAPIView):
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        header = {}
        if instance.state == "DONE":
            stat = status.HTTP_200_OK
        elif instance.state == "ERROR":
            stat = status.HTTP_400_BAD_REQUEST
        elif instance.state in ("PENDING", "RUNNING"):
            stat = status.HTTP_200_OK
            header = {"Retry-After": str(20)}
        return Response(serializer.data, status=stat, headers=header)

class CreateEnrichmentAnalysisView(CreateAsyncJobAPIView):
    """Submit a Gene Ontology enrichment analysis.

    This endpoint accepts requests to perform gene ontology enrichment analysis
    on extant and ancestral gene sets. Jobs are executed asynchronously; the
    response includes a 202 status with a Location header pointing to a URL
    where the job status can be checked.

    The request body must be JSON with a `foreground` set of extant genes (all
    from the same species) for an extant genome enrichment analysis, or a set
    of HOGs that exist at a given ancestral taxonomy level. Indicate the type
    of analysis with the `type` parameter ("ancestral" or "extant"). An
    optional `name` parameter is also accepted.
    """
    serializer_class = serializers.EnrichmentAnalysisInputSerializer

    def perform_create(self, serializer):
        obj = serializer.save(state="PENDING")
        go_enrichment.delay(obj.id)
        return obj



class StatusEnrichmentAnalysisView(StatusAsyncJobAPIView):
    queryset = rest_models.EnrichmentAnalysisModel.objects.all()
    lookup_field = 'id'
    serializer_class = serializers.EnrichmentAnalysisStatusSerializer
