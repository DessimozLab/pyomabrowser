from itertools import groupby
from operator import itemgetter

from rest_framework import serializers
from oma.utils import db
from pyoma.browser.models import ProteinEntry, Genome
from pyoma.browser.db import XrefIdMapper
from django.utils.http import urlencode


class QueryParamHyperlinkedIdentityField(serializers.HyperlinkedIdentityField):
    def __init__(self, query_params, **kwargs):
        super(QueryParamHyperlinkedIdentityField, self).__init__(**kwargs)
        self.query_params = query_params

    def get_url(self, obj, view_name, request, format):
        url = super(QueryParamHyperlinkedIdentityField, self).get_url(obj, view_name, request, format)
        if len(self.query_params) > 0:
            url += "?" + urlencode({k: getattr(obj, v) for k, v in self.query_params.items()})
        return url


class ReadOnlySerializer(serializers.Serializer):
    """Base class for Serializers that don't store data
    into the database and hence do not need a create/update
    method"""
    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass


class ProteinEntrySerializer(ReadOnlySerializer):
    entry_nr = serializers.IntegerField(required=True)
    entry_url = serializers.HyperlinkedIdentityField(
        view_name='protein-detail',
        lookup_field='entry_nr',
        lookup_url_kwarg='entry_id')
    omaid = serializers.CharField()
    canonicalid = serializers.CharField()
    sequence_md5 = serializers.CharField()


class ProteinEntryDetailSerializer(ReadOnlySerializer):
    entry_nr = serializers.IntegerField(required=True)
    omaid = serializers.CharField()
    canonicalid = serializers.CharField()
    sequence_md5 = serializers.CharField()
    oma_group = serializers.IntegerField()
    roothog_id = serializers.IntegerField(source='hog_family_nr')
    oma_hog_id = serializers.CharField(source='oma_hog')
    hog_levels = serializers.SerializerMethodField(method_name=None)
    chromosome = serializers.CharField()
    locus = serializers.SerializerMethodField(method_name=None)
    sequence_length = serializers.IntegerField()
    sequence = serializers.CharField()
    cdna = serializers.CharField()
    domains = serializers.HyperlinkedIdentityField(view_name='protein-domains', read_only=True,
                                                   lookup_field='entry_nr', lookup_url_kwarg='entry_id')
    xref = serializers.HyperlinkedIdentityField(view_name='protein-xref', read_only=True, lookup_field='entry_nr',
                                                lookup_url_kwarg='entry_id')

    orthologs = serializers.HyperlinkedIdentityField(view_name='protein-orthologs', read_only=True,
                                                     lookup_field='entry_nr', lookup_url_kwarg='entry_id')
    ontology = serializers.HyperlinkedIdentityField(view_name='protein-ontology', read_only=True,
                                                    lookup_field='entry_nr', lookup_url_kwarg='entry_id')

    def get_locus(self, obj):
        return [obj.locus_start, obj.locus_end, obj.strand]

    def get_hog_levels(self, obj):
        protein = ProteinEntry.from_entry_nr(db, obj.entry_nr)
        levels = db.hog_levels_of_fam(protein.hog_family_nr)
        protein_levels = []
        for level in levels:
            level = level.decode("utf-8")
            members_at_level = [ProteinEntry(db, memb) for memb in
                                db.member_of_hog_id(protein.oma_hog, level)]
            for member in members_at_level:
                if str(member) == str(protein) and level not in protein_levels:
                    protein_levels.append(level)
        return protein_levels


class OrthologsListSerializer(ProteinEntrySerializer):
    rel_type = serializers.CharField()
    distance = serializers.FloatField()
    score = serializers.FloatField()


class SubHOGSerializer(ReadOnlySerializer):
    hog_id = serializers.CharField()
    members_url = QueryParamHyperlinkedIdentityField(
        view_name='hog-members',
        lookup_field='hog_id',
        query_params={'level': 'level'})


class HOGInfoSerializer(ReadOnlySerializer):
    hog_id = serializers.CharField()
    level = serializers.CharField()
    subhogs = serializers.ListSerializer(child=SubHOGSerializer())


class HOGMembersListSerializer(ReadOnlySerializer):
    hog_id = serializers.CharField()
    level = serializers.CharField()
    members = serializers.ListSerializer(child=ProteinEntrySerializer())


class RootHOGserializer(ReadOnlySerializer):
    hog_id = serializers.CharField()
    root_level = serializers.CharField()
    members = serializers.ListSerializer(child=ProteinEntrySerializer())


class ChromosomeInfoSerializer(ReadOnlySerializer):
    id = serializers.CharField()
    entry_ranges = serializers.ListSerializer(
        child=serializers.ListSerializer(child=serializers.IntegerField()))


class GenomeBaseSerializer(ReadOnlySerializer):
    code = serializers.CharField(max_length=5, source='uniprot_species_code')
    taxon_id = serializers.IntegerField(source='ncbi_taxon_id')
    species = serializers.CharField(source='sciname')
    common = serializers.CharField(required=False)


class GenomeInfoSerializer(GenomeBaseSerializer):
    genome_url = serializers.HyperlinkedIdentityField(
        view_name='genome-detail',
        lookup_field='uniprot_species_code',
        lookup_url_kwarg='genome_id')


class GenomeDetailSerializer(GenomeBaseSerializer):
    nr_entries = serializers.IntegerField()
    lineage = serializers.ListSerializer(child=serializers.CharField())
    proteins_list = serializers.HyperlinkedIdentityField(view_name='genome-proteins-list', read_only=True,
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


class OmaGroupSerializer(ReadOnlySerializer):
    group_nr = serializers.IntegerField(source='GroupNr')
    fingerprint = serializers.CharField()
    related_groups = serializers.HyperlinkedIdentityField(
        view_name='group-close-groups',
        lookup_field='GroupNr',
        lookup_url_kwarg='group_id')
    members = serializers.ListSerializer(child=ProteinEntrySerializer())


class XRefSerializer(ReadOnlySerializer):
    xref = serializers.CharField()
    source = serializers.CharField()
    entry_nr = serializers.IntegerField()
    omaid = serializers.CharField()
    genome = GenomeInfoSerializer(required=False)


class GeneOntologySerializer(ReadOnlySerializer):
    entry_nr = serializers.IntegerField()
    GO_term = serializers.SerializerMethodField(method_name=None)
    name = serializers.SerializerMethodField(method_name=None)
    aspect = serializers.SerializerMethodField(method_name=None)
    evidence = serializers.CharField()
    reference = serializers.CharField()

    def get_GO_term(self, obj):
        return str(obj.term)

    def get_name(self, obj):
        return obj.term.name

    def get_aspect(self, obj):
        return obj.aspect


class HOGsLevelSerializer(ReadOnlySerializer):
    level = serializers.CharField()
    level_url = QueryParamHyperlinkedIdentityField(view_name='hog-detail', lookup_field='hog_id',
                                                   query_params={'level': 'level'})


class ProteinHOGSerializer(ReadOnlySerializer):
    hog_id = serializers.CharField()
    levels = serializers.ListSerializer(child=HOGsLevelSerializer())


class HOGDetailSerializer(ProteinHOGSerializer):
    root_level = serializers.CharField()


class GroupListSerializer(ReadOnlySerializer):
    oma_group = serializers.IntegerField(source='GroupNr')
    group_url = serializers.HyperlinkedIdentityField(
        view_name='group-detail',
        lookup_field='GroupNr',
        lookup_url_kwarg='group_id')


class RelatedGroupsSerializer(GroupListSerializer):
    hits = serializers.IntegerField()


# the below 2 HOGS serializers are to do with the list of hogs found at api/hogs/
class HOGsListSerializer(ReadOnlySerializer):
    roothog_id = serializers.CharField()
    hog_id = serializers.CharField()
    hog_id_url = serializers.HyperlinkedIdentityField(view_name='hog-detail', read_only=True, lookup_field='hog_id')


# api/hogs/?level
class HOGsListSerializer_at_level(ReadOnlySerializer):
    roothog_id = serializers.CharField()
    hog_id = serializers.CharField()
    hog_id_url = QueryParamHyperlinkedIdentityField(view_name='hog-detail', lookup_field='hog_id',
                                                    query_params={'level': 'level'})


class DomainSerializer(ReadOnlySerializer):
    source = serializers.CharField()
    domainid = serializers.CharField()
    name = serializers.CharField()
    location = serializers.CharField()


class ProteinDomainsSerializer(ReadOnlySerializer):
    seq_id = serializers.CharField(max_length=32)
    length = serializers.IntegerField()
    regions = DomainSerializer(many=True)


class PairwiseRelationSerializer(ReadOnlySerializer):
    entry_1 = ProteinEntrySerializer()
    entry_2 = ProteinEntrySerializer()
    rel_type = serializers.CharField()
    distance = serializers.FloatField()
    score = serializers.FloatField()


class TaxonSerializer(ReadOnlySerializer):
    name = serializers.CharField()
    taxon_id = serializers.CharField()


class TaxonomyNewickSerializer(ReadOnlySerializer):
    root_taxon = TaxonSerializer()
    newick = serializers.CharField()
