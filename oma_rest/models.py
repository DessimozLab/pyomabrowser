import json
import uuid

from rest_framework.exceptions import APIException, status
from django.db import models
import re
import random
re_hogid = re.compile(r"HOG:(?P<rel>[A-Z]*)(?P<fam>\d+)(?P<subhog>[a-z0-9.]+)?")


class HOG(object):
    def __init__(self, hog_id=None, **kwargs):
        self.hog_id = hog_id
        for k, v in kwargs.items():
            setattr(self, k, v)
        if hog_id is not None:
            m = re_hogid.match(hog_id)
            self.roothog_id = int(m.group("fam"))


class OMAGroup(object):
    def __init__(self, GroupNr=None, fingerprint=None, members=None, **kwargs):
        self.GroupNr = GroupNr
        self.fingerprint = fingerprint
        self.members = members
        for k, v in kwargs.items():
            setattr(self, k, v)


class IdGoneException(APIException):
    status_code = status.HTTP_410_GONE
    default_detail = 'ID {outdated} is no longer valid.'
    default_code = 'id_gone'

    def __init__(self, outdated, replacements=None, detail=None, code=None):
        if detail is None:
            detail = self.default_detail.format(outdated=outdated)
        if replacements is not None:
            self.replacement_ids = replacements
        super(IdGoneException, self).__init__(detail, code)


ENRICHMENT_CHOICES=[("ancestral", "Ancestral genome Gene Ontology Enrichment Analysis"),
                    ("extant", "Extant genome Gene Ontology Enrichment Analysis")]
class EnrichmentAnalysisModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    data_hash = models.CharField(max_length=32)
    type = models.CharField(choices=ENRICHMENT_CHOICES, max_length=16)
    _foreground = models.TextField(db_column='foreground', verbose_name="List of genes / hogs that constitute the foreground set.")
    taxlevel = models.CharField(max_length=256, blank=True, verbose_name="Taxonomic level")
    state = models.CharField(max_length=8)
    result = models.FileField(blank=True)
    submit_time = models.DateTimeField(auto_now_add=True, auto_now=False)
    modified_time = models.DateTimeField(auto_now=True)
    compute_time = models.FloatField(null=True, blank=True)
    name = models.CharField(max_length=256, verbose_name="Name of the enrichment analysis", blank=True)
    message = models.TextField(blank=True)

    @property
    def foreground(self):
        return self._foreground and json.loads(self._foreground)

    @foreground.setter
    def foreground(self, data):
        self._foreground = json.dumps(data) if data else None