import functools
import logging
import time
import os

from typing import Type

from celery.exceptions import SoftTimeLimitExceeded
from celery import shared_task
from django.conf import settings

from .models import AsyncJobBase
from .misc import md5

logger = logging.getLogger(__name__)

def async_job_task(model: Type[AsyncJobBase], logical_inputs=None, **shared_task_kwargs):
    logical_inputs = logical_inputs or {}

    def decorator(func):

        @shared_task(bind=True, **shared_task_kwargs)
        @functools.wraps(func)
        def wrapper(self, job_hash, **kwargs):
            logger.debug("Starting async task for job with hash: {}".format(job_hash))
            try:
                job = model.objects.get(pk=job_hash)
            except model.DoesNotExist:
                raise ValueError("Job with hash {} does not exist.".format(job_hash))

            start = time.time()
            job.state = model.STATE_RUNNING
            job.metadata = job.metadata or {}
            job.metadata.update({
                'task_id': self.request.id,
                'task_name': self.name,
                'parameters': kwargs,
                'logical_inputs': {
                    k: kwargs.get(v) for k, v in wrapper.logical_inputs.items() if v in kwargs
                }
            })
            job.save(update_fields=['state', 'metadata'])

            try:
                result = func(job, **kwargs)
                if isinstance(result, tuple):
                    result_path, task_meta = result
                    job.metadata.update(task_meta)
                else:
                    result_path = result

                if result_path and os.path.exists(os.path.join(settings.MEDIA_ROOT, result_path)):
                    job.metadata.update({'md5_checksum': md5(os.path.join(settings.MEDIA_ROOT, result_path))})

                job.state = model.STATE_DONE
                job.result.name = result_path
                logger.info("Task completed successfully for job %s. Result saved at: %s", job_hash, result_path)

            except SoftTimeLimitExceeded:
                job.state = model.STATE_TIMEOUT
                logger.warning("Task for job %s exceeded time limit and was terminated.", job_hash)
                raise

            except Exception as e:
                job.state = model.STATE_ERROR
                job.message = str(e)
                logger.error("Task for job %s failed with error: %s", job_hash, e)
                raise

            finally:
                try:
                    job.runtime_seconds = time.time() - start
                    job.save()
                except Exception:
                    logger.exception("Failed to save job final state for job %s", job_hash)
            return result

        wrapper.logical_inputs = logical_inputs
        return wrapper

    return decorator
