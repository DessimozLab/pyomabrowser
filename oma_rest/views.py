import functools
import operator
import itertools
import os

import Bio.SeqRecord
import Bio.Alphabet.IUPAC
import Bio.Seq
import collections

from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, ParseError
from rest_framework.settings import api_settings
from django.http import HttpResponse
from distutils.util import strtobool

from . import models as rest_models
from . import serializers
from .pagination import PaginationMixin, LazyPagedPytablesQuery

from oma import utils, misc
from pyoma.browser import models, db
import logging

from collections import Counter
from rest_framework.decorators import detail_route, list_route
logger = logging.getLogger(__name__)


# Create your views here.
class ProteinEntryViewSet(ViewSet):
    serializer_class = serializers.ProteinEntryDetailSerializer
    lookup_field = 'entry_id'

    @list_route(methods=['post'])
    def bulk_retrieve(self, request, format=None):
        """Retrieve the information available for multiple protein IDs at once.

        The POST request must contain a json-encoded list of IDs of
        up to 100 IDs for which the information is returned.

        In case the ID is not unique or unknown, an empty element is
        returned for this query element.

        :param ids: list of ids of proteins to retrieve.

        """
        MAX_SIZE = 100
        if 'ids' not in request.data:
            raise NotFound("No results found")
        if len(request.data['ids']) > MAX_SIZE:
            raise ParseError("POST request exceeded max number of ids. Please limit to {}".format(MAX_SIZE))

        proteins = []
        for entry_id in request.data['ids']:
            try:
                entry_nr = utils.id_resolver.resolve(entry_id)
                proteins.append(models.ProteinEntry.from_entry_nr(utils.db, entry_nr))
            except (db.InvalidId, db.AmbiguousID):
                proteins.append(None)
        serializer = serializers.ProteinEntryDetailSerializer(
            instance=proteins, many=True, context={'request': request})
        return Response(serializer.data)

    def retrieve(self, request, entry_id=None, format=None):
        """
        Retrieve the information available for a protein entry.

        :param entry_id: an unique identifier for a protein - either it entry number, omaid or its canonical id

        """

        # Load the entry and its domains, before forming the JSON to draw client-side.
        try:
            entry_nr = utils.id_resolver.resolve(entry_id)
        except db.InvalidId:
            raise NotFound('requested id is unknown')
        protein = models.ProteinEntry.from_entry_nr(utils.db, entry_nr)
        serializer = serializers.ProteinEntryDetailSerializer(
            instance=protein, context={'request': request})
        return Response(serializer.data)

    @detail_route()
    def orthologs(self, request, entry_id=None, format=None):
        """List of all the identified orthologues for a protein.

        Possible to filter out orthologs by specifying the ?rel_type
        query parameter.

        :param entry_id: an unique identifier for a protein - either it
                         entry number, omaid or its canonical id
        :queryparam rel_type: allows the user to filter the orthologs
                              for a specific relationship type only
        """
        rel_type = request.query_params.get('rel_type', None)
        p_entry_nr = utils.id_resolver.resolve(entry_id)
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

    @detail_route()
    def homoeologs(self, request, entry_id=None, format=None):
        """List of all the homoeologs for a given protein.

        :param entry_id: an unique identifier for a protein - either its
            entry number, omaid or canonical id."""
        entry_nr = utils.id_resolver.resolve(entry_id)
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

    @detail_route()
    def ontology(self, request, entry_id=None, format=None):
        """Ontology information available for a protein.

        :param entry_id: an unique identifier for a protein - either it
                         entry number, omaid or its canonical id
        """
        p_entry_nr = utils.id_resolver.resolve(entry_id)
        data = db.Database.get_gene_ontology_annotations(utils.db, int(p_entry_nr))
        ontologies = [models.GeneOntologyAnnotation(utils.db, m) for m in data]
        serializer = serializers.GeneOntologySerializer(instance=ontologies, many=True)
        return Response(serializer.data)

    @detail_route()
    def domains(self, request, entry_id=None, format=None):
        """List of the domains present in a protein.

        :param entry_id: an unique identifier for a protein - either it entry number, omaid or its canonical id
        """
        entry_nr = utils.id_resolver.resolve(entry_id)
        entry = utils.db.entry_by_entry_nr(entry_nr)
        domains = utils.db.get_domains(entry['EntryNr'])
        response = misc.encode_domains_to_dict(entry, domains, utils.domain_source)
        return Response(response)

    @detail_route()
    def xref(self, request, entry_id=None, format=None):
        """List of cross-references for a protein.

        :param entry_id: an unique identifier for a protein - either it
                         entry number, omaid or its canonical id
        """
        entry_nr = utils.id_resolver.resolve(entry_id)
        xrefs = utils.id_mapper['XRef'].map_entry_nr(entry_nr)
        for ref in xrefs:
            ref['entry_nr'] = entry_nr
            ref['omaid'] = utils.id_mapper['OMA'].map_entry_nr(entry_nr)
        serializer = serializers.XRefSerializer(instance=xrefs, many=True)
        return Response(serializer.data)


class OmaGroupViewSet(PaginationMixin, ViewSet):
    lookup_field = 'group_id'

    def list(self, request, format=None):
        """List of all the OMA Groups in the current release."""
        nr_groups = utils.db.get_nr_oma_groups()
        data = [rest_models.OMAGroup(GroupNr=i) for i in range(1, nr_groups + 1)]
        page = self.paginator.paginate_queryset(data, request)
        serializer = serializers.GroupListSerializer(page, many=True, context={'request': request})
        return self.paginator.get_paginated_response(serializer.data)

    def retrieve(self, request, group_id=None, format=None):
        """Retrieve the information available for a given OMA group.

        :param group_id: an unique identifier for an OMA group - either its
                         group number, its fingerprint or an entry id of one
                         of its members
        """
        try:
            # get members in case its a group id or fingerprint
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
            group = rest_models.OMAGroup(GroupNr=data['group_nr'], members=members, fingerprint=fingerprint)

        serializer = serializers.OmaGroupSerializer(
            instance=group, context={'request': request})
        return Response(serializer.data)

    @detail_route()
    def close_groups(self, request, group_id=None, format=None):
        """Retrieve the sorted list of closely related groups for a given OMA group.

        :param group_id: an unique identifier for an OMA group - either its
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

    def _hog_id_from_entry(self, entry_id):
        try:
            entry_nr = utils.id_resolver.resolve(entry_id)
            protein = utils.ProteinEntry(entry_nr)
            if len(protein.oma_hog) == 0:
                raise NotFound("{} is not part of any HOG.".format(entry_id))
            return protein.oma_hog
        except db.InvalidId:
            raise NotFound("{} is an unknown identifier for a protein".format(entry_id))

    def _get_level_and_adjust_hogid_if_needed(self, hog_id):
        level = self.request.query_params.get('level', None)
        if level is not None:
            if level.lower() == "root":
                level = None
                hog_id = utils.db.format_hogid(utils.db.parse_hog_id(hog_id))
            elif not self._check_level_is_valid(level):
                raise ParseError('Invalid or unknown level parameter for this HOG')
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

    def list(self, request, format=None):
        """List of all the HOGs identified by OMA.

        :queryparam level: allows filtering of the list of HOGs by
            a specific taxonomic level.
        """
        level, _ = self._get_level_and_adjust_hogid_if_needed('HOG:000001')
        if level is not None:
            query = 'Level == {!r}'.format(level.encode('utf-8'))
            queryset = LazyPagedPytablesQuery(table=utils.db.get_hdf5_handle().get_node('/HogLevel'),
                                              query=query,
                                              obj_factory=lambda r: rest_models.HOG(hog_id=r['ID'].decode(),
                                                                                    level=level))
        else:
            # list of all the rootlevel hogs
            nr_hogs = utils.db.get_nr_toplevel_hogs()
            queryset = [rest_models.HOG(hog_id=utils.db.format_hogid(i), level="root") for i in range(1, nr_hogs + 1)]
        page = self.paginator.paginate_queryset(queryset, request)
        serializer = serializers.HOGsListSerializer(page, many=True, context={'request': request})
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

        :param hog_id: an unique identifier for a hog_group - either its hog id or one
                       of its member proteins
        :queryparam level: taxonomic level of restriction for a HOG. The special level
            'root' can be used to identify the level at the roothog.
        """
        if hog_id[:4] != "HOG:":
            # hog_id == member
            hog_id = self._hog_id_from_entry(hog_id)

        level, hog_id = self._get_level_and_adjust_hogid_if_needed(hog_id)
        fam_nr = utils.db.parse_hog_id(hog_id)
        if level is None:
            levs = frozenset(
                [row['Level'].decode() for row in utils.db.get_hdf5_handle().root.HogLevel.where('(ID==hog_id)')])
            if 'LUCA' in levs:
                level = 'LUCA'
            else:
                pe = next(utils.db.iter_members_of_hog_id(hog_id))
                lin = pe.genome.lineage
                for level in lin[::-1]:
                    if level in levs:
                        break
            result_data = [rest_models.HOG(hog_id=hog_id, level=level)]
        else:
            subhogs = utils.db.get_subhogids_at_level(fam_nr, level)
            result_data = []
            for h in subhogs:
                h = h.decode()
                if hog_id.startswith(h) or h.startswith(hog_id):
                    result_data.append(rest_models.HOG(hog_id=h, level=level))

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

    @detail_route()
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

        :param hog_id: an unique identifier for a hog_group - either
                       its hog id starting with "HOG:" or one of its
                       member proteins in which case the specific
                       HOG ID of that protein is used.
        :queryparam level: taxonomic level of restriction for a HOG -
                           default is its deepest level for a given
                           HOG ID. .
        """
        if hog_id[:4] != "HOG:":
            hog_id = self._hog_id_from_entry(hog_id)

        level, hog_id = self._get_level_and_adjust_hogid_if_needed(hog_id)
        if level is not None:
            members = [utils.ProteinEntry(entry) for entry in utils.db.hog_members_from_hog_id(hog_id, level)]
            hog_id = self._identify_lca_hog_id_from_proteins(members)
        else:
            fam_nr = utils.db.parse_hog_id(hog_id)
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


class APIVersion(ViewSet):
    def list(self, request, format=None):
        """Returns the version information of the api and the underlying oma browser database release."""
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
        xrefs = self._order_xrefs(xrefs, ('xref', 'source'))
        res = []
        for k, grp in itertools.groupby(xrefs, key=operator.itemgetter('xref')):
            res.append(next(grp))
        return res

    def list(self, request, format=None):
        """List all the crossreferences that match a certain pattern.

        :queryparam search: the pattern to be searched for. The pattern
                            must be at least 3 characters long in order to
                            return a hit."""
        pattern = request.query_params.get('search', None)
        res = []
        if pattern is not None and len(pattern) >= 3:
            make_genome = functools.partial(models.Genome, utils.db)
            enr_to_genome = utils.id_mapper['OMA'].genome_of_entry_nr
            xref_mapper = utils.id_mapper['XRef']
            for ref in xref_mapper.search_xref(pattern, is_prefix=True):
                res.append({'entry_nr': ref['EntryNr'],
                            'omaid': utils.id_mapper['OMA'].map_entry_nr(ref['EntryNr']),
                            'source': xref_mapper.source_as_string(ref['XRefSource']),
                            'xref': ref['XRefId'].decode(),
                            'genome': make_genome(enr_to_genome(ref['EntryNr']))})
            res = self._remove_redundant_xrefs(res)
        serializer = serializers.XRefSerializer(instance=res, many=True, context={'request': request})
        return Response(serializer.data)


class GenomeViewSet(PaginationMixin, ViewSet):
    lookup_field = 'genome_id'

    def list(self, request, format=None):
        """List of all the genomes present in the current release."""
        make_genome = functools.partial(models.Genome, utils.db)
        genomes = [make_genome(g) for g in utils.id_mapper['OMA'].genome_table]
        page = self.paginator.paginate_queryset(genomes, request)
        serializer = serializers.GenomeInfoSerializer(instance=page, many=True, context={'request': request})
        return self.paginator.get_paginated_response(serializer.data)

    def retrieve(self, request, genome_id, format=None):
        """Retrieve the information available for a given genome.

        :param genome_id: an unique identifier for a genome
                         - either its ncbi taxon id or the
                         UniProt species code"""
        try:
            g = models.Genome(utils.db, utils.id_mapper['OMA'].identify_genome(genome_id))
        except db.UnknownSpecies as e:
            raise NotFound(e)
        serializer = serializers.GenomeDetailSerializer(instance=g, context={'request': request})
        return Response(serializer.data)

    @detail_route()
    def proteins(self, request, genome_id=None):
        """Retrieve the list of all the protein entries available for a genome.

        :param genome_id: an unique identifier for a genome
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

        :param genome_id1: an unique identifier for the first genome
                           - either its ncbi taxon id or the UniProt
                           species code
        :param genome_id2: an unique identifier for the second genome
                           - either its ncbi taxon id or the UniProt
                           species code
        :queryparam chr1: id of the chromosome of interest in the
                          first genome
        :queryparam chr2: id of the chromosome of interest in the
                          second genome
        :queryparam rel_type: limit relations to a certain type of
                          relations, e.g. '1:1'.
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


class TaxonomyViewSet(ViewSet):
    lookup_field = 'root_id'

    def list(self, request, format=None):
        """Retrieve the taxonomic tree that is available in the current release.

        :queryparam type: the type of the returned data - either
               dictionary (default), newick or phyloxml.

        :queryparam members: list of members to get the induced taxonomy
               from. The list is supposed to be a comma-separated list.
               Member IDs can be either their ncbi taxon IDs or their
               UniProt species codes - they just have to be consistent.

        :queryparam collapse: whether or not taxonomic levels with a single
            child should be collapsed or not. Defaults to yes.
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

        :param root_id: either the taxon id, species name or the 5 letter UniProt
            species code for a root taxonomic level

        :queryparam type: the type of the returned data - either dictionary
            (default) or newick.

        :queryparam collapse: whether or not taxonomic levels with a single
            child should be collapsed or not. Defaults to yes.
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
    def get(self, request, format=None):
        """Identify a protein sequence

        :queryparam query: the sequence to be searched.
        :queryparam search: argument to choose search strategy. Can be set
            to 'exact', 'approximate' or 'mixed'. Defaults to 'mixed', meaning
            first tries to find exact match. If no target can be found, uses
            approximate search strategy to identify query sequence in database.
        :queryparam full_length: a boolean indicating whether or not for
            exact matches, the query sequence must be matching the full
            target sequence. By default, a partial exact match is also
            reported as exact match."""
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
    def get(self, request, format=None):
        """Annotate a sequence with GO functions based on all
        annotations in OMA.

        :queryparam query: the sequence to be annotated"""
        query_seq = request.query_params.get('query', '')
        query_seq = utils.db.seq_search._sanitise_seq(query_seq)
        if len(query_seq) < 10:
            raise ParseError('The query sequence must be at least 10 amino acids long.')

        seq_list = [Bio.SeqRecord.SeqRecord(Bio.Seq.Seq(query_seq.decode(), Bio.Alphabet.IUPAC.protein), id='unknown')]
        projector = db.FastMapper(utils.db)
        annotations = []
        for anno in projector.iter_projected_goannotations(seq_list):
            for key in ("DB_Object_Symbol", "DB_Object_ID", "Taxon_ID", "Gene_Product_Form_ID", "Annotation_Extension"):
                anno.pop(key)
            anno['GO_name'] = utils.db.gene_ontology.term_by_id(anno['GO_ID']).name
            annotations.append(anno)
        return Response(annotations)