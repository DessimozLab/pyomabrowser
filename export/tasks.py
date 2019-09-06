from __future__ import absolute_import
from __future__ import division
import logging
import os
import re
from django.db.models import Q
from .models import StandaloneExportJobs
import shutil
from django.utils import timezone
from datetime import datetime, timedelta
from celery import task
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


def submit_export(session, res_file=None, genomes=None):
    session_dir = '/tmp/gc3sessions'
    if not os.path.isdir(session_dir):
        os.makedirs(session_dir)
    if res_file is not None and not os.path.isdir(os.path.dirname(res_file)):
        os.makedirs(os.path.dirname(res_file))

    res_file = 'blank' if res_file is None else res_file
    genomes = ['blank'] if genomes is None else genomes

    cmd = ['source', os.path.expanduser(os.path.join('~', 'gc3pie', 'bin', 'activate'))]
    cmd.extend(['&&', 'python', 'gc3workflow.py', '-u' 'sqlite:///tmp/gc3session.db',
                '-s', os.path.join(session_dir, session), res_file])
    for g in genomes:
        cmd.append(g)

    cmd = " ".join(cmd)
    logger.info('running command: ' + cmd)
    try:
        res = subprocess.run(cmd, cwd=os.path.dirname(__file__), timeout=1500,
                             shell=True, stdout=subprocess.PIPE)
        if res.returncode == 0:
            shutil.rmtree(os.path.join(session_dir, session))
        return JobStatus(res)

    except subprocess.TimeoutExpired as e:
        logger.exception("Timeout in standalone export gc3 command: " + e.cmd)
        return JobStatus(-1)


@task()
def update_running_jobs():
    for job in StandaloneExportJobs.objects.filter(Q(state='pending') | Q(state='running')):
        if job.processing:
            continue
        job.processing = True
        job.save()

        res = submit_export(job.data_hash)
        job.state = res.state
        job.create_time = timezone.now()
        job.processing = False
        job.save()


@task()
def purge_old_exports():
    time_threshold = datetime.now() - timedelta(days=8)
    StandaloneExportJobs.objects.filter(create_time__lt=time_threshold).delete()
