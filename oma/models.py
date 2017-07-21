# sql database models
from django.db import models
from django.utils import timezone
import re


class FileResult(models.Model):
    data_hash = models.CharField(max_length=32, primary_key=True)
    result_type = models.CharField(max_length=16)
    state = models.CharField(max_length=8)
    result = models.FileField(blank=True)
    create_time = models.DateTimeField(auto_now=True)
    purged = models.BooleanField(default=False)

    def remove_erroneous_or_long_pending(self):
        if self.state == "error" or (self.state == "pending" and
                (timezone.now() - self.create_time).total_seconds() > 300):
            self.delete()
            return True
        return False

class HOG(object):
    def __init__(self, hog_id=None, level=None):
        self.hog_id = hog_id
        self.level = level
        if hog_id is not None:
            start = hog_id.find(':') + 1
            end = hog_id.find('.')
            if end >= 0:
                self.roothog_id = int(hog_id[start:end])
            else:
                self.roothog_id = int(hog_id[start:])

class OMAGroup(object):
    def __init__(self, GroupNr=None, fingerprint=None, members=None):
        self.GroupNr = GroupNr
        self.fingerprint = fingerprint
        self.members = members
