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


logger = logging.getLogger(__name__)


# Create your views here.
class ProteinEntryViewSet(ViewSet):
    serializer_class = serializers.ProteinEntryDetailSerializer
    lookup_field = 'entry_id'

    def retrieve(self, request, entry_id=None, format=None):
        """Retrieve the basic information on a protein

        :param entry_id: an unique identifier for a protein"""
        # Load the entry and its domains, before forming the JSON to draw client-side.
        entry_nr = utils.id_resolver.resolve(entry_id)
        serializer = serializers.ProteinEntryDetailSerializer(
            instance=models.ProteinEntry.from_entry_nr(utils.db, entry_nr),
            context={'request': request})
        return Response(serializer.data)


class ProteinDomains(ViewSet):
    lookup_field='entry_id'

    def retrieve(self, request, entry_id=None, format=None):
        """retrieve the domains of a protein if available

        :param entry_id: a unique identifier for the protein"""
        entry_nr = utils.id_resolver.resolve(entry_id)
        entry = utils.db.entry_by_entry_nr(entry_nr)
        domains = utils.db.get_domains(entry['EntryNr'])
        response = misc.encode_domains_to_dict(entry, domains, utils.domain_source)
        #serializer = serializer.
        return Response(response)


class OmaGroupViewSet(ViewSet):
    lookup_field = 'id'
    serializer_class = serializers.ProteinEntrySerializer

    def retrieve(self, request, id=None, format=None):
        #fingerprint = utils.db.get_hdf5_handle().root.OmaGroups.MetaData.read_where('GroupNr'==id, field='Fingerprint').decode("utf-8")
        data = {'members': [models.ProteinEntry(utils.db, memb) for memb in utils.db.oma_group_members(int(id))],
                'FingerPrint': '',
                'GroupNr': int(id)}
        serializer = serializers.OmaGroupSerializer(
            instance=data, context={'request': request})
        return Response(serializer.data)

class HOGsViewSet(ViewSet):
    lookup_field = 'hog_id'
    serializer_class = serializers.ProteinEntrySerializer

    def retrieve(self, request, hog_id):
        level = self.request.query_params.get('level', None)
        members = db.Database.member_of_hog_id(utils.db,hog_id = 'hog_id',level='level')
        serializer = serializers.ProteinEntrySerializer(instance = [models.ProteinEntry(utils.db, memb) for memb in members], many=True)
        return Response(serializer.data)


class ProteinsViewSet(ViewSet):
    lookup_field = 'genome_id'

    def retrieve(self, request, genome_id= None, format=None):
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


class OrthologsViewSet (ViewSet):
    serializer_class = serializers.ProteinEntrySerializer
    lookup_field = 'entry_id'

    def retrieve(self, request, entry_id = None, format = None):
        data = utils.db.get_vpairs(int(entry_id))
        content = []
        for row in data:
            entry_nr = row[1]
            ortholog = models.ProteinEntry.from_entry_nr(utils.db, int(entry_nr))
            content.append({'ortholog': ortholog, 'RelType': row[4] , 'Distance': row[3], 'Score': row[2] })
        serializer = serializers.OrthologuesListSerializer(instance = content, many=True)
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
        make_genome = functools.partial(models.Genome, utils.db)
        genomes = [make_genome(g) for g in utils.id_mapper['OMA'].genome_table]
        serializer = serializers.GenomeInfoSerializer(instance=genomes, many=True)
        return Response(serializer.data)

    def retrieve(self, request, genome_id, format=None):
        try:
            g = models.Genome(utils.db, utils.id_mapper['OMA'].identify_genome(genome_id))
        except db.UnknownSpecies as e:
            raise NotFound(e)
        serializer = serializers.GenomeDetailSerializer(instance=g,context={'request': request})
        return Response(serializer.data)


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