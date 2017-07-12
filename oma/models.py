# sql database models
from django.db import models
from django.utils import timezone


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

class HOGroup(models.Model):
    hog_id = models.CharField(max_length=32)
    size = models.IntegerField()

