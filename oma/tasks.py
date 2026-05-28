from __future__ import absolute_import
from __future__ import division

import collections
import logging
import os
import random
import tarfile
import io
import time
import gzip
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
from pyoma.browser.exceptions import DBVersionError

from .decorators import async_job_task
from .misc import result_upload_path

try:
    from Bio.Alphabet import IUPAC
except ImportError:
    IUPAC = None
from django.core.mail import EmailMessage
from django.template.loader import get_template
from zoo.wrappers.aligners import Mafft, Foldmason, DataType, WrapperError
from zoo.utils import auto_open

from django.conf import settings
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
import pyoma.browser.models
from pyoma.browser.db import FastMapper
from . import utils, misc
from .models import FileResult

logger = logging.getLogger(__name__)


@async_job_task(model=FileResult)
def export_marker_genes(job: FileResult, genomes, min_species_coverage=0.5, top_N_grps=None):
    logger.info('starting task export_marker_genes for %s', job.data_hash)

    grps = collect_groups(genomes, min_species_coverage=min_species_coverage)
    if top_N_grps is not None:
        size_ordered_grpids = sorted(grps.keys(), key=lambda x: -len(grps[x]))
        grps = {k: grps[k] for k in size_ordered_grpids[0:top_N_grps]}
    with FastaTarballResultBuilder('marker_genes', 'OMAGroup_', job.data_hash) as exporter:
        exporter.add_groups(grps)
    task_meta = {
        'n_groups': len(grps),
        'avg_group_size': sum(len(g) for g in grps.values()) / len(grps) if len(grps) > 0 else 0,
    }
    return exporter.fname, task_meta


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
        self.fname = misc.result_upload_path(f"markers", prefix, data_id, "tgz" )
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
            for ext, content in zip(["fa", "fna"], self._group_to_fasta(membs)):
                grpfile = io.BytesIO(content.encode('utf-8'))
                t = tarfile.TarInfo('{}/{}{}.{}'.format(
                    self.prefix, self.grouptype, grp_key, ext))
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
        cds = []
        for memb in group:
            e = pyoma.browser.models.ProteinEntry.from_entry_nr(utils.db, memb)
            headers.append(self.format_fasta_header(e))
            seqs.append(e.sequence)
            cds.append(e.cdna)
        return misc.as_fasta(headers=headers, seqs=seqs), misc.as_fasta(headers=headers, seqs=cds)


@async_job_task(FileResult, soft_time_limit=800, logical_inputs=dict(group_type="group_type", group_id="hog_id_or_grp_nr", level="level", tool="tool", max_seqs="max_nr_seqs"))
def compute_msa(job: FileResult, group_type, hog_id_or_grp_nr, **kwargs):
    logger.info(f'starting computing MSA for {group_type} {hog_id_or_grp_nr} with data_id {job.data_hash}')
    t0  = time.perf_counter()
    if group_type == 'hog':
        level = kwargs.get('level', None)
        memb = utils.db.member_of_hog_id(hog_id_or_grp_nr, level)
    elif group_type == 'og':
        memb = utils.db.oma_group_members(hog_id_or_grp_nr)
    tool = kwargs.get('tool', 'Mafft')
    seqs, struc = [], []
    for e in memb:
        prot = pyoma.browser.models.ProteinEntry(utils.db, e)
        if IUPAC is not None:
            seq = Seq(prot.sequence, IUPAC.protein)
        else:
            seq = Seq(prot.sequence)
        seqs.append(SeqRecord(seq, id=prot.omaid, annotations={"molecule_type": "protein"}))
        if tool == 'Foldmason':
            try:
                three_di = prot.structure.seq_3di.decode()
                seq = Seq(three_di, IUPAC.protein) if IUPAC else Seq(three_di)
            except (AttributeError, KeyError) as e:
                logger.warning("No structure found for %s", prot.omaid)
                raise DBVersionError("No structure found for %s", prot.omaid)
            struc.append(SeqRecord(seq, id=prot.omaid, annotations={"molecule_type": "protein"}))

    avg_len = sum([len(s) for s in seqs])/len(seqs) if len(seqs) > 0 else 0
    n_seqs = len(seqs)
    logger.info("msa for %d sequences (avg length: %.1f)",len(seqs), avg_len)

    if kwargs.get('max_nr_seqs') and n_seqs > kwargs['max_nr_seqs']:
        logger.warning("too many sequences for msa (%d), subsampling!", n_seqs)
        keep = random.sample(range(len(seqs)), kwargs['max_nr_seqs'])
        seqs = [seqs[k] for k in keep]
        if tool == 'Foldmason':
            struc = [struc[k] for k in keep]

    try:
        if tool=="Mafft":
            aligner = Mafft(seqs, datatype=DataType.PROTEIN)
            msa = aligner()
        elif tool=="Foldmason":
            aligner = Foldmason(seqs, struc, datatype=DataType.PROTEIN)
            res = aligner()
            msa = res['aa']
            msa_3di = res['3di']
        else:
            raise NotImplementedError(f"MSA tool {tool} not implemented")
        name = result_upload_path('msa', "MSA", job.data_hash, "fasta.gz")
        path = os.path.join(settings.MEDIA_ROOT, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with gzip.open(path, 'wt') as fh:
            SeqIO.write(msa, fh, 'fasta')
        if tool == 'Foldmason':
            path_3di = path.replace('.fasta.gz', '_3di.fasta.gz')
            with gzip.open(path_3di, 'wt') as fh:
                SeqIO.write(msa_3di, fh, 'fasta')
    except (IOError, WrapperError) as e:
        arglist = [group_type, str(hog_id_or_grp_nr), *kwargs.items()]
        logger.exception('error while computing msa for dataset: {}'.format(
            ', '.join(arglist)))
        raise

    tot_time = time.perf_counter() - t0
    logger.info(
        f'finished compute_msa task. took %.3f sec, %.3f%% for {tool}',
        tot_time,
        100 * aligner.elapsed_time / tot_time
    )
    task_meta = {
        'n_sequences': n_seqs,
        'n_sequences_aligned': len(msa),
        'avg_length': avg_len,
        'subsampled': kwargs.get('max_nr_seqs') is not None and n_seqs > kwargs['max_nr_seqs'],
        'compression': 'gzip',
        'tool': tool,
    }
    return name, task_meta




class FunctionProjectorMock(object):
    def __init__(self, sequences, limit):
        self.go = utils.db.gene_ontology
        self.sequences = sequences

    def __iter__(self):
        for seq in self.sequences:
            for go, from_ in zip((10844, 6915), ('YEAST05232', 'HUMAN02242')):
                rec = collections.defaultdict(str)
                goterm = self.go.ensure_term(go)
                rec.update({'DB': 'OMA', 'DB_Object_ID': seq.id, 'GO_ID': str(goterm),
                           'DB:Reference': 'OMAFun:002', 'Evidence': 'IEA', 'With':from_,
                           'Assigned_by': 'OMA Fun Proj', 'Aspect': 'M'})
                yield rec

@async_job_task(FileResult)
def assign_go_function_to_user_sequences(job: FileResult, sequence_file, tax_limit=None, result_url=None):
    t0 = time.time()
    logger.info('starting projecting GO functions for %s with data_id %s', sequence_file, job.data_hash)

    name = result_upload_path('function_projection', "OMA-GO", job.data_hash, "gaf.gz")
    path = os.path.join(settings.MEDIA_ROOT, name)
    try:
        with auto_open(sequence_file, 'rt') as seq_in:
            sequences = SeqIO.parse(seq_in, 'fasta')
            projector = FastMapper(utils.db)

            if not os.path.isdir(os.path.dirname(path)):
                os.makedirs(os.path.dirname(path))
            with gzip.open(path, 'wt') as fout:
                projector.write_annotations(fout, sequences)

        if job.email != '':
            logger.info('sending ready mail to {}'.format(job.email))
            context = {'e': job, 'result_url': result_url}
            message = get_template('email_function_projection_ready.html').render(context)
            sender = "noreply@omabrowser.org"
            msg = EmailMessage("GO Function Predictions ready", message, to=[job.email], from_email=sender)
            msg.content_subtype = "html"
            try:
                msg.send()
            except OSError as e:
                logger.error('cannot send confirmation mail: {}'.format(e))

        tot_time = time.time() - t0
        logger.info('finished assign_go_function_to_user_sequences task. took {:.3f}sec'.format(tot_time))
    except:
        logger.exception('error while computing assign_go_function_to_user_sequences for dataset: {}'
            .format(job.data_hash))
        raise
    finally:
        os.remove(sequence_file)
    return name, {}