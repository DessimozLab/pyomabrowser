from __future__ import absolute_import
from __future__ import division
import logging
import os
import re
from pathlib import Path
from typing import List

import django
from django.conf import settings
from django.db.models import Q

from oma import utils
from .models import StandaloneExportJobs
import shutil
from django.utils import timezone
from datetime import datetime, timedelta
from celery import shared_task
import subprocess

logger = logging.getLogger(__name__)


class JobStatus(object):
    def __init__(self, subproc):
        if isinstance(subproc, int) and subproc < 0:
            self.state = "error"
        elif subproc.returncode == 0:
            self.state = "done"
        elif subproc.returncode > 3:
            m = re.search(rb'RUNNING\s+(?P<run>\d+)/(?P<tot>\d+)\s', subproc.stdout)
            if m is not None and int(m.group("run")) > 0:
                self.state = "running"
            else:
                self.state = "pending"
        else:
            self.state = "error"

def submit_export(job:StandaloneExportJobs, genomes:List[str], release=None):
    engine = settings.EXPORT_OMA.get('engine', 'celery').lower()
    if engine not in ("celery", "cluster"):
        raise django.conf.ImproperlyConfigured("invalid engine setting in EXPORT_OMA configuration")

    logger.debug("submit process: engine: %s, abs_path for result: %s, hash: %s",
                 engine, job.result.path, job.data_hash)
    if engine == "celery":
        job.save()
        run_export_celery.delay(job.data_hash, genomes)
    elif engine == "cluster":
        res = submit_export_on_cluster(job.data_hash, job.result.path, genomes, release)
        job.state = res.state
        job.save()

def submit_export_on_cluster(session, res_file=None, genomes=None, release=None):
    session_dir = '/tmp/gc3sessions'
    if not os.path.isdir(session_dir):
        os.makedirs(session_dir)
    if res_file is not None and not os.path.isdir(os.path.dirname(res_file)):
        os.makedirs(os.path.dirname(res_file))

    res_file = 'blank' if res_file is None else res_file
    genomes = ['blank'] if genomes is None else genomes

    cmd = ['source', os.path.expanduser(os.path.join('~', 'gc3pie', 'bin', 'activate'))]
    cmd.extend(['&&', 'python', 'gc3workflow.py', '-u' 'sqlite:///tmp/gc3session.db',
                '-s', os.path.join(session_dir, session)])

    if release is not None:
        cmd.extend(['--release', release])

    cmd.append(res_file)
    for g in genomes:
        cmd.append(g)

    cmd = " ".join(cmd)
    logger.info('running command: ' + cmd)
    try:
        res = subprocess.run(cmd, cwd=os.path.dirname(__file__), timeout=1500,
                             shell=True, stdout=subprocess.PIPE)
        if res.returncode == 0:
            shutil.rmtree(os.path.join(session_dir, session))
        logger.debug("return code of export command: {}".format(res.returncode))
        return JobStatus(res)

    except subprocess.TimeoutExpired as e:
        logger.exception("Timeout in standalone export gc3 command: " + e.cmd)
        return JobStatus(-1)


@shared_task()
def update_running_jobs():
    for job in StandaloneExportJobs.objects.filter(Q(state='pending') | Q(state='running')):
        if job.processing:
            continue
        job.processing = True
        job.save()

        res = submit_export_on_cluster(job.data_hash)
        job.state = res.state
        job.create_time = timezone.now()
        job.processing = False
        job.save()


@shared_task()
def purge_old_exports():
    time_threshold = datetime.now() - timedelta(days=8)
    StandaloneExportJobs.objects.filter(create_time__lt=time_threshold).delete()


@shared_task(soft_time_limit=12*3600)
def run_export_celery(data_id, genomes):
    from . import export_standalone
    job = StandaloneExportJobs.objects.get(data_hash=data_id)

    allall_root = settings.EXPORT_OMA.get('allall_root', None)
    build_folder = settings.EXPORT_OMA.get('build_folder', None)
    if allall_root is None or not os.path.isdir(allall_root):
        job.state = "error"
        job.message = "Invalid server configuration. Please contact the OMA administrator"
        job.save()
        raise django.conf.ImproperlyConfigured("invalid allall_root setting in EXPORT_OMA configuration: {}".format(allall_root))
    job.state = "running"
    job.processing = True
    job.create_time = timezone.now()
    job.save()
    try:
        export_standalone.build_export_tarball(
            utils.db, genomes=genomes, outfn=job.result.path, allall=Path(allall_root), tmpfolder=build_folder
        )
        job.state = "done"
        job.create_time = timezone.now()
    except Exception as e:
        job.state = "error"
        job.message = str(e)
        logger.error("export job %s on %s failed: %s", data_id, genomes, e)
    finally:
        job.processing = False
        job.save()


@shared_task(soft_time_limit=6*3600)
def run_fastoma_export(data_id, genomes):
    from . import export_fastoma
    job = StandaloneExportJobs.objects.get(data_hash=data_id)

    build_folder = settings.EXPORT_OMA.get('build_folder', None)
    job.state = "running"
    job.processing = True
    job.create_time = timezone.now()
    job.save()
    try:
        export_fastoma.build_export_tarball(
            utils.db, genomes=genomes, outfn=job.result.path, tmpfolder=build_folder
        )
        job.state = "done"
        job.create_time = timezone.now()
    except Exception as e:
        job.state = "error"
        job.message = str(e)
        logger.error("fastoma export job %s on %s failed: %s", data_id, genomes, e)
    finally:
        job.processing = False
        job.save()