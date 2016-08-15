from __future__ import absolute_import

import collections
import logging
import os
import tarfile
import io
import time
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
from Bio.Alphabet import IUPAC
from zoo.wrappers.aligners import Mafft, DataType, WrapperError

from django.conf import settings
from celery import shared_task
import pyoma.browser.models
from . import utils, misc
from .models import FileResult


logger = logging.getLogger(__name__)


@shared_task
def export_marker_genes(genomes, data_id, min_species_coverage=0.5, top_N_grps=None):
    logger.debug('starting task export_marker_genes for {}'.format(data_id))
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
        logger.exception('failed to create marker genes:')
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
            t.size = len(grpfile.getvalue())
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


@shared_task
def compute_msa(data_id, group_type, entry_nr_or_grp_nr, *args):
    t0 = time.time()
    logger.info('starting computing MSA')
    db_entry = FileResult.objects.get(data_hash=data_id)
    db_entry.state = "running"
    db_entry.save()

    if group_type == 'hog':
        level = args[0]
        memb = utils.db.hog_members(entry_nr_or_grp_nr, level)
    elif group_type == 'og':
        memb = []
    members = [pyoma.browser.models.ProteinEntry(utils.db, e) for e in memb]
    seqs = [SeqRecord(Seq(m.sequence, IUPAC.protein), id=m.omaid) for m in members]
    logger.info('msa for {:d} sequences (avg length: {:.1f})'.format(len(seqs), 500))
    try:
        mafft = Mafft(seqs, datatype=DataType.PROTEIN)
        msa = mafft()
        name = os.path.join('msa', data_id[-2:], data_id[-4:-2], data_id)
        path = os.path.join(settings.MEDIA_ROOT, name)
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        with open(path, 'w') as fh:
            SeqIO.write(msa, fh, 'fasta')
        db_entry.result = name
        db_entry.state = 'done'
        tot_time = time.time() - t0
        logger.info('finished compute_msa task. took {:.3f}sec, {:.3%} for mafft'.format(tot_time, mafft.elapsed_time/tot_time))
    except (IOError, WrapperError) as e:
        logger.exception('error while computing msa for dataset: {}'.format(
            ', '.join([group_type, str(entry_nr_or_grp_nr), *args])))
        db_entry.state = 'error'
    db_entry.save()
