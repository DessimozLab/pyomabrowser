from django.db import models
from django.dispatch import receiver
from django.utils import timezone
import os
import logging
logger = logging.getLogger(__name__)


# Create your models here.
class StandaloneExportJobs(models.Model):
    data_hash = models.CharField(max_length=32, primary_key=True)
    state = models.CharField(max_length=8)
    genomes = models.TextField(null=True)
    result = models.FileField(blank=True)
    create_time = models.DateTimeField(auto_now=True)
    processing = models.BooleanField(False)
    email = models.EmailField(blank=True)
    name = models.CharField(max_length=64, blank=True)

    def remove_erroneous_or_long_pending(self):
        PENDING_TIMEOUT = 600
        ERROR_TIMEOUT = 300
        age = (timezone.now() - self.create_time).total_seconds()
        if (self.state == "error" and age > ERROR_TIMEOUT) or \
           (self.state == "pending" and age > PENDING_TIMEOUT):
            logger.info('removing invalid file result: {}'.format(self))
            self.delete()
            return True
        return False


@receiver(models.signals.post_delete, sender=StandaloneExportJobs)
def auto_delete_file_on_delete(sender, instance, **kwargs):
    """
    Deletes file from filesystem
    when corresponding `StandaloneExportJobs` object is deleted.
    """
    if instance.result:
        if os.path.isfile(instance.result.path):
            logger.info("Removing old AllAll Export file '{}' ({:.1f}MB).".format(
                instance.result.path, os.path.getsize(instance.result.path) / (2 ** 20)))
            os.remove(instance.result.path)
        else:
            logger.warning("Removing StandaloneExportJob model with in-existing file '{}' on disk"
                           .format(instance.result.path))