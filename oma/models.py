# sql database models
from django.db import models


class FileResult(models.Model):
    data_hash = models.CharField(max_length=32, primary_key=True)
    state = models.CharField(max_length=8)
    result = models.FileField(blank=True)
    create_time = models.DateTimeField(auto_now=True)
    purged = models.BooleanField(default=False)


