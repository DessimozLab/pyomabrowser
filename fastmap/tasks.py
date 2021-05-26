import csv
import logging
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timedelta

import Bio.SeqIO
import django.conf
from celery import task, shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django.core.mail import EmailMessage
from django.template.loader import get_template
from pyoma.browser.db import ClosestSeqMapper
from pyoma.common import auto_open

from oma import utils
from .models import FastMappingJobs

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


def submit_mapping(data_id, input_file, map_method=None, target=None, job_name=""):
    engine = settings.FASTMAP.get('engine', 'celery').lower()
    if engine not in ("celery", "cluster"):
        raise django.conf.ImproperlyConfigured("invalid engine setting in FASTMAP configuration")

    res_file_rel = os.path.join("FastMappingExport", "FastMapping-{}.txt.gz".format(data_id))
    res_file_abs = os.path.join(settings.MEDIA_ROOT, res_file_rel)
    logger.debug(f"submit process: engine: {engine}, res_file_abs: {res_file_abs}, hash: {data_id}")
    if engine == "celery":
        r = FastMappingJobs(data_hash=data_id, state="pending", result=res_file_rel,
                            map_method=map_method, fasta=os.path.basename(input_file),
                            name=job_name, processing=False)
        r.save()
        compute_mapping_with_celery.delay(data_id, res_file_abs, input_file, map_method, target)
    elif engine == "cluster":
        res = submit_mapping_on_cluster(data_id, res_file_abs, input_file, map_method, target)
        r = FastMappingJobs(data_hash=data_id, state=res.state, result=res_file_rel,
                            map_method=map_method, fasta=os.path.basename(input_file),
                            name=job_name, processing=False)
        r.save()


@shared_task(soft_time_limit=24*3600)
def compute_mapping_with_celery(data_id, res_file_absolute, input_file, map_method, target):
    t0 = time.time()
    logger.info('starting computing fastmapping of {}'.format(input_file))
    db_entry = FastMappingJobs.objects.get(data_hash=data_id)
    db_entry.state = "running"
    db_entry.save()

    try:
        if map_method in ('s', 'st'):
            mapper = ClosestSeqMapper(utils.db)
        else:
            raise ValueError("Invalid mapping method: {}".format(map_method))
        if target in ("all", ""):
            target = None

        if not os.path.isdir(os.path.dirname(res_file_absolute)):
            os.makedirs(os.path.dirname(res_file_absolute))
        with auto_open(res_file_absolute, "wt") as fout:
            csv_writer = csv.writer(fout, delimiter="\t")
            csv_writer.writerow(
                [
                    "query",
                    "target",
                    "is_main_isoform",
                    "HOG",
                    "OMA_group",
                    "PAM_distance",
                    "Alignment_score",
                ]
            )

            with auto_open(input_file, "rt") as fin:
                seqs = Bio.SeqIO.parse(fin, "fasta")
                it = mapper.imap_sequences(seqs, target_species=target)
                seen_queries = set([])
                for map_res in it:
                    if map_res.query in seen_queries:
                        continue  # we keep just the very best mapping
                    seen_queries.add(map_res.query)
                    if map_res.target.hog_family_nr != 0:
                        hog_id = utils.db.format_hogid(map_res.target.hog_family_nr)
                    else:
                        hog_id = "n/a"
                    if map_res.target.oma_group != 0:
                        oma_grp = "OmaGroup:{}".format(map_res.target.oma_group)
                    else:
                        oma_grp = "n/a"
                    csv_writer.writerow(
                        [
                            map_res.query,
                            map_res.target.omaid,
                            map_res.target.entry_nr == map_res.closest_entry_nr,
                            hog_id,
                            oma_grp,
                            map_res.distance,
                            map_res.score,
                        ]
                    )

            # remove uploaded input file
            os.remove(input_file)
            db_entry.state = 'done'
            db_entry.create_time = timezone.now()
            tot_time = time.time() - t0
            logger.info('finished fastmapping task {} (inputfile {}). took {:.1f}sec'.format(
                data_id, input_file, tot_time))
            send_notification_email(db_entry)

    except SoftTimeLimitExceeded as e:
        logger.warning('computing fastmapping timed out for dataset: {} (inputfile {})'
                       .format(data_id, input_file))
        db_entry.state = 'timeout'
    except Exception as e:
        logger.exception("An error occured while processing {} (inputfile {})"
                         .format(data_id, input_file))
        db_entry.state = "error"
    db_entry.save()


def submit_mapping_on_cluster(session, res_file=None, fasta=None, map_method=None, target=None):
    session_dir = '/tmp/gc3sessions'

    if not os.path.isdir(session_dir):
        os.makedirs(session_dir)
    if res_file is not None and not os.path.isdir(os.path.dirname(res_file)):
        os.makedirs(os.path.dirname(res_file))

    res_file = 'blank' if res_file is None else res_file
    fasta = 'blank' if fasta is None else fasta
    map_method = 's' if map_method is None else map_method
    target = 'all' if target in (None, "") else target

    cmd = ['source', os.path.expanduser(os.path.join('~', 'gc3pie', 'bin', 'activate'))]
    cmd.extend(['&&', 'python', 'fastmapping.py', '-u' 'sqlite:///tmp/gc3session.db',
                '-s', os.path.join(session_dir, session)])
    cmd.append(res_file)
    cmd.append(fasta)
    cmd.append(map_method)
    cmd.append(target)

    cmd = " ".join(cmd)
    logger.info('running command: ' + cmd)

    try:
        res = subprocess.run(cmd, cwd=os.path.dirname(__file__), timeout=1500,
                             shell=True, stdout=subprocess.PIPE)
        if res.returncode == 0:
            shutil.rmtree(os.path.join(session_dir, session))
        return JobStatus(res)

    except subprocess.TimeoutExpired as e:
        logger.exception("Timeout in fast mapping gc3 command: " + e.cmd)
        return JobStatus(-1)


@task()
def update_running_jobs():
    for job in FastMappingJobs.objects.filter(Q(state='pending') | Q(state='running')):
        if job.processing:
            continue
        job.processing = True
        job.save()

        res = submit_mapping_on_cluster(job.data_hash, map_method=job.map_method)
        job.state = res.state
        job.create_time = timezone.now()
        job.processing = False
        job.save()
        if job.state == "done":
            try:
                send_notification_email(job)
            except Exception as e:
                logger.exception("cannot send notification mail for job {}".format(job))


@task()
def purge_old_fastmap():
    time_threshold = datetime.now() - timedelta(days=int(settings.FASTMAP.get('store_files_in_days', 8)))
    FastMappingJobs.objects.filter(create_time__lt=time_threshold).delete()


def send_notification_email(job: FastMappingJobs):
    context = {'job': job, 'time_until_delete': settings.FASTMAP.get('store_files_in_days', None)}
    message = get_template('email_dataset_ready.html').render(context)

    sender = settings.CONTACT_EMAIL
    subj = "[OMA] Results of sequence mapping job {} ready".format(job.name)
    msg = EmailMessage(subj, message, to=[job.email], from_email=sender)
    msg.content_subtype = "html"
    msg.send()
    logger.info(f"notification message sent to {job.email}")