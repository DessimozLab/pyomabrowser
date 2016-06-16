from __future__ import absolute_import

import collections
import logging
import os
import tarfile
import io
import time

from django.core.files import File
from django.conf import settings
from celery import shared_task
import pyoma.browser.models
from . import utils, misc
from .models import FileResult

logger = logging.getLogger(__name__)


@shared_task
def export_marker_genes(genomes, data_id, min_species_coverage=0.5, top_N_grps=None):
    logger.debug('')
    db_entry = FileResult.objects.get(data_hash=data_id)
    db_entry.state = 'running'
    db_entry.save()
    try:
        grps = collect_groups(genomes, min_species_coverage=min_species_coverage)
        if top_N_grps is not None:
            size_ordered_grpids = sorted(grps.keys(), key=lambda x: -len(grps[x]))
            grps = {k: grps[k] for k in size_ordered_grpids[0:top_N_grps]}
        with FastaTarballResultBuilder('marker_genes', 'OMAGroup_', data_id) as exporter:
            exporter.add_groups(grps)

        db_entry.result = exporter.fname
        db_entry.state = 'done'

    except Exception:
        logger.exception()
        db_entry.state = 'error'
    finally:
        db_entry.save()


def collect_groups(genomes, min_species_coverage):
    memb = collections.defaultdict(list)
    entryTab = utils.db.get_hdf5_handle().get_node('/Protein/Entries')
    for g in genomes:
        ran = utils.id_mapper['OMA'].genome_range(g)
        for row in entryTab.where('(EntryNr >= {}) & (EntryNr <= {})'.format(*ran)):
            if row['OmaGroup'] != 0:
                memb[row['OmaGroup']].append(row['EntryNr'])
    # remove groups that are too small
    min_cnt = max(2, min_species_coverage * len(genomes))
    filtered = {grp: memb[grp] for grp in memb if len(memb[grp]) >= min_cnt}
    return filtered


class FastaTarballResultBuilder(object):

    def __init__(self, prefix, grouptype, data_id):
        self.prefix = prefix
        self.grouptype = grouptype
        self.fname = os.path.join("markers","{}_{}.tgz".format(prefix, data_id))
        self.fpath = os.path.join(settings.MEDIA_ROOT, self.fname)

    def __enter__(self):
        file_dir = os.path.dirname(self.fpath)
        if not os.path.isdir(file_dir):
            os.makedirs(file_dir)
        self.tar = tarfile.open(self.fpath, mode='w:gz')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.tar.close()

    def add_groups(self, groups):
        t = tarfile.TarInfo(self.prefix)
        t.type = tarfile.DIRTYPE
        t.mode = 0o755
        self.tar.addfile(t)

        for grp_key, membs in groups.items():
            grpfile = io.BytesIO(self._group_to_fasta(membs).encode('utf-8'))
            t = tarfile.TarInfo('{}/{}{}.fa'.format(
                self.prefix, self.grouptype, grp_key))
            t.size = grpfile.getbuffer().nbytes
            t.type = tarfile.REGTYPE
            t.mode = 0o644
            t.uid = 501
            t.gid = 20
            t.mtime = time.time()
            self.tar.addfile(t, grpfile)

    def format_fasta_header(self, e):
        return " | ".join([e.omaid, 'OMA{}'.format(e.oma_group),
                           e.canonicalid, '[{}]'.format(e.genome.sciname)])

    def _group_to_fasta(self, group):
        headers = []
        seqs = []
        for memb in group:
            e = pyoma.browser.models.ProteinEntry.from_entry_nr(utils.db, memb)
            headers.append(self.format_fasta_header(e))
            seqs.append(e.sequence)
        return misc.as_fasta(headers=headers, seqs=seqs)
