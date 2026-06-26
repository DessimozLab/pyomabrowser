import logging

from django.db import models

logger = logging.getLogger(__name__)


class Release(models.Model):
    """A versioned OMA Browser release. Files may come from multiple Zenodo records."""
    name = models.CharField(max_length=50, unique=True)  # e.g. "All.Mar2026"
    zenodo_record_id = models.CharField(max_length=50, blank=True)  # primary / concept record
    zenodo_doi = models.CharField(max_length=100, blank=True)
    # release_group groups independent dataset lineages (e.g. "All", "Plants").
    # is_latest is enforced as unique within a group, so each lineage can have
    # its own "current" release. The group also drives the /All/ URL lookup.
    release_group = models.CharField(max_length=50, default='All', db_index=True)
    is_latest = models.BooleanField(default=False, db_index=True)
    release_date = models.DateField()

    class Meta:
        ordering = ['-release_date']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.is_latest:
            Release.objects.exclude(pk=self.pk).filter(
                release_group=self.release_group, is_latest=True
            ).update(is_latest=False)
        super().save(*args, **kwargs)


class ZenodoFile(models.Model):
    """A file within a release, served via Zenodo redirect."""
    release = models.ForeignKey(Release, on_delete=models.CASCADE, related_name='files')
    filename = models.CharField(max_length=255)
    zenodo_url = models.URLField(max_length=500)
    size = models.BigIntegerField(default=0)
    checksum = models.CharField(max_length=100, blank=True)
    source_record_id = models.CharField(max_length=50, blank=True)  # which Zenodo record this file came from

    class Meta:
        unique_together = [('release', 'filename')]

    def __str__(self):
        return f"{self.release.name}/{self.filename}"


class DownloadEvent(models.Model):
    """One row per redirected download, for counting purposes."""
    file = models.ForeignKey(ZenodoFile, on_delete=models.CASCADE, related_name='download_events')
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['file', 'timestamp'])]
