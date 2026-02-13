import os
from django.db import models
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class AsyncJobBase(models.Model):
    STATE_PENDING = "pending"
    STATE_RUNNING = "running"
    STATE_DONE = "done"
    STATE_ERROR = "error"
    STATE_TIMEOUT = "timeout"

    STATE_CHOICES = [
        (STATE_PENDING, "Pending"),
        (STATE_RUNNING, "Running"),
        (STATE_DONE, "Done"),
        (STATE_ERROR, "Error"),
        (STATE_TIMEOUT, "Timeout"),
    ]

    data_hash = models.CharField(max_length=32, primary_key=True)
    state = models.CharField(max_length=8, choices=STATE_CHOICES, default=STATE_PENDING)
    result = models.FileField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)
    last_accessed_at = models.DateTimeField(null=True, blank=True)
    access_count = models.IntegerField(default=0)

    runtime_seconds = models.FloatField(null=True)
    message = models.TextField(blank=True)
    email = models.EmailField(blank=True)

    # maximum allowed time for pending jobs in seconds (can override in subclasses)
    PENDING_TIMEOUT_SECONDS = 300

    class Meta:
        abstract = True

    # -----------------------
    # Job cleanup
    # -----------------------
    def is_error_or_long_pending(self, delete=False):
        """
        checks if state is error or job is pending for too long.

        The method returns True if the job is in error state or pending for too long,
        False otherwise. If delete=True, the job will be deleted if it is in error or pending for too long.

        :param bool delete: if True, the job will be deleted if it is in error or pending for too long.

        :return bool: True if the job is in error state or pending for too long, False otherwise.
        """
        if self.state == self.STATE_ERROR or (
                self.state == self.STATE_PENDING and
                (timezone.now() - self.created_time).total_seconds() > self.PENDING_TIMEOUT_SECONDS
        ):
            if delete:
                self.delete()
            return True
        return False

    # -----------------------
    # Auto-delete file hook
    # -----------------------
    @classmethod
    def _connect_auto_delete_signal(cls):
        """
        Connects post_delete signal to automatically delete the file on disk.
        """
        def auto_delete_file_on_delete(sender, instance, **kwargs):
            if instance.result:
                if os.path.isfile(instance.result.path):
                    logger.info("Removing file '{}' ({:.1f}MB).".format(
                        instance.result.path, os.path.getsize(instance.result.path) / (2 ** 20)))
                    os.remove(instance.result.path)
                else:
                    logger.warning(
                        f"Deleting model with non-existing file '{instance.result.path}' on disk"
                    )

        models.signals.post_delete.connect(auto_delete_file_on_delete, sender=cls, weak=False)

    def save(self, *args, **kwargs):
        # connect the signal once per subclass
        if not hasattr(self.__class__, "_signal_connected"):
            self.__class__._connect_auto_delete_signal()
            self.__class__._signal_connected = True
        super().save(*args, **kwargs)


class FileResult(AsyncJobBase):
    result_type = models.CharField(max_length=32)
    name = models.CharField(max_length=64, blank=True)