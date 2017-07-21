from itertools import groupby
from operator import itemgetter

from rest_framework import serializers
from oma.utils import db
from pyoma.browser.models import ProteinEntry, Genome
from pyoma.browser.db import XrefIdMapper
from django.utils.http import urlencode

class QueryParamHyperlinkedIdentiyField(serializers.HyperlinkedIdentityField):
    def __init__(self, query_params, **kwargs):
        super(QueryParamHyperlinkedIdentiyField, self).__init__(**kwargs)
        self.query_params = query_params

    def get_url(self, obj, view_name, request, format):
        url = super(QueryParamHyperlinkedIdentiyField, self).get_url(obj, view_name, request, format)
        if len(self.query_params) > 0:
            url += "?"+urlencode({k: getattr(obj, v) for k,v in self.query_params.items()})
        return url


class ProteinEntrySerializer(serializers.Serializer):
    entry_nr = serializers.IntegerField(required=True)
    omaid = serializers.CharField()
    canonicalid = serializers.CharField()
    oma_group = serializers.IntegerField()
    roothog_id = serializers.IntegerField(source='hog_family_nr')
    oma_hog_id = serializers.CharField(source ='oma_hog')
    hog_levels = serializers.SerializerMethodField(method_name = None)
    sequence_length = serializers.IntegerField()
    sequence_md5 = serializers.CharField()
    chromosome = serializers.CharField()
    locus = serializers.SerializerMethodField(method_name=None)

    def create(self, validated_data):
        return ProteinEntry.from_entry_nr(db, validated_data['entry_nr'])

    def update(self, instance, validated_data):
        return instance

    def get_locus(self, obj):
        return [obj.locus_start, obj.locus_end, obj.strand]

    def get_hog_levels(self,obj):
        levels = db.hog_levels_of_fam(obj.hog_family_nr)
        protein_levels = []
        for level in levels:
            level = level.decode("utf-8")
            members_at_level = [ProteinEntry(db, memb) for memb in db.member_of_hog_id(obj.oma_hog, level)]
            for member in members_at_level:
                if str(member) == str(obj):
                    protein_levels.append(level)
                else:
                    pass
        return list(set(protein_levels))

class ProteinEntryDetailSerializer(ProteinEntrySerializer):
    sequence = serializers.CharField()
    cdna = serializers.CharField()
    domains = serializers.HyperlinkedIdentityField(view_name='protein-domains', read_only=True,
                                                   lookup_field='entry_nr', lookup_url_kwarg='entry_id')
    xref = serializers.HyperlinkedIdentityField(view_name='protein-xref', read_only=True, lookup_field='entry_nr', lookup_url_kwarg='entry_id')
    orthologs = serializers.HyperlinkedIdentityField(view_name = 'protein-orthologs', read_only = True, lookup_field='entry_nr', lookup_url_kwarg='entry_id')
    ontology = serializers.HyperlinkedIdentityField(view_name='protein-ontology', read_only = True, lookup_field = 'entry_nr', lookup_url_kwarg= 'entry_id')

class OrthologsListSerializer(serializers.Serializer):
    ortholog = ProteinEntrySerializer()
    RelType = serializers.CharField()
    Distance = serializers.FloatField()
    Score = serializers.FloatField()

class HOGserializer(serializers.Serializer):
    hog_id = serializers.CharField()
    level = serializers.CharField()
    members = serializers.ListSerializer(child=ProteinEntrySerializer())

class RootHOGserializer(serializers.Serializer):
    hog_id = serializers.CharField()
    root_level = serializers.CharField()
    members = serializers.ListSerializer(child=ProteinEntrySerializer())

class ChromosomeInfoSerializer(serializers.Serializer):
    id = serializers.CharField()
    entry_ranges = serializers.ListSerializer(
        child=serializers.ListSerializer(child=serializers.IntegerField()))

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass


class GenomeInfoSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=5, source='uniprot_species_code')
    taxon_id = serializers.IntegerField(source='ncbi_taxon_id')
    species = serializers.CharField(source='sciname')
    common = serializers.CharField(required=False)


    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass


class GenomeDetailSerializer(GenomeInfoSerializer):
    nr_entries = serializers.IntegerField()
    lineage = serializers.ListSerializer(child=serializers.CharField())
    proteins = serializers.HyperlinkedIdentityField(view_name='genome-proteins-list', read_only=True,
                                                    lookup_field='uniprot_species_code',
                                                    lookup_url_kwarg='genome_id')
    chromosomes = serializers.SerializerMethodField(method_name=None)

    def get_chromosomes(self, obj):
        chrs = []
        for chr_id in obj.chromosomes:
            entries = obj.chromosomes[chr_id]
            ranges = []
            for k, g in groupby(enumerate(entries), lambda x: x[0] - x[1]):
                group = [z[1] for z in g]
                ranges.append((group[0], group[-1]))
            chrs.append({'id': chr_id, 'entry_ranges': ranges})
        return chrs

class RelatedGroupsSerializer(serializers.Serializer):
    GroupNr = serializers.SerializerMethodField(method_name = None)
    Hits = serializers.SerializerMethodField(method_name=None)

    def get_GroupNr(self, obj):
        return (obj[0])

    def get_Hits(self,obj):
        return (obj[1])

class OmaGroupSerializer(serializers.Serializer):
    GroupNr = serializers.IntegerField()
    fingerprint = serializers.CharField()
    members = serializers.ListSerializer(child=ProteinEntrySerializer())


class CloseGroupsSerializer(serializers.Serializer):
    related_groups = serializers.ListSerializer(child = RelatedGroupsSerializer())

class XRefSerializer(serializers.Serializer):
    xref = serializers.CharField()
    source = serializers.CharField()
    entry_nr = serializers.IntegerField()
    omaid = serializers.CharField()
    genome = GenomeInfoSerializer(required=False)

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass

class GeneOntologySerializer(serializers.Serializer):
    entry_nr = serializers.IntegerField()
    GO_term = serializers.SerializerMethodField(method_name=None)
    name = serializers.SerializerMethodField(method_name=None)
    evidence = serializers.CharField()
    reference = serializers.CharField()

    def get_GO_term(self,obj):
        return str(obj.term)

    def get_name(self,obj):
        return obj.term.name

class HOGsLevelsListSerializer(serializers.Serializer):
    level = serializers.CharField()
    level_url = serializers.HyperlinkedIdentityField(view_name = 'hogslevels-detail', read_only=True, lookup_field='level')

class HOGsLevelSerializer(serializers.Serializer):
    level = serializers.CharField()
    subHOGs = serializers.ListSerializer(child=QueryParamHyperlinkedIdentiyField(view_name='hogs-detail',
                                                                                 lookup_field='hog_id',
                                                                                 query_params={'level': 'level'}))

class HOGsDetailSerializer(serializers.Serializer):
    hog_id = serializers.CharField()
    levels = serializers.ListSerializer(child = HOGsLevelSerializer())


class HOGsListSerializer(serializers.Serializer):
    roothog_id = serializers.CharField()
    hog_id_url = serializers.HyperlinkedIdentityField(view_name='hogs-detail', read_only=True, lookup_field='hog_id')

class HOGsListSerializer_at_level(serializers.Serializer):
    roothog_id = serializers.CharField()
    hog_id_url = QueryParamHyperlinkedIdentiyField(view_name='hogs-detail', lookup_field='hog_id', query_params={'level': 'level'})

class DomainSerializer(serializers.Serializer):
    source = serializers.CharField()
    domainid = serializers.CharField()
    name = serializers.CharField()
    location = serializers.CharField()

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass


class ProteinDomainsSerializer(serializers.Serializer):
    seq_id = serializers.CharField(max_length=32)
    length = serializers.IntegerField()
    regions = DomainSerializer(many=True)

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass


class PairwiseRelationSerializer(serializers.Serializer):
    entry_1 = ProteinEntrySerializer()
    entry_2 = ProteinEntrySerializer()
    rel_type = serializers.CharField()
    distance = serializers.FloatField()
    score = serializers.FloatField()

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass
