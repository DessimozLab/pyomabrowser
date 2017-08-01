import functools
import operator
import itertools

from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from oma import utils, misc
from . import serializers
from pyoma.browser import models, db
import logging

from rest_framework.pagination import PageNumberPagination
from collections import Counter
from rest_framework.decorators import detail_route
from oma import models as m


logger = logging.getLogger(__name__)


# Create your views here.
class ProteinEntryViewSet(ViewSet):
    serializer_class = serializers.ProteinEntryDetailSerializer
    lookup_field = 'entry_id'

    def retrieve(self, request, entry_id=None, format=None):
        """
        Retrieve the basic information on a protein

        :param entry_id: an unique identifier for a protein
        """
        # Load the entry and its domains, before forming the JSON to draw client-side.
        entry_nr = utils.id_resolver.resolve(entry_id)
        serializer = serializers.ProteinEntryDetailSerializer(
            instance=models.ProteinEntry.from_entry_nr(utils.db, entry_nr),
            context={'request': request})
        return Response(serializer.data)

    @detail_route()
    def hog_levels(self,request,entry_id=None,format=None):
        entry_nr = utils.id_resolver.resolve(entry_id)
        protein = models.ProteinEntry.from_entry_nr(utils.db, entry_nr)
        levels = utils.db.hog_levels_of_fam(protein.hog_family_nr)
        protein_levels = []
        for level in levels:
            level = level.decode("utf-8")
            members_at_level = [models.ProteinEntry(utils.db, memb) for memb in utils.db.member_of_hog_id(protein.oma_hog, level)]
            for member in members_at_level:
                if str(member) == str(protein) and level not in protein_levels:
                    protein_levels.append(level)
        data = []
        for level in protein_levels:
            data.append(m.HOG(hog_id=protein.oma_hog,level=level))
        serializer = serializers.HOGsLevelSerializer(instance = data, many= True, context={'request': request} )
        return Response(serializer.data)

    @detail_route()
    def  orthologs(self, request, entry_id=None, format=None):
        """
            List of all the identified orthologues for a protein
                       """
        rel_type = request.query_params.get('rel_type', None)
        p_entry_nr = utils.id_resolver.resolve(entry_id)
        data = utils.db.get_vpairs(int(p_entry_nr))
        content = []
        for row in data:
            entry_nr = row[1]
            ortholog = models.ProteinEntry.from_entry_nr(utils.db, int(entry_nr))
            if rel_type != None:
                if row[4]==rel_type:
                    content.append({'ortholog': ortholog, 'RelType': row[4], 'Distance': row[3], 'Score': row[2]})
                else:
                    pass
            else:
                content.append({'ortholog': ortholog, 'RelType': row[4], 'Distance': row[3], 'Score': row[2]})
        serializer = serializers.OrthologsListSerializer(instance=content, many=True)
        return Response(serializer.data)

    @detail_route()
    def ontology(self, request, entry_id=None, format=None):
        """
                    Ontology information available for a protein
                               """
        p_entry_nr = utils.id_resolver.resolve(entry_id)
        data = db.Database.get_gene_ontology_annotations(utils.db, int(p_entry_nr))
        ontologies = [models.GeneOntologyAnnotation(utils.db, m) for m in data]
        serializer = serializers.GeneOntologySerializer(instance=ontologies, many=True)
        return Response(serializer.data)

    @detail_route()
    def domains(self,request,entry_id=None, format=None):
        """
                    List of the domains present in a protein
                               """
        entry_nr = utils.id_resolver.resolve(entry_id)
        entry = utils.db.entry_by_entry_nr(entry_nr)
        domains = utils.db.get_domains(entry['EntryNr'])
        response = misc.encode_domains_to_dict(entry, domains, utils.domain_source)
        return Response(response)

    @detail_route()
    def xref(self, request, entry_id=None, format=None):
        """
                    List of cross-references for a protein
                               """
        entry_nr = utils.id_resolver.resolve(entry_id)
        xrefs = utils.id_mapper['XRef'].map_entry_nr(entry_nr)
        for ref in xrefs:
            ref['entry_nr'] = entry_nr
            ref['omaid'] = utils.id_mapper['OMA'].map_entry_nr(entry_nr)
        serializer = serializers.XRefSerializer(instance=xrefs, many=True)
        return Response(serializer.data)






class OmaGroupViewSet(ViewSet):
    lookup_field = 'id'
    serializer_class = serializers.ProteinEntrySerializer

    def retrieve(self, request, id=None, format=None):
        """
               Retrieve the meta data on the OMA group, its protein members and related groups

               :param group_id: an unique identifier for an OMA group
               """
        members = [models.ProteinEntry(utils.db, m) for m in utils.db.oma_group_members(id)]
        data = utils.db.oma_group_metadata(members[0].oma_group)
        fingerprint = data['fingerprint']
        group = m.OMAGroup(GroupNr=id, members=members, fingerprint=fingerprint)
        serializer = serializers.OmaGroupSerializer(
            instance=group, context={'request': request})
        return Response(serializer.data)

    @detail_route()
    def close_groups(self, request, id=None, format = None):
        members = [models.ProteinEntry(utils.db, m) for m in utils.db.oma_group_members(id)]
        data = utils.db.oma_group_metadata(members[0].oma_group)
        content = []
        for m in members:
            # get all the verified pairs
            vpairs = utils.db.get_vpairs(m.entry_nr)
            # vpairs into instances of the ProteinEntry model
            for row in vpairs:
                entry_nr = row[1]
                ortholog = models.ProteinEntry.from_entry_nr(utils.db, int(entry_nr))
                content.append(ortholog)
        groups = []

        for row in content:
            if row.oma_group == int(id):
                pass
            else:
                groups.append(row.oma_group)
        # count the groups' hits and return in form of a list instead of a dictionary
        r_groups = Counter(groups).most_common()
        data['related_groups'] = sorted(r_groups)
        serializer = serializers.CloseGroupsSerializer(
            instance=data)
        return Response(serializer.data)


class HOGsViewSet(ViewSet):
    lookup_field = 'hog_id'
    lookup_value_regex = r'[^/]+'
    serializer_class = serializers.ProteinEntrySerializer

    def list(self, request, format = None):
        """
               List of all the roothog_id's HOGs currently identified and the url to access their details


               """
        level = self.request.query_params.get('level', None)
        if level != None:
            hog_tab = utils.db.get_hdf5_handle().root.HogLevel.read_where('(Level==level)')
            hogs = []
            for row in hog_tab:
                hogs.append(row[1].decode("utf-8"))
            hogs=sorted(hogs)
            data = []
            for row in hogs:
                data.append(m.HOG(hog_id=row, level=level))
            paginator = PageNumberPagination()
            page = paginator.paginate_queryset(data, request)
            serializer = serializers.HOGsListSerializer_at_level(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)

        else:
            hog_tab = utils.db.get_hdf5_handle().root.HogLevel
            hogs = []
            for row in hog_tab:
                hogs.append(row[1].decode("utf-8"))
            hog_ids = sorted(set(hogs))
            data=[]
            for row in hog_ids:
                data.append(m.HOG(hog_id=row))
            paginator = PageNumberPagination()
            page = paginator.paginate_queryset(data, request)
            serializer = serializers.HOGsListSerializer(page,many=True,context={'request': request})
            return paginator.get_paginated_response(serializer.data)


    def retrieve(self, request, hog_id):
        """
               List all the levels present for a given Hog_id and by including it in the url as the query parameter, list all the member proteins.
               Any subHOGs present at each level are also listed.

               :param hog_id: an unique identifier for a hog_group
               :param level: an unique name for a level
               """
        level = self.request.query_params.get('level', None)
        if level == None:
            hogs_tab = utils.db.get_hdf5_handle().root.HogLevel.read_where('(ID==hog_id)')
            levels = []
            for row in hogs_tab:
                hog_model = m.HOG(hog_id=row[1].decode("utf-8"), level=row[2].decode("utf-8"))
                levels.append(hog_model)

            #below is the root level calculation
            members = [models.ProteinEntry(utils.db, memb) for memb in utils.db.member_of_hog_id(hog_id)]
            # get all levels for a hog_id
            fam_nr = members[0].hog_family_nr
            levels_for_fam = utils.db.hog_levels_of_fam(fam_nr)
            # take first member, get species
            species = members[0].genome
            # get lineage of the species
            lineage = species.lineage
            # indexing of levels for a hog
            if len(hog_id) > 11:
                for lvl in levels_for_fam:
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
                    for level in levels_for_fam:
                        level = level.decode("utf-8")
                        if level in lineage:
                            level_index = lineage.index(level)
                            indexed_levels.append([level, int(level_index)])
                    indexed_levels.sort(key=lambda x: x[1])
                    root_hog_level = indexed_levels[-1][0]
            data = {'hog_id': hog_id, 'root_level': root_hog_level,'levels': levels}
            serializer = serializers.HOGDetailSerializer(instance=data, context={'request': request})
            return Response(serializer.data)
        else:
            members = [models.ProteinEntry(utils.db, memb) for memb in utils.db.member_of_hog_id(hog_id)]
            fam_nr = members[0].hog_family_nr
            subhogs = utils.db.get_subhogids_at_level(fam_nr, level)
            subHOGs_2 = []
            for i in subhogs:
                # create hog model instances
                subHOGs_2.append(m.HOG(hog_id=i.decode("utf-8"), level=level))
            data = {'hog_id': hog_id, 'level': level, 'subhogs': subHOGs_2}
            serializer = serializers.HOGInfoSerializer(instance=data, context={'request': request})
            return Response(serializer.data)

    @detail_route()
    def members(self,request,hog_id=None,format=None):
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
        serializer = serializers.XRefSerializer(instance=res, many=True)
        return Response(serializer.data)

    def retrieve(self, request, entry_id, format=None):
        """
               Retrieve the cross references for a given protein

               :param entry_id: an unique identifier for a protein
               """
        entry_nr = utils.id_resolver.resolve(entry_id)
        xrefs = utils.id_mapper['XRef'].map_entry_nr(entry_nr)
        for ref in xrefs:
            ref['entry_nr'] = entry_nr
            ref['omaid'] = utils.id_mapper['OMA'].map_entry_nr(entry_nr)
        serializer = serializers.XRefSerializer(instance=xrefs, many=True)
        return Response(serializer.data)


class GenomeViewSet(ViewSet):
    lookup_field = 'genome_id'

    def list(self, request, format=None):
        """
               List of all the genomes present in the current release


               """
        make_genome = functools.partial(models.Genome, utils.db)
        genomes = [make_genome(g) for g in utils.id_mapper['OMA'].genome_table]
        serializer = serializers.GenomeInfoSerializer(instance=genomes, many=True,context={'request': request})
        return Response(serializer.data)

    def retrieve(self, request, genome_id, format=None):
        """
               Retrieve the basic information on a given genome

               :param genome_id: an unique identifier for a genome
               """
        try:
            g = models.Genome(utils.db, utils.id_mapper['OMA'].identify_genome(genome_id))
        except db.UnknownSpecies as e:
            raise NotFound(e)
        serializer = serializers.GenomeDetailSerializer(instance=g,context={'request': request})
        return Response(serializer.data)

    @detail_route()
    def proteins_list(self, request, genome_id=None):
        """
                       Retrieve the list of proteins available for a genome

                       :param genome_id: an unique identifier for a genome
                       """

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
        serializer = serializers.ProteinEntrySerializer(page, many= True, context={'request': request})
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
        different and close paralogs and homeologs in case
        they are the same.

        using the query_params 'chr1' and 'chr2', one can limit
        the relations to a certain chromosome for one or both
        genomes."""
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
                res.append(rel)
                if cnt+1 % 100 == 0:
                    logger.debug("Processed {} rows".format(cnt))
        serializer = serializers.PairwiseRelationSerializer(instance=res, many=True)
        return Response(serializer.data)
