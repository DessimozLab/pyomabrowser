from rest_framework import serializers
from oma.utils import db
from pyoma.browser.models import ProteinEntry, Genome


class ProteinEntrySerializer(serializers.Serializer):
    entry_nr = serializers.IntegerField(required=True)
    omaid = serializers.CharField()
    canonicalid = serializers.CharField()
    oma_group = serializers.IntegerField()
    roothog_id = serializers.IntegerField(source='hog_family_nr')
    oma_hog = serializers.CharField()
    sequence_length = serializers.IntegerField()
    sequence_md5 = serializers.CharField()

    def create(self, validated_data):
        return ProteinEntry.from_entry_nr(db, validated_data['entry_nr'])

    def update(self, instance, validated_data):
        return instance


class ProteinEntryDetailSerializer(ProteinEntrySerializer):
    sequence = serializers.CharField()
    cdna = serializers.CharField()
    domains = serializers.HyperlinkedIdentityField(view_name='domain-detail', read_only=True,
                                                   lookup_field='entry_nr', lookup_url_kwarg='entry_id')


class DomainSerializer(serializers.Serializer):
    source = serializers.CharField(max_length=30)
    domainid = serializers.CharField(max_length=20)
    name = serializers.CharField(max_length=255)
    location = serializers.CharField(max_length=255)

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
