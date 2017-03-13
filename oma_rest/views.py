import functools
import operator

import itertools
from rest_framework.viewsets import ViewSet
from rest_framework.response import Response
from oma import utils, misc
from . import serializers
from pyoma.browser import models


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
        group = utils.db.oma_group_members(int(id))
        serializer = serializers.ProteinEntrySerializer(
            instance=(models.ProteinEntry(utils.db, memb) for memb in group),
            many=True, context={'request': request})
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


