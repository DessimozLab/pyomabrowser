import functools
import operator
import itertools
import os

import networkx as nx
import numpy
import pyoma.browser.exceptions
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
from rest_framework import status

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
from django.http import HttpResponse
from distutils.util import strtobool

from . import models as rest_models
from . import serializers
from .schema import DocStringSchemaExtractor
from .pagination import PaginationMixin, LazyPagedPytablesQuery

from oma import utils, misc
from pyoma.browser import models, db
import logging

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


# Create your views here.
class ProteinEntryViewSet(ViewSet):
    serializer_class = serializers.ProteinEntryDetailSerializer
    lookup_field = 'entry_id'
    schema = DocStringSchemaExtractor()

    @action(detail=False, methods=['post'])
    def bulk_retrieve(self, request, format=None):
        """Retrieve the information available for multiple protein IDs at once.

        The POST request must contain a json-encoded list of IDs of
        up to 1000 IDs for which the information is returned.

        In case the ID is not unique or unknown, an empty element is
        returned for this query element.

        changed in verison 1.7: the endpoint returns now a list with tuples (query_id, target)
        instead of a simple list of proteins in the order of the query ids.

        ---
        parameters:

          - name: ids
            description: A list of ids of proteins to retrieve
            location: body
            required: True

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

    def retrieve(self, request, entry_id=None, format=None):
        """
        Retrieve the information available for a protein entry.
        ---
        parameters:

          - name: entry_id
            description: an unique identifier for a protein - either it
                         entry number, omaid or its canonical id
        """

        # Load the entry and its domains, before forming the JSON to draw client-side.
        entry_nr = resolve_protein_from_id_or_raise(entry_id)
        protein = models.ProteinEntry.from_entry_nr(utils.db, entry_nr)
        serializer = serializers.ProteinEntryDetailSerializer(
            instance=protein, context={'request': request})
        return Response(serializer.data)

    @action(detail=True)
    def orthologs(self, request, entry_id=None, format=None):
        """List of all the identified pairwise orthologues for a protein. Filtering
        specific subtypes of orthology is possible by specifying a rel_type
        query parameter.
        ---
        parameters:

          - name: entry_id
            description: an unique identifier for a protein - either it
                         entry number, omaid or its canonical id

          - name: rel_type
            description: filter for orthologs of a specific relationship type only
            location: query
            type: string
            example: "1:1"
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

    @action(detail=True)
    def hog_derived_orthologs(self, request, entry_id, format=None):
        """List of the orthologs derived from the hog for a given protein.

        ---
        parameters:

          - name: entry_id
            description: an unique identifier for a protein - either it
                         entry number, omaid or its canonical id
        """
        p_entry_nr = resolve_protein_from_id_or_raise(entry_id)
        data = utils.db.get_hog_induced_pairwise_orthologs(p_entry_nr)
        content = [models.ProteinEntry(utils.db, e) for e in data]
        serializer = serializers.ProteinEntrySerializer(instance=content, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True)
    def homoeologs(self, request, entry_id=None, format=None):
        """List of all the homoeologs for a given protein.

        ---
        parameters:

          - name: entry_id
            description: an unique identifier for a protein - either its
                         entry number, omaid or canonical id."""
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

    @action(detail=True)
    def gene_ontology(self, request, entry_id=None, format=None):
        """Gene ontology information available for a protein.
        ---
        parameters:

          - name: entry_id
            description: an unique identifier for a protein - either its
                         entry number, omaid or its canonical id
        """
        p_entry_nr = resolve_protein_from_id_or_raise(entry_id)
        data = utils.db.get_gene_ontology_annotations(int(p_entry_nr))
        annotations = [models.GeneOntologyAnnotation(utils.db, m) for m in data]
        serializer = serializers.GeneOntologySerializer(instance=annotations, many=True)
        return Response(serializer.data)

    @action(detail=True)
    def ontology(self, request, entry_id=None, format=None):
        """Deprecated: use gene_ontology endpoint instead"""
        return self.gene_ontology(request, entry_id, format=format)

    @action(detail=True)
    def domains(self, request, entry_id=None, format=None):
        """List of the domains present in a protein.
        ---
        parameters:
          - name: entry_id
            description: an unique identifier for a protein -
                         either it entry number, omaid or its canonical id
        """
        entry_nr = resolve_protein_from_id_or_raise(entry_id)
        entry = utils.db.entry_by_entry_nr(entry_nr)
        domains = utils.db.get_domains(entry['EntryNr'])
        response = misc.encode_domains_to_dict(entry, domains, utils.domain_source)
        return Response(response)

    @action(detail=True)
    def isoforms(self, request, entry_id=None, format=None):
        """List of isoforms for a protein.

        The result contains a list of proteins with information on
        their locus and and exon structure for all the isoforms
        recored in OMA belonging to the gene of the query protein.

        ---
        parameters:

          - name: entry_id
            description: an unique identifier for a protein - either it
                         entry number, omaid or its canonical id
        """
        entry_nr = resolve_protein_from_id_or_raise(entry_id)
        proteins = [models.ProteinEntry(utils.db, e)
                    for e in utils.db.get_splicing_variants(entry_nr)]
        serializer = serializers.IsoformProteinSerializer(
            instance=proteins, many=True, context={'request': request})
        return Response(serializer.data)


    @action(detail=True)
    def xref(self, request, entry_id=None, format=None):
        """List of cross-references for a protein.
        ---
        parameters:

          - name: entry_id
            description: an unique identifier for a protein - either it
                         entry number, omaid or its canonical id
        """
        entry_nr = resolve_protein_from_id_or_raise(entry_id)
        xrefs = utils.id_mapper['XRef'].map_entry_nr(entry_nr)
        for ref in xrefs:
            ref['entry_nr'] = entry_nr
            ref['omaid'] = utils.id_mapper['OMA'].map_entry_nr(entry_nr)
        serializer = serializers.XRefSerializer(instance=xrefs, many=True)
        return Response(serializer.data)


class OmaGroupViewSet(PaginationMixin, ViewSet):
    lookup_field = 'group_id'
    schema = DocStringSchemaExtractor()

    def list(self, request, format=None):
        """List of all the OMA Groups in the current release."""
        nr_groups = utils.db.get_nr_oma_groups()
        data = [rest_models.OMAGroup(GroupNr=i) for i in range(1, nr_groups + 1)]
        page = self.paginator.paginate_queryset(data, request)
        serializer = serializers.GroupListSerializer(page, many=True, context={'request': request})
        return self.paginator.get_paginated_response(serializer.data)

    def retrieve(self, request, group_id=None, format=None):
        """Retrieve the information available for a given OMA group.
        ---
        parameters:

          - name: group_id
            description: an unique identifier for an OMA group - either its
                         group number, its fingerprint or an entry id of one
                         of its members
        """
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

    @action(detail=True)
    def close_groups(self, request, group_id=None, format=None):
        """Retrieve the sorted list of closely related groups for a given OMA group.
        ---
        parameters:

          - name: group_id
            description: an unique identifier for an OMA group - either its
                         group number, its fingerprint or an entry id of one
                         of its members
        """

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
    serializer_class = serializers.ProteinEntrySerializer
    schema = DocStringSchemaExtractor()

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
                raise NotFound('Invalid or unknown level parameter for this HOG')
        return level, hog_id

    def _check_level_is_valid(self, level):
        return level.encode('utf-8') in utils.db.tax.all_hog_levels

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

    def list(self, request, format=None):
        """List of all the HOGs identified by OMA.
        ---
        parameters:

          - name: level
            description: filter the list of HOGs by a specific
                         taxonomic level.
            location: query

          - name: compare_with
            description: compares the hog at `level` with those passed
                         with this argument (must be a parent level) and
                         annotates all hogs with the evolutionary events
                         that occured between the two points in time.
            location: query
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

    def retrieve(self, request, hog_id):
        """Retrieve the detail available for a given HOG, along with its deepest level
        (i.e. root level) as well as the list of all the taxonomic levels that the HOG
        spans through.

        For a given hog_id, the endpoint searches the deepest taxonomic level that
        has this ID, unless a more recent level has been chosen with the `level` query
        parameter in which case the following information is returned for all induced
        hogs.

        The endpoint returns an object per hog with the level, urls to the members and
        a list of parent and children hogs. The parent and children hogs are more
        ancient resp. more recent levels that involve at least one duplication event
        on the lineage from the query hog. So, in the parent_hogs, one can find hogs
        for which we infer a duplication event *to* the query hog level, where as
        for the children_hogs there happened at least one duplication event *after*
        the query hog level. In addition, we indicate alternative levels for which
        we infer that no event happened between those levels for this specific hog.
        ---
        parameters:

          - name: hog_id
            description: an unique identifier for a hog_group - either its hog id or one
                         of its member proteins
          - name: level
            description: taxonomic level of restriction for a HOG. The special level
                         'root' can be used to identify the level at the roothog, i.e.
                         the deepest level of that HOG.
            location: query
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

    @action(detail=True)
    def members(self, request, hog_id=None, format=None):
        """Retrieve a list of all the protein members for a given hog_id.

        The hog_id parameter uses an encoding of the inferred duplication
        events along the evolution of the family using the LOFT schema
        (see https://doi.org/10.1186/1471-2105-8-83).

        The hog_id changes only after duplication events and hence, the
        ID remains the same for potentially many taxonomic levels. If
        no level parameter is provided, this endpoint returns the deepest
        level that contains this specific ID.

        If a level is provided, the endpoint returns the members with respect
        to this level. Note that if the level is a more ancient taxonomic
        level than the deepest level for the specified hog_id, the endpoint
        retuns the members of for that more ancient level (but adjusting the
        hog_id in the result object).
        The special level "root" will always return the members of the root
        HOG together with its deepest level.

        ---
        parameters:

          - name: hog_id
            description: a unique identifier for a hog_group - either
                         its hog id starting with "HOG:" or one of its
                         member proteins in which case the specific
                         HOG ID of that protein is used.
            example: HOG:0001221.1a,  P12345

          - name: level
            description: taxonomic level of restriction for a HOG -
                         default is its deepest level for a given
                         HOG ID.
            location: query
            example: "Mammalia"
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

    @action(detail=True)
    def similar_profile_hogs(self, request, hog_id=None, format=None):
        """Returns the HOGs with the most similar phylogenetic profiles.

        The profiles are based on the number of duplications, losses and
        retained genes along the phylogenetic tree. Hence, the profiles are
        computed on the deepest level only and all sub-hogs ids will return
        the same similar HOGs.

        Similar profile search is only useful for hogs that have a certain
        size, i.e. 100 species. For smaller query HOGs, the result will simply
        be empty.

        The result contains for both, the query HOG as well as the similar HOGs
        a field `in_species` that contains a list of all species in which at
        least one copy of the gene is present in the HOG.

        ---
        parameters:

          - name: hog_id
            description: an unique identifier for a hog_group - either
                         its hog id starting with "HOG:" or one of its
                         member proteins in which case the specific
                         HOG ID of that protein is used.
            example: HOG:0450897,  P12345

          - name: max_results
            description: the number of similar profiles to return. Must
                         be a positive number less than 50. By default
                         the 10 most HOGs with the most similar profiles
                         are returned.
            location: query
            example: 20
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

        result = utils.db.get_families_with_similar_hog_profile(
            hog_id, max_nr_similar_fams=nr_profiles)
        nr_species = len(result.species_names)
        sim_hogs = [rest_models.HOG(hog_id=utils.db.format_hogid(fam),
                                    in_species=[result.species_names[z] for z in range(nr_species) if result.similar[fam][z] > 0],
                                    jaccard_similarity=result.jaccard_distance[str(fam)])
                    for fam in result.similar.keys()]
        sim_hogs.sort(key=lambda h: -h.jaccard_similarity)
        data = rest_models.HOG(
            hog_id=hog_id,
            similar_profile_hogs=sim_hogs,
            in_species=[result.species_names[z] for z in range(nr_species) if result.query_profile[z] > 0]
        )
        serializer = serializers.HOGsSimilarProfileSerializer(data, context={'request': request})
        return Response(serializer.data)

    @action(detail=True)
    def gene_ontology(self, request, hog_id=None, format=None):
        """Gene ontology annotations for an ancestral gene (i.e. HOG).

        If a level is provided, the endpoint returns annotations with respect
        to this level. Note that if the level is a more ancient taxonomic
        level than the deepest level for the specified hog_id, the endpoint
        returns the annotations of that more ancient level (but adjusting the
        hog_id in the result object).
        The special level "root" will always return the members of the root
        HOG together with its deepest level.

        ---
        parameters:

          - name: hog_id
            description: a unique identifier for a hog_group - either
                         its hog id starting with "HOG:" or one of its
                         member proteins in which case the specific
                         HOG ID of that protein is used.
            example: HOG:0001221.1a,  P12345

          - name: level
            description: taxonomic level of reference for a HOG -
                         default is its deepest level for a given
                         HOG ID.
            location: query
            example: "Mammalia"
        """
        if hog_id[:4] != "HOG:":
            hog_id = self._hog_id_from_entry(hog_id)
        fam_nr = self._validate_hogid(hog_id)
        level, hog_id = self._get_level_and_get_roothog_if_root_as_level(hog_id)
        hog = self._get_best_matching_hog_or_raise(hog_id, level)
        data = utils.db.get_ancestral_gene_ontology_annotations(hog['Level'], hog['ID'])
        #TODO: fix with better GOA model that allows for both extend and ancestral annotations
        hack_models = [utils.GeneOntologyAnnotation(x) for x in data]
        serializer = serializers.AncestralGeneOntologySerializer(instance=hack_models, many=True)
        return Response(serializer.data)


class SyntenyViewSet(ViewSet):
    schema = DocStringSchemaExtractor()
    lookup_field = 'hog_id'
    lookup_value_regex = r'[^/]+'

    def list(self, request, format=None):
        """List of all the ancestral / extant "contigs" of an ancestral / extant genome.

        Each contig will contain a graph with all the ancestral genes (HOGs) or
        the extant genes and their neighbors as edges (order of ancestral/extant genes
        on "scaffolds/chromosomes")

        The return value is a list of graph objects that consist of 'nodes' and
        'links' attributes.

            {"nodes": [{"id":"HOG:C0594134.1a", ...},
                       {"id":"HOG:C0594135.3c", ...},
                       {"id":"HOG:C0600830.1c.3b", ...}],
             "links": [{"weight":15,"source":"HOG:C0594134.1a","target":"HOG:C0594135.3c"},
                       {"weight":15,"source":"HOG:C0594134.1a","target":"HOG:C0600830.1c.3b"}]
            }

        For extant genes, the gene IDs are the OMA IDs (e.g. `HUMAN00007`)

        ---
        parameters:

          - name: level
            description: The taxonomic level at which the ancestral synteny should
                         be retrieved. The level can be specified with its numeric
                         taxid or the scientific name. For extant genomes, also the
                         UniProt mnemonic species code can be used.
            location: query
            required: True

          - name: evidence
            description: The evidence value for the ancestral synteny graph.
                         This is used for filtering. The evidence values are
                         `linearized` < `parsimonious` < `any`
                         By default, we only show the linearized graph
            location: query
            example: linearized, parsimonious, any

          - name: break_circular_contigs
            description: Some ancestral contigs end up being circles. For certain applications
                         this poses a problem. By setting this argument to "yes" (default),
                         the function will break the circle on the weakest edge, with "no" it
                         will return the full linearized graph. Note that this parameter
                         has no effect if the `evidence` parameter is not equal to "linearized".
            location: query

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
            g = nx.node_link_data(contig)
            for k in ('directed', 'multigraph', 'graph'):
                g.pop(k, None)
            contigs.append(g)
        return Response(contigs)

    def retrieve(self, request, hog_id):
        """
        Returns the ancestral synteny graph around a reference hog at a given taxonomic level.

        ---
        parameters:

          - name: hog_id / protein_id
            description: a unique identifier for a hog_group starting
                         with "HOG:" for ancestral synteny levels, or
                         a unique protein ID (e.g. YEAST00012) for an
                         extant species synteny query.
            example: HOG:0450897, HUMAN01330

          - name: level
            description: the taxonomic level at which the synteny graph
                         should be extracted. If not specified, the
                         deepest level of the given HOG is used. The level
                         can bei either a scientific name or the numeric
                         taxonomy identifier
            location: query
            example: Primates, 9604

          - name: evidence
            description: The evidence value for the ancestral synteny graph.
                         This is used for filtering. The evidence values are
                         `linearized` < `parsimonious` < `any`
            location: query
            example: parsimonious

          - name: context
            description: the size of the graph around the query HOG. By default
                         the HOGs which are at most 2 edges apart from the query
                         HOG are returned.
            location: query

        """
        level = self.request.query_params.get('level', None)
        evidence = self.request.query_params.get('evidence', "any")
        size = int(self.request.query_params.get('context', 2))

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
        graph_as_dict = nx.node_link_data(graph)
        for k in ('directed', 'multigraph', 'graph'):
            graph_as_dict.pop(k, None)
        return Response(graph_as_dict)


class APIVersion(ViewSet):
    def list(self, request, format=None):
        """Returns the version information of the api and
        the underlying oma browser database release."""
        return Response({'oma_version': utils.db.get_release_name(),
                         'api_version': api_settings.DEFAULT_VERSION})


class XRefsViewSet(ViewSet):
    serializer_class = serializers.XRefSerializer
    lookup_field = 'entry_id'
    schema = DocStringSchemaExtractor()

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

    def list(self, request, format=None):
        """List all the crossreferences that match a certain pattern.
        ---
        parameters:
          - name: search
            description: the pattern to be searched for. The pattern
                         must be at least 3 characters long in order to
                         return a hit.
            location: query"""
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
    schema = DocStringSchemaExtractor()

    def list(self, request, format=None):
        """List of all the genomes present in the current release."""
        make_genome = functools.partial(models.Genome, utils.db)
        genomes = [make_genome(g) for g in utils.id_mapper['OMA'].genome_table]
        page = self.paginator.paginate_queryset(genomes, request)
        serializer = serializers.GenomeInfoSerializer(instance=page, many=True, context={'request': request})
        return self.paginator.get_paginated_response(serializer.data)

    def retrieve(self, request, genome_id, format=None):
        """Retrieve the information available for a given genome.
        ---
        parameters:
          - name: genome_id
            description: an unique identifier for a genome
                         - either its ncbi taxon id or the
                         UniProt species code"""
        try:
            g = models.Genome(utils.db, utils.id_mapper['OMA'].identify_genome(genome_id))
        except db.UnknownSpecies as e:
            raise NotFound(e)
        serializer = serializers.GenomeDetailSerializer(instance=g, context={'request': request})
        return Response(serializer.data)

    @action(detail=True)
    def proteins(self, request, genome_id=None):
        """Retrieve the list of all the protein entries available for a genome.
        ---
        parameters:
          - name: genome_id
            description: an unique identifier for a genome
                         - either its ncbi taxon id or the
                         UniProt species code"""

        try:
            g = models.Genome(utils.db, utils.id_mapper['OMA'].identify_genome(genome_id))
            prot = []
            range1 = g.entry_nr_offset + 1
            range2 = range1 + g.nr_entries
            for entry_nr in range(range1, range2):
                prot.append(models.ProteinEntry.from_entry_nr(utils.db, entry_nr))
        except db.UnknownSpecies as e:
            raise NotFound(e)
        page = self.paginator.paginate_queryset(prot, request)
        serializer = serializers.ProteinEntrySerializer(page, many=True, context={'request': request})
        return self.paginator.get_paginated_response(serializer.data)


class PairwiseRelationAPIView(PaginationMixin, APIView):
    schema = DocStringSchemaExtractor()

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

    def get(self, request, genome_id1, genome_id2, chr1=None, chr2=None):
        """List the pairwise relations among two genomes

        The relations are orthologs in case the genomes are
        different and close paralogs and homoeologs in case
        they are the same.

        By using the query_params 'chr1' and 'chr2', one can limit
        the relations to a certain chromosome for one or both
        genomes. The id of the chromosome corresponds to the ids
        returned by the genome endpoint.
        ---
        parameters:
          - name: genome_id1
            description: an unique identifier for the first genome
                         - either its ncbi taxon id or the UniProt
                         species code
          - name: genome_id2
            description: an unique identifier for the second genome
                         - either its ncbi taxon id or the UniProt
                         species code
          - name: chr1
            description: id of the chromosome of interest in the
                         first genome
            location: query

          - name: chr2
            description: id of the chromosome of interest in the
                         second genome
            location: query

          - name: rel_type
            description: limit relations to a certain type of
                        relations, e.g. '1:1'.
            location: query
        """
        rel_type = request.query_params.get('rel_type', None)
        try:
            genome1 = models.Genome(utils.db, utils.db.id_mapper['OMA'].identify_genome(genome_id1))
            genome2 = models.Genome(utils.db, utils.db.id_mapper['OMA'].identify_genome(genome_id2))
        except db.UnknownSpecies as e:
            raise NotFound(e)

        tab_name = 'VPairs' if genome1.uniprot_species_code != genome2.uniprot_species_code else 'within'
        rel_tab = utils.db.get_hdf5_handle().get_node('/PairwiseRelation/{}/{}'.format(
            genome1.uniprot_species_code, tab_name))

        chr1 = request.query_params.get('chr1', None)
        chr2 = request.query_params.get('chr2', None)
        range1 = self._get_entry_range(genome1, chr1)
        range2 = self._get_entry_range(genome2, chr2)
        logger.debug("EntryRanges: ({0[0]},{0[1]}), ({1[0]},{1[1]})".format(range1, range2))

        def obj_factory(data):
            rel = models.PairwiseRelation(utils.db, data)
            if ((chr1 is None or chr1 == rel.entry_1.chromosome) and
                    (chr2 is None or chr2 == rel.entry_2.chromosome)):
                if rel_type is None or rel_type == rel.rel_type:
                    return rel
            return None

        query = '(EntryNr1 >= {0[0]}) & (EntryNr1 <= {0[1]}) ' \
                '& (EntryNr2 >= {1[0]}) & (EntryNr2 <= {1[1]})'.format(range1, range2)
        queryset = LazyPagedPytablesQuery(rel_tab, query=query, obj_factory=obj_factory)
        page = self.paginator.paginate_queryset(queryset, request)
        serializer = serializers.PairwiseRelationSerializer(instance=page, many=True, context={'request': request})
        return self.paginator.get_paginated_response(serializer.data)


class MinimalPairwiseRelation(APIView):
    schema = None

    def get(self, request, genome_id1, genome_id2, format=None):
        """Retrieve minimal version of pairs for a genome pair.
        ---
        parameters:
          - name: genome_id1
            description: an unique identifier for the first genome
                         - either its ncbi taxon id or the UniProt
                         species code
          - name: genome_id2
            description: an unique identifier for the second genome
                         - either its ncbi taxon id or the UniProt
                         species code"""
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


class TaxonomyViewSet(ViewSet):
    lookup_field = 'root_id'
    schema = DocStringSchemaExtractor()

    def list(self, request, format=None):
        """Retrieve the taxonomic tree that is available in the current release.
        ---
        parameters:
          - name: type
            description: the type of the returned data - either
                dictionary (default), newick or phyloxml.
            location: query

          - name: members
            description: list of members to get the induced taxonomy
                from. The list is supposed to be a comma-separated list.
                Member IDs can be either their ncbi taxon IDs or their
                UniProt species codes - they just have to be consistent.
            location: query

          - name: collapse
            description: whether or not taxonomic levels with a single
                child should be collapsed or not. Defaults to yes.
            location: query
            type: boolean
        """

        # e.g. members = YEAST,ASHGO
        members = request.query_params.getlist('members', None)  # read as a string
        type = request.query_params.get('type', None)  # if none, dictionary returned
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
            data = {'root_taxon': root_data, 'newick': tx.newick()}
            serializer = serializers.TaxonomyNewickSerializer(instance=data)
            return Response(serializer.data)
        elif type == "phyloxml":
            phyloxml = tax_obj.as_phyloxml()
            return HttpResponse(phyloxml, content_type="application/xml")
        else:
            data = tx.as_dict()
            return Response(data)

    def retrieve(self, request, root_id, format=None):
        """
        Retrieve the subtree rooted at the taxonomic level indicated.
        ---
        parameters:
          - name: root_id
            description: either the taxon id, species name or the 5 letter UniProt
                species code for a root taxonomic level

          - name: type
            description: the type of the returned data - either dictionary
                 (default) or newick.
            location: query


          - name: collapse
            description: whether or not taxonomic levels with a single
                 child should be collapsed or not. Defaults to yes.
            type: boolean
            location: query
        """
        type = request.query_params.get('type', None)

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
            phyloxml = induced_tax.as_phyloxml()
            return HttpResponse(phyloxml, content_type="application/xml")
        else:
            data = induced_tax.as_dict()
            return Response(data)


class IdentifiySequenceAPIView(APIView):
    schema = DocStringSchemaExtractor()

    def get(self, request, format=None):
        """Identify a protein sequence.
        ---
        parameters:
          - name: query
            description: the sequence to be searched.
            location: query
            required: True
          - name: search
            description: argument to choose search strategy. Can be set
                to 'exact', 'approximate' or 'mixed'. Defaults to 'mixed', meaning
                first tries to find exact match. If no target can be found, uses
                approximate search strategy to identify query sequence in database.
            location: query
          - name: full_length
            description: a boolean indicating whether or not for
                exact matches, the query sequence must be matching the full
                target sequence. By default, a partial exact match is also
                reported as exact match.
            location: query
            type: boolean
        """
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
    schema = DocStringSchemaExtractor()

    def get(self, request, format=None):
        """Annotate a sequence with GO functions based on all
        annotations in OMA. The sequence is expected to be a
        simple string of amino acids and can be passed as a
        query parameter
        ---
        parameters:
          - name: query
            description: the sequence to be annotated
            location: query
            required: True
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
    schema = DocStringSchemaExtractor()

    def get(self, request, genome_id1, genome_id2, format=None):
        """Returns the fraction of shared ancestry between to species of interest.

        ---
        parameters:
          - name: genome_id1
            description: a unique identifier for the first genome
                         - either its ncbi taxon id or the UniProt
                         species code

          - name: genome_id2
            description: a unique identifier for the second genome
                         - either its ncbi taxon id or the UniProt
                         species code

          - name: type
            description: type of orthology information to compute the
                         fraction of shared ancestry, either 'hogs' (default)
                         or 'vps'.
            location: query
        """
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
    serializer_class = serializers.EnrichmentAnalysisInputSerializer
    schema = DocStringSchemaExtractor()

    """
    Submit a Gene Ontology enrichment analysis.
    
    This endpoint accepts requests to perform gene ontology enrichment analysis
    on extant and ancestral gene sets. The jobs will be executed asynchronously.
    The reply of the server will contain a 202 reply with a Location header that 
    points to a url where the status of the job can be checked.
    
    The endpoint accepts json encoded data in a POST request. The data must contain
    a `foreground` set of extant genes (all from the same species) for an extant genome 
    enrichment analysis, or a set of HOGs that exist in an given ancestral taxonomy 
    level. You must indicated whether an ancestral or an extant analysis should be 
    performed by setting the `type` parameter to either `ancestral` or `extant`. 
    In addition, the endpoint accepts an optional `name` parameter.
    
    ---
    parameters:
       - name: type
         description: Indicate type of analysis. either `ancestral` or `extant`.
         
       - name: foreground
         description: set of foreground genes / hogs. The background will 
                      automatically be set as the set of all existing HOGs at the
                      given taxonomic level for the ancestral enrichment analysis,
                      or all the main isoform protein sequences of the extant 
                      species.
         type: list of gene/hog IDs
         
       - name: taxlevel
         description: Taxonomic level at which the ancestral enrichment analysis 
                      should be performed. If extant analysis, this parameter 
                      can be ignored.
         
       - name: name
         description: An optional name for the analysis. 
          
    """
    def perform_create(self, serializer):
        """
        Submit a Gene Ontology enrichment analysis.

        This endpoint accepts requests to perform gene ontology enrichment analysis
        on extant and ancestral gene sets. The jobs will be executed asynchronously.
        The reply of the server will contain a 202 reply with a Location header that
        points to a url where the status of the job can be checked.

        The endpoint accepts json encoded data in a POST request. The data must contain
        a `foreground` set of extant genes (all from the same species) for an extant genome
        enrichment analysis, or a set of HOGs that exist in an given ancestral taxonomy
        level. You must indicated whether an ancestral or an extant analysis should be
        performed by setting the `type` parameter to either `ancestral` or `extant`.
        In addition, the endpoint accepts an optional `name` parameter.

        ---
        parameters:
           - name: type
             description: Indicate type of analysis. either `ancestral` or `extant`.

           - name: foreground
             description: set of foreground genes / hogs. The background will
                          automatically be set as the set of all existing HOGs at the
                          given taxonomic level for the ancestral enrichment analysis,
                          or all the main isoform protein sequences of the extant
                          species.
             type: list of gene/hog IDs

           - name: taxlevel
             description: Taxonomic level at which the ancestral enrichment analysis
                          should be performed. If extant analysis, this parameter
                          can be ignored.

           - name: name
             description: An optional name for the analysis.

        """
        obj = serializer.save(state="PENDING")
        go_enrichment.delay(obj.id)
        return obj



class StatusEnrichmentAnalysisView(StatusAsyncJobAPIView):
    queryset = rest_models.EnrichmentAnalysisModel.objects.all()
    lookup_field = 'id'
    serializer_class = serializers.EnrichmentAnalysisStatusSerializer


