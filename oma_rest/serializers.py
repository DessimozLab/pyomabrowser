import itertools
import collections
from hashlib import md5
import logging

from rest_framework import serializers
from oma.utils import db
from pyoma.browser.models import ProteinEntry
from django.utils.http import urlencode
from .models import EnrichmentAnalysisModel, ENRICHMENT_CHOICES

logger = logging.getLogger(__name__)

class QueryParamHyperlinkedIdentityField(serializers.HyperlinkedIdentityField):
    def __init__(self, query_params, nullvalues=None, **kwargs):
        super(QueryParamHyperlinkedIdentityField, self).__init__(**kwargs)
        self.query_params = query_params
        self.nullvalues = list(nullvalues) if nullvalues is not None else [None]

    def get_url(self, obj, view_name, request, format):
        url = super(QueryParamHyperlinkedIdentityField, self).get_url(obj, view_name, request, format)
        qparams = {}
        for param_name, key in self.query_params.items():
            try:
                param_value = getattr(obj, key)
                if param_value not in self.nullvalues:
                    qparams[param_name] = param_value
            except AttributeError:
                pass
        if len(qparams) > 0:
            url += "?" + urlencode(qparams)
        return url


class OptionalHyperlinkedIdentityField(serializers.HyperlinkedIdentityField):
    def __init__(self, nullvalues=None, **kwargs):
        super(OptionalHyperlinkedIdentityField, self).__init__(required=False, **kwargs)
        self.nullvalues = list(nullvalues)

    def get_url(self, obj, view_name, request, format):
        if getattr(obj, self.lookup_field) in self.nullvalues:
            return None
        return super(OptionalHyperlinkedIdentityField, self).get_url(obj, view_name, request, format)


class OnlyPolyploidHyperlinkedIdentifyField(serializers.HyperlinkedIdentityField):
    def __init__(self, **kwargs):
        super(OnlyPolyploidHyperlinkedIdentifyField, self).__init__(required=False, **kwargs)

    def get_url(self, obj, view_name, request, format):
        if not obj.genome.is_polyploid:
            return None
        return super(OnlyPolyploidHyperlinkedIdentifyField, self).get_url(obj, view_name, request, format)


class ReadOnlySerializer(serializers.Serializer):
    """Base class for Serializers that don't store data
    into the database and hence do not need a create/update
    method"""
    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass


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
    proteins = serializers.HyperlinkedIdentityField(view_name='genome-proteins', read_only=True,
                                                         lookup_field='uniprot_species_code',
                                                         lookup_url_kwarg='genome_id')
    chromosomes = serializers.SerializerMethodField(method_name=None)

    def get_chromosomes(self, obj):
        chrs = []
        for chr_id in obj.chromosomes:
            entries = obj.chromosomes[chr_id]
            ranges = []
            for k, g in itertools.groupby(enumerate(entries), lambda x: x[0] - x[1]):
                group = [z[1] for z in g]
                ranges.append((group[0], group[-1]))
            chrs.append({'id': chr_id, 'entry_ranges': ranges})
        return chrs


class ProteinEntrySerializer(ReadOnlySerializer):
    entry_nr = serializers.IntegerField(required=True)
    entry_url = serializers.HyperlinkedIdentityField(
        view_name='protein-detail',
        lookup_field='entry_nr',
        lookup_url_kwarg='entry_id')
    omaid = serializers.CharField()
    canonicalid = serializers.CharField()
    sequence_md5 = serializers.CharField()
    sequence_length = serializers.IntegerField()
    species = GenomeInfoSerializer(source='genome')
    oma_group = serializers.IntegerField(required=False)
    oma_hog_id = serializers.CharField(required=False, source='oma_hog')
    chromosome = serializers.CharField()
    locus = serializers.SerializerMethodField(method_name=None)
    is_main_isoform = serializers.BooleanField()

    def get_locus(self, obj):
        return collections.OrderedDict([('start', obj.locus_start), ('end', obj.locus_end), ('strand', obj.strand)])


class ProteinEntryDetailSerializer(ProteinEntrySerializer):
    roothog_id = serializers.IntegerField(source='hog_family_nr')
    hog_levels = serializers.SerializerMethodField(method_name=None)

    sequence = serializers.CharField()
    cdna = serializers.CharField()
    description = serializers.CharField()
    domains = serializers.HyperlinkedIdentityField(view_name='protein-domains', read_only=True,
                                                   lookup_field='entry_nr', lookup_url_kwarg='entry_id')
    xref = serializers.HyperlinkedIdentityField(view_name='protein-xref', read_only=True, lookup_field='entry_nr',
                                                lookup_url_kwarg='entry_id')
    orthologs = serializers.HyperlinkedIdentityField(view_name='protein-orthologs', read_only=True,
                                                     lookup_field='entry_nr', lookup_url_kwarg='entry_id')
    homoeologs = OnlyPolyploidHyperlinkedIdentifyField(view_name='protein-homoeologs',
                                                  lookup_field='entry_nr', lookup_url_kwarg='entry_id')
    gene_ontology = serializers.HyperlinkedIdentityField(view_name='protein-gene-ontology', read_only=True,
                                                    lookup_field='entry_nr', lookup_url_kwarg='entry_id')
    oma_group_url = OptionalHyperlinkedIdentityField(view_name='group-detail', lookup_field='oma_group',
                                                         lookup_url_kwarg='group_id', nullvalues=[0])
    oma_hog_members = OptionalHyperlinkedIdentityField(view_name='hog-members', lookup_field='oma_hog',
                                                           lookup_url_kwarg='hog_id', nullvalues=('', b''))
    isoforms = serializers.HyperlinkedIdentityField(view_name="protein-isoforms", read_only=True,
                                                    lookup_field="entry_nr", lookup_url_kwarg='entry_id')
    alternative_isoforms_urls = serializers.ListSerializer(
        child=serializers.HyperlinkedIdentityField(view_name='protein-detail', lookup_field='entry_nr',
                                                   lookup_url_kwarg='entry_id', read_only=True),
        source='alternative_isoforms')

    def get_hog_levels(self, obj):
        protein = ProteinEntry.from_entry_nr(db, obj.entry_nr)
        levs_of_fam = frozenset([z.decode() for z in db.hog_levels_of_fam(protein.hog_family_nr)])
        levels = []
        for lev in itertools.chain(protein.genome.lineage, ('LUCA',)):
            if lev.encode('ascii') in db.tax.all_hog_levels and lev in levs_of_fam:
                levels.append(lev)
        return levels


class XRef2ProteinDetailSerializer(ReadOnlySerializer):
    query_id = serializers.CharField()
    target = ProteinEntryDetailSerializer(required=False)


class IsoformProteinSerializer(ProteinEntrySerializer):
    locus = serializers.SerializerMethodField(method_name=None)
    nr_exons = serializers.SerializerMethodField(method_name=None)

    def get_locus(self, obj):
        return obj.exons.as_list_of_dict()

    def get_nr_exons(self, obj):
        return len(obj.exons)


class OrthologsListSerializer(ProteinEntrySerializer):
    rel_type = serializers.CharField()
    distance = serializers.FloatField()
    score = serializers.FloatField()


class ApproxSearchProteinSerializer(ProteinEntryDetailSerializer):
    alignment_score = serializers.FloatField(required=False)
    alignment = serializers.ListSerializer(child=serializers.CharField(), required=False)


class SequenceSearchResultSerializer(ReadOnlySerializer):
    query = serializers.CharField()
    identified_by = serializers.CharField()
    targets = serializers.ListSerializer(child=ApproxSearchProteinSerializer())


class ChromosomeInfoSerializer(ReadOnlySerializer):
    id = serializers.CharField()
    entry_ranges = serializers.ListSerializer(
        child=serializers.ListSerializer(child=serializers.IntegerField()))


class OmaGroupSerializer(ReadOnlySerializer):
    group_nr = serializers.IntegerField(source='GroupNr')
    fingerprint = serializers.CharField()
    description = serializers.CharField()
    related_groups = serializers.HyperlinkedIdentityField(
        view_name='group-close-groups',
        lookup_field='GroupNr',
        lookup_url_kwarg='group_id')
    members = serializers.ListSerializer(child=ProteinEntrySerializer())


class XRefSerializer(ReadOnlySerializer):
    xref = serializers.CharField()
    source = serializers.CharField()
    seq_match = serializers.CharField()
    entry_nr = serializers.IntegerField()
    omaid = serializers.CharField()
    genome = GenomeInfoSerializer(required=False)



class BaseGeneOntologySerializer(ReadOnlySerializer):
    id = serializers.SerializerMethodField(method_name=None)
    GO_term = serializers.SerializerMethodField(method_name=None)
    name = serializers.SerializerMethodField(method_name=None)
    aspect = serializers.SerializerMethodField(method_name=None)

    def get_id(self, obj):
        return str(obj.object_id)

    def get_GO_term(self, obj):
        return str(obj.term)

    def get_name(self, obj):
        return obj.term.name

    def get_aspect(self, obj):
        return obj.aspect

class GeneOntologySerializer(BaseGeneOntologySerializer):
    entry_nr = serializers.IntegerField()
    evidence = serializers.CharField()
    reference = serializers.CharField()

class AncestralGeneOntologySerializer(BaseGeneOntologySerializer):
    #stars = serializers.SerializerMethodField(method_name=None)
    score = serializers.SerializerMethodField(method_name=None)

    def get_id(self, obj):
        return str(obj.anno['HogID'].decode())

    def get_score(self, obj):
        return float(obj.anno['RawScore'])

    #def get_stars(self, obj):
    #    return int(obj.anno['Score'])


class GroupListSerializer(ReadOnlySerializer):
    oma_group = serializers.IntegerField(source='GroupNr')
    group_url = serializers.HyperlinkedIdentityField(
        view_name='group-detail',
        lookup_field='GroupNr',
        lookup_url_kwarg='group_id')


class RelatedGroupsSerializer(GroupListSerializer):
    hits = serializers.IntegerField()


class HOGsBaseSerializer(ReadOnlySerializer):
    hog_id = serializers.CharField()
    level = serializers.CharField(required=False)
    levels_url = QueryParamHyperlinkedIdentityField(view_name='hog-detail',
                                                    lookup_field='hog_id',
                                                    query_params={'level': 'level'})
    members_url = QueryParamHyperlinkedIdentityField(view_name='hog-members',
                                                     query_params={'level': 'level'},
                                                     lookup_field='hog_id')
    alternative_levels = serializers.ListSerializer(required=False,
                                                    child=serializers.CharField())


class HOGsListSerializer(HOGsBaseSerializer):
    roothog_id = serializers.IntegerField()
    completeness_score = serializers.FloatField(required=False)
    description = serializers.SerializerMethodField(method_name=None)
    similar_profile_hogs = serializers.HyperlinkedIdentityField(
        view_name="hog-similar-profile-hogs",
        lookup_field="roothog_id",
        lookup_url_kwarg="hog_id")

    def get_description(self, obj):
        return db.get_roothog_keywords(obj.roothog_id)


class HOGsCompareListSerializer(HOGsListSerializer):
    event = serializers.CharField()


class HOGsLevelDetailSerializer(HOGsListSerializer):
    parent_hogs = serializers.ListSerializer(child=HOGsBaseSerializer())
    children_hogs = serializers.ListSerializer(child=HOGsBaseSerializer())


class HOGMembersListSerializer(ReadOnlySerializer):
    hog_id = serializers.CharField()
    level = serializers.CharField()
    members = serializers.ListSerializer(child=ProteinEntrySerializer())


class HOGandPatternSerializer(HOGsBaseSerializer):
    in_species = serializers.ListSerializer(child=serializers.CharField())


class HOGsSimilarProfileSerializer(HOGsListSerializer):
    in_species = serializers.ListSerializer(child=serializers.CharField())
    similar_profile_hogs = serializers.ListSerializer(child=HOGandPatternSerializer())


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
    taxon_id = serializers.IntegerField()


class TaxonomyNewickSerializer(ReadOnlySerializer):
    root_taxon = TaxonSerializer()
    newick = serializers.CharField()


class EnrichmentAnalysisInputSerializer(serializers.ModelSerializer):
    status_url = serializers.HyperlinkedIdentityField('enrichment-status', lookup_field='id')
    foreground = serializers.JSONField()

    class Meta:
        model = EnrichmentAnalysisModel
        fields = ['id', 'data_hash', 'type', 'foreground', 'taxlevel', 'name', 'status_url']
        read_only_fields = ['id', 'data_hash', 'state']

    def validate_taxlevel(self, value):
        logger.debug(f"validate {value}, in {db.tax.all_hog_levels}")
        if value and not value.encode('utf-8') in db.tax.all_hog_levels:
            raise serializers.ValidationError("Invalid / unknown taxlevel value")
        return value

    def validate_type(self, value):
        if not value in [x[0] for x in ENRICHMENT_CHOICES]:
            raise serializers.ValidationError(f"Invalid type. Must be one of {[x[0] for x in ENRICHMENT_CHOICES]}")
        return value

    def validate_foreground(self, value):
        if not isinstance(value, list) or len(value) < 1:
            raise serializers.ValidationError("foreground should be a json encoded list of proteins / hogs")
        if any((not isinstance(z, str) for z in value)):
            raise serializers.ValidationError("foreground should be a json encoded list of proteins / hogs")
        return value

    def validate(self, data):
        contains_ancestral = any(x.startswith('HOG:') for x in data['foreground'])
        if contains_ancestral and data['type'] != 'ancestral':
            raise serializers.ValidationError("HOGs can only be used for ancestral enrichment analysis")
        if data['type'] == 'ancestral' and data['taxlevel'] is None:
            raise serializers.ValidationError("taxlevel must be specified for ancestral enrichment analysis")

        if data['type'] == 'extant':
            data['taxlevel'] = ""

        data['data_hash'] = self.get_data_hash(data)
        return data

    def get_data_hash(self, data):
        h = md5()
        if 'taxlevel' in data:
            h.update(data['taxlevel'].encode('utf-8'))
        for elem in sorted(data['foreground']):
            h.update(elem.encode('utf-8'))
        return h.hexdigest()


class EnrichmentAnalysisStatusSerializer(serializers.ModelSerializer, ReadOnlySerializer):
    class Meta:
        model = EnrichmentAnalysisModel
        fields = ['id', 'data_hash', 'type', 'foreground', 'name', 'state', 'message', 'result', 'result_json']
        read_only_fields = ['id', 'data_hash', 'state']
