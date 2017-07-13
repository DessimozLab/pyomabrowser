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
from rest_framework.decorators import detail_route, list_route
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


class ProteinDomains(ViewSet):
    lookup_field='entry_id'

    def retrieve(self, request, entry_id=None, format=None):
        """

        Retrieve all the domains of a protein if available

        :param entry_id: a unique identifier for the protein

        """
        entry_nr = utils.id_resolver.resolve(entry_id)
        entry = utils.db.entry_by_entry_nr(entry_nr)
        domains = utils.db.get_domains(entry['EntryNr'])
        response = misc.encode_domains_to_dict(entry, domains, utils.domain_source)
        return Response(response)


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
        content = []
        for m in members:
            #get all the verified pairs
            vpairs = utils.db.get_vpairs(m.entry_nr)
            # vpairs into instances of the ProteinEntry model
            for row in vpairs:
                entry_nr = row[1]
                ortholog = models.ProteinEntry.from_entry_nr(utils.db, int(entry_nr))
                content.append(ortholog)
        groups = []
        #extract groups for vpairs but ignore vpairs with the same oma_group as the query id
        for row in content:
            if row.oma_group == int(id):
                pass
            else:
                groups.append(row.oma_group)
        #count the groups' hits and return in form of a list instead of a dictionary
        r_groups = Counter(groups).most_common()

        fingerprint = data['fingerprint']
        data['members'] = members
        data['GroupNr'] = id
        data['fingerprint'] = fingerprint
        data['related_groups'] = sorted(r_groups)
        serializer = serializers.OmaGroupSerializer(
            instance=data, context={'request': request})
        return Response(serializer.data)

class HOGLevelsListViewSet(ViewSet):
    lookup_field = 'level'
    serializer_class = serializers.HOGsLevelsListSerializer

    def list(self,request, format=None):
        """
            List of all the levels for currently identified HOGs.
            By passing a level parameter into the url, all the hogs present at that level are listed

           """

        hog_tab = utils.db.get_hdf5_handle().root.HogLevel
        levels = hog_tab.col('Level')
        levels = set(levels)
        data = []
        for level in levels:
            data.append({'level': level.decode("utf-8")})
        serializer = serializers.HOGsLevelsListSerializer(instance = data, many = True, context={'request': request})
        return Response(serializer.data)

    def retrieve(self,request, level):
        """
                    List of all the hogs with the relevant level.

                   """
        hog_tab = utils.db.get_hdf5_handle().root.HogLevel.read_where('(Level==level)')
        hogs = []
        for row in hog_tab:
            hogs.append(row[1].decode("utf-8"))
        hog_ids = sorted(set(hogs))
        hog_ids = [elem[:11] for elem in hog_ids]
        data = []
        for row in hog_ids:
            members = [models.ProteinEntry(utils.db, memb) for memb in utils.db.member_of_hog_id(row)]
            fam_nr = members[0].hog_family_nr
            data.append(m.HOGroup(roothog_id=fam_nr, hog_id=row))
        data = list(set(data))
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(data, request)
        serializer = serializers.HOGsListSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)



class HOGsViewSet(ViewSet):
    lookup_field = 'hog_id'
    serializer_class = serializers.ProteinEntrySerializer

    def list(self, request, format = None):
        """
               List of all the roothog_id's HOGs currently identified and the url to access their details


               """
        hog_tab = utils.db.get_hdf5_handle().root.HogLevel
        hogs = []
        for row in hog_tab:
            hogs.append(row[1].decode("utf-8"))
        hog_ids = sorted(set(hogs))
        data=[]
        for row in hog_ids:
            members = [models.ProteinEntry(utils.db, memb) for memb in utils.db.member_of_hog_id(row)]
            fam_nr = members[0].hog_family_nr
            data.append(m.HOGroup(roothog_id=fam_nr, hog_id=row))
        data = list(set(data))
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
        if level != None:
            members = utils.db.member_of_hog_id(hog_id, level)
            data = {'hog_id': hog_id, 'level': level, 'members': [models.ProteinEntry(utils.db, memb) for memb in members] }
            serializer = serializers.HOGserializer(instance = data, context={'request': request})
            return Response(serializer.data)
        else:
            #fastest way to get from hog_id to fam_nr is through the members
            members = [models.ProteinEntry(utils.db, memb) for memb in utils.db.member_of_hog_id(hog_id)]
            fam_nr = members[0].hog_family_nr
            levels = utils.db.hog_levels_of_fam(fam_nr)
            levels_2 = []
            for row in levels:
                subHOGs = utils.db.get_subhogids_at_level(fam_nr,row)
                subHOGs_2 = []
                for i in subHOGs:
                    if i.decode("utf-8") == hog_id:
                        pass
                    else:
                        subHOGs_2.append(i.decode("utf-8"))
                levels_2.append({'level': row.decode("utf-8"), 'subHOGs': subHOGs_2})
            data = {'hog_id': hog_id, 'levels' : levels_2}
            serializer = serializers.HOGsDetailSerializer(instance = data)
            return Response(serializer.data)



class OrthologsViewSet (ViewSet):
    serializer_class = serializers.ProteinEntrySerializer
    lookup_field = 'entry_id'

    def retrieve(self, request, entry_id = None, format = None):
        """
               Retrieve the orthologs for a protein entry

               :param entry_id: an unique identifier for a protein
               """
        data = utils.db.get_vpairs(int(entry_id))
        content = []
        for row in data:
            entry_nr = row[1]
            ortholog = models.ProteinEntry.from_entry_nr(utils.db, int(entry_nr))
            content.append({'ortholog': ortholog, 'RelType': row[4] , 'Distance': row[3], 'Score': row[2] })
        serializer = serializers.OrthologsListSerializer(instance = content, many=True)
        return Response(serializer.data)

class GeneOntologyViewSet (ViewSet):
    serializer_class = serializers.GeneOntologySerializer
    lookup_field = 'entry_id'

    def retrieve(self, request, entry_id = None, format= None):
        """
               Retrieve the available ontology data on a protein

               :param entry_id: an unique identifier for a protein
               """
        data = db.Database.get_gene_ontology_annotations(utils.db, int(entry_id))
        ontologies = [models.GeneOntologyAnnotation(utils.db, m) for m in data]
        serializer = serializers.GeneOntologySerializer(instance = ontologies, many = True)
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
               Retrieve the cross rederencing for a given protein

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
        serializer = serializers.GenomeInfoSerializer(instance=genomes, many=True)
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

    def get(self, request, genome_id1, genome_id2):
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