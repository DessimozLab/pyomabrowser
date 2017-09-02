import functools
import operator
import itertools

from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet
from rest_framework.response import Response
from rest_framework.exceptions import NotFound

from . import models as rest_models
from . import serializers
from oma import utils, misc
from pyoma.browser import models, db
import logging

from rest_framework.pagination import PageNumberPagination
from collections import Counter
from rest_framework.decorators import detail_route


logger = logging.getLogger(__name__)


# Create your views here.
class ProteinEntryViewSet(ViewSet):
    serializer_class = serializers.ProteinEntryDetailSerializer
    lookup_field = 'entry_id'

    def retrieve(self, request, entry_id=None, format=None):
        """
        Retrieve the information available for a protein entry.

        :param entry_id: an unique identifier for a protein - either it entry number, omaid or its canonical id

        """

        # Load the entry and its domains, before forming the JSON to draw client-side.
        entry_nr = utils.id_resolver.resolve(entry_id)
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
            entry_nr = row[1]
            ortholog = models.ProteinEntry.from_entry_nr(utils.db, int(entry_nr))
            ortholog.RelType = row[4]
            ortholog.Distance = row[3]
            ortholog.Score = row[2]
            if rel_type is not None:
                if rel_type == ortholog.RelType:
                    content.append(ortholog)
            else:
                content.append(ortholog)
        serializer = serializers.OrthologsListSerializer(instance=content, many=True, context={'request': request})
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


class OmaGroupViewSet(ViewSet):
    lookup_field = 'group_id'
    serializer_class = serializers.ProteinEntrySerializer

    def list(self, request, format=None):
        """List of all the OMA Groups in the current release.

        :queryparam page: the page number of the response json
        """
        nr_groups = utils.db.get_nr_oma_groups()
        data = [rest_models.OMAGroup(GroupNr=i) for i in range(1, nr_groups + 1)]
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(data, request)
        serializer = serializers.GroupListSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

    def retrieve(self, request, group_id=None, format=None):
        """Retrieve the information available for a given OMA group.

        :param group_id: an unique identifier for an OMA group - either its
                         group number, its fingerprint or an entry id of one
                         of its members
        """
        try:
            # get members in case its a group id or fingerprint
            memb = utils.db.oma_group_members(group_id)
        except db.InvalidId:
            try:
                # let's try if group_id is a member protein id
                entry_nr = utils.id_resolver.resolve(group_id)
                prot = models.ProteinEntry.from_entry_nr(utils.db, entry_nr)
                if prot.oma_group == 0:
                    return Response({})
                return self.retrieve(request, prot.oma_group)
            except db.InvalidId:
                raise NotFound(group_id)

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
        serializer = serializers.RelatedGroupsSerializer(
            instance=close_groups, many=True, context={'request': request})
        return Response(serializer.data)


class HOGViewSet(ViewSet):
    lookup_field = 'hog_id'
    lookup_value_regex = r'[^/]+'
    serializer_class = serializers.ProteinEntrySerializer

    def list(self, request, format=None):
        """List of all the HOGs identified by OMA.

        :queryparam level: allows filtering of the list of HOGs by a specific taxonomic level
        :queryparam page: the page number of the response json
        """
        level = self.request.query_params.get('level', None)
        if level != None:
            # filtering by level
            hog_tab = utils.db.get_hdf5_handle().root.HogLevel.read_where('(Level==level)')
            hogs = []
            for row in hog_tab:
                hogs.append(row[1].decode("utf-8"))
            hogs = sorted(hogs)
            data = []
            for row in hogs:
                data.append(rest_models.HOG(hog_id=row, level=level))
            paginator = PageNumberPagination()
            page = paginator.paginate_queryset(data, request)
            serializer = serializers.HOGsListSerializer_at_level(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)

        else:
            # list of all the hogs
            hog_tab = utils.db.get_hdf5_handle().root.HogLevel
            hogs = []
            for row in hog_tab:
                hogs.append(row['ID'].decode("utf-8"))
            hog_ids = sorted(set(hogs))
            data = []
            for row in hog_ids:
                data.append(rest_models.HOG(hog_id=row))
            paginator = PageNumberPagination()
            page = paginator.paginate_queryset(data, request)
            serializer = serializers.HOGsListSerializer(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)

    def retrieve(self, request, hog_id):
        """Retrieve the detail available for a given HOG, along with its deepest level
        (i.e. root level) as well as the list of all the taxonomic levels that the HOG
        spans through.

        :param hog_id: an unique identifier for a hog_group - either its hog id or one
                       of its member proteins
        :queryparam level: taxonomic level of restriction for a HOG. If indicated
                           returns a list of any subghogs at that level.
        """
        level = self.request.query_params.get('level', None)
        if hog_id[:3] != "HOG":
            # hog_id == member
            entry_nr = utils.id_resolver.resolve(hog_id)
            protein = models.ProteinEntry.from_entry_nr(utils.db, entry_nr)
            hog_id = protein.oma_hog
        if level == None:
            hogs_tab = utils.db.get_hdf5_handle().root.HogLevel.read_where('(ID==hog_id)')
            levels = []
            for row in hogs_tab:
                hog_model = rest_models.HOG(hog_id=row[1].decode("utf-8"), level=row[2].decode("utf-8"))
                levels.append(hog_model)

            # below is the root level calculation
            members = [models.ProteinEntry(utils.db, memb) for memb in utils.db.member_of_hog_id(hog_id)]
            # get all levels for a hog_id
            fam_nr = members[0].hog_family_nr
            levels_for_fam = utils.db.hog_levels_of_fam(fam_nr)
            # take first member, get species
            species = members[0].genome
            # get lineage of the species
            lineage = species.lineage
            # indexing of levels for a hog
            if len(hog_id) > 11:  # i.e. it is a subhog
                # root level for subhogs is the level at which they appear i.e. when the duplication occured
                for lvl in levels_for_fam:
                    subhogs = utils.db.get_subhogids_at_level(fam_nr, lvl)
                    if subhogs is not None:
                        for subhog in subhogs:
                            subhog = subhog.decode("utf-8")
                            if subhog == hog_id:
                                root_hog_level = lvl.decode("utf-8")
            else:  # not a subhog
                if 'LUCA' in levels:
                    # last universal common ancestor is the deepest level by default
                    root_hog_level = 'LUCA'
                else:
                    indexed_levels = []
                    for level in levels_for_fam:
                        level = level.decode("utf-8")
                        if level in lineage:
                            level_index = lineage.index(level)
                            indexed_levels.append([level, int(level_index)])
                    indexed_levels.sort(key=lambda x: x[1])
                    root_hog_level = indexed_levels[-1][0]
                    levels = []  # the spanning levels for the whole hog i.e the family number
                    for level in levels_for_fam:
                        hog_model = rest_models.HOG(hog_id=hog_id, level=level.decode("utf-8"))
                        levels.append(hog_model)
            data = {'hog_id': hog_id, 'root_level': root_hog_level, 'levels': levels}
            serializer = serializers.HOGDetailSerializer(instance=data, context={'request': request})
            return Response(serializer.data)
        else:
            # level specified, returns a list of all the subhogs at a level
            members = [models.ProteinEntry(utils.db, memb) for memb in utils.db.member_of_hog_id(hog_id)]
            fam_nr = members[0].hog_family_nr
            subhogs = utils.db.get_subhogids_at_level(fam_nr, level)
            subHOGs_2 = []
            for i in subhogs:
                # create hog model instances
                subHOGs_2.append(rest_models.HOG(hog_id=i.decode("utf-8"), level=level))
            data = {'hog_id': hog_id, 'level': level, 'subhogs': subHOGs_2}
            serializer = serializers.HOGInfoSerializer(instance=data, context={'request': request})
            return Response(serializer.data)

    @detail_route()
    def members(self, request, hog_id=None, format=None):
        """Retrieve a list of all the protein members for a given hog_id.

        :param hog_id: an unique identifier for a hog_group - either
                       its hog id starting with "HOG:" or one of its
                       member proteins
        :queryparam level: taxonomic level of restriction for a HOG -
                           default is its deepest most i.e. root level.
        """
        level = self.request.query_params.get('level', None)
        if level != None:
            members = [models.ProteinEntry(utils.db, memb) for memb in utils.db.member_of_hog_id(hog_id)]
            data = {'hog_id': hog_id, 'level': level,
                    'members': members}
            serializer = serializers.HOGMembersListSerializer(instance=data, context={'request': request})
            return Response(serializer.data)
        else:
            members = [models.ProteinEntry(utils.db, memb) for memb in utils.db.member_of_hog_id(hog_id)]
            # get all levels for a hog_id
            fam_nr = members[0].hog_family_nr
            levels = utils.db.hog_levels_of_fam(fam_nr)
            # take first member, get species
            species = members[0].genome
            # get lineage of the species
            lineage = species.lineage
            # indexing of levels for a hog
            if len(hog_id) > 11:
                for lvl in levels:
                    subhogs = utils.db.get_subhogids_at_level(fam_nr, lvl)
                    if subhogs is not None:
                        for subhog in subhogs:
                            subhog = subhog.decode("utf-8")
                            if subhog == hog_id:
                                root_hog_level = lvl.decode("utf-8")
            else:
                if 'LUCA' in levels:
                    root_hog_level = 'LUCA'
                else:
                    indexed_levels = []
                    for level in levels:
                        level = level.decode("utf-8")
                        if level in lineage:
                            level_index = lineage.index(level)
                            indexed_levels.append([level, int(level_index)])
                    indexed_levels.sort(key=lambda x: x[1])
                    root_hog_level = indexed_levels[-1][0]
            data = {'hog_id': hog_id, 'root_level': root_hog_level,
                    'members': members}
            serializer = serializers.RootHOGserializer(instance=data, context={'request': request})
            return Response(serializer.data)


class APIVersion(ViewSet):
    def list(self, request, format=None):
        """Returns the version of the underlying oma browser database release."""
        return Response({'oma-version': utils.db.get_release_name()})


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


class GenomeViewSet(ViewSet):
    lookup_field = 'genome_id'

    def list(self, request, format=None):
        """List of all the genomes present in the current release.

        :queryparam page: the page number of the response json"""
        make_genome = functools.partial(models.Genome, utils.db)
        genomes = [make_genome(g) for g in utils.id_mapper['OMA'].genome_table]
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(genomes, request)
        serializer = serializers.GenomeInfoSerializer(instance=page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

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
                          UniProt species code
        :queryparam page: the page number of the response json"""

        try:
            g = models.Genome(utils.db, utils.id_mapper['OMA'].identify_genome(genome_id))
            prot = []
            range1 = g.entry_nr_offset + 1
            range2 = range1 + g.nr_entries
            for entry_nr in range(range1, range2):
                prot.append(models.ProteinEntry.from_entry_nr(utils.db, entry_nr))
        except db.UnknownSpecies as e:
            raise NotFound(e)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(prot, request)
        serializer = serializers.ProteinEntrySerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)


class PairwiseRelationAPIView(APIView):
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
        :queryparam chr1: id of the chromosome of interest in the first genome
        :queryparam chr2: id of the chromosome of interest in the second genome
        :queryparam page: the page number of the response json
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
        res = []

        logger.debug("EntryRanges: ({0[0]},{0[1]}), ({1[0]},{1[1]})".format(range1, range2))
        for cnt, row in enumerate(rel_tab.where('(EntryNr1 >= {0[0]}) & (EntryNr1 <= {0[1]}) & '
                                                '(EntryNr2 >= {1[0]}) & (EntryNr2 <= {1[1]})'
                                                        .format(range1, range2))):
            rel = models.PairwiseRelation(utils.db, row.fetch_all_fields())
            if ((chr1 is None or chr1 == rel.entry_1.chromosome) and
                    (chr2 is None or chr2 == rel.entry_2.chromosome)):
                if rel_type == None:
                    res.append(rel)
                else:
                    if rel_type == rel.rel_type:
                        res.append(rel)
                if cnt + 1 % 100 == 0:
                    logger.debug("Processed {} rows".format(cnt))

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(res, request)
        serializer = serializers.PairwiseRelationSerializer(instance=page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)


class TaxonomyViewSet(ViewSet):
    lookup_field = 'root_id'

    def list(self, request, format=None):
        """Retrieve the taxonomic tree that is available in the current release.

        :queryparam type: the type of the returned data - either dictionary (default) or newick.
        :queryparam members: list of members to get the induced the taxonomy from.
               Member id's can be either their ncbi taxon ids or their UniProt
               species codes - they just have to be consistent.
        """

        # e.g. members = YEAST,ASHGO
        members = request.query_params.get('members', None)  # read as a string
        type = request.query_params.get('type', None)  # if none, dictionary returned
        taxonomy_tab = utils.db.get_hdf5_handle().root.Taxonomy
        tax_obj = db.Taxonomy(taxonomy_tab[0:int(len(taxonomy_tab))])
        if members != None:
            members = members.split(',')  # as the query param is passed as a string
            members_list = []
            try:
                int(members[0])
                isListOfNames = False
            except:
                isListOfNames = True
            if isListOfNames:
                decoded_members_array = []
                for i in range(len(members)):
                    decoded_members_array.append(members[i])
                if (len(members[0])) > 5:  # names provided
                    for i in range(len(decoded_members_array)):
                        for lvl in taxonomy_tab.read(field='Name'):
                            if str(lvl.decode("utf-8")) == decoded_members_array[i]:
                                members_list.append(lvl)
                else:  # if user provides a list of oma_ids
                    for i in range(len(decoded_members_array)):
                        genome_tab = utils.db.get_hdf5_handle().root.Genome
                        encoded_id = decoded_members_array[i].encode("utf-8")
                        txn_id = genome_tab.read_where('UniProtSpeciesCode == encoded_id', field='NCBITaxonId')
                        members_list.append(str(txn_id)[1:-1])
            else:
                # handling the case user gave a list of NCBI taxon ids
                for i in range(len(members)):
                    members_list.append(members[i])
            tx = tax_obj.get_induced_taxonomy(members=members_list)
            root = tx._get_root_taxon()
            root_data = {'name': root[2].decode("utf-8"), 'taxon_id': root[0]}
            if type == 'newick':
                data = {'root_taxon': root_data, 'newick': tx.newick()}
                serializer = serializers.TaxonomyNewickSerializer(instance=data)
                return Response(serializer.data)
            else:
                data = tx.as_dict()
                return Response(data)

        else:
            # whole taxonomy returned
            root = tax_obj._get_root_taxon()
            root_data = {'name': root[2].decode("utf-8"), 'taxon_id': root[0]}
            if type == 'newick':
                data = {'root_taxon': root_data, 'newick': tax_obj.newick()}
                serializer = serializers.TaxonomyNewickSerializer(instance=data)
                return Response(serializer.data)
            else:
                data = tax_obj.as_dict()
                return Response(data)

    def retrieve(self, request, root_id, format=None):
        """
         Retrieve the subtree rooted at the taxonomic level indicated.

         :param root_id: either the taxon id, species name or the 5 letter UniProt species code for a root taxonomic level
         :queryparam type: the type of the returned data - either dictionary (default) or newick.
         """
        type = request.query_params.get('type', None)
        subtree = []
        taxonomy_tab = utils.db.get_hdf5_handle().root.Taxonomy
        tax_obj = db.Taxonomy(taxonomy_tab[0:int(len(taxonomy_tab))])

        try:
            taxon_id = int(root_id)
        except:
            if root_id.isupper():
                genome_tab = utils.db.get_hdf5_handle().root.Genome
                encoded_id = root_id.encode("utf-8")
                taxon_id = genome_tab.read_where('UniProtSpeciesCode == encoded_id', field='NCBITaxonId')
                taxon_id = int(taxon_id)
            else:
                taxon_id = taxonomy_tab.read_where('Name==root_id', field='NCBITaxonId')
                taxon_id = int(taxon_id)

        def get_children(id):
            children = db.Taxonomy._direct_children_taxa(tax_obj, id)
            if len(children) > 0:
                for child in children:
                    child_id = child['NCBITaxonId']
                    subtree.append(child_id)
                    get_children(child_id)
            return subtree

        subtree.append(taxon_id)
        branch = get_children(taxon_id)
        induced_tax = tax_obj.get_induced_taxonomy(members=branch)

        if type == 'newick':
            root_taxon = tax_obj._taxon_from_numeric(taxon_id)
            root_data = {'name': root_taxon[2].decode("utf-8"), 'taxon_id': root_taxon[0]}
            data = {'root_taxon': root_data, 'newick': induced_tax.newick()}
            serializer = serializers.TaxonomyNewickSerializer(instance=data)
            return Response(serializer.data)
        else:
            data = induced_tax.as_dict()
            return Response(data)
