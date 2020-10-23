from __future__ import absolute_import
from __future__ import division

import collections
import logging
import os
import tarfile
import io
import time
import gzip
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
try:
    from Bio.Alphabet import IUPAC
except ImportError:
    IUPAC = None
from django.core.mail import EmailMessage
from django.template.loader import get_template
from zoo.wrappers.aligners import Mafft, DataType, WrapperError

from django.conf import settings
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
import pyoma.browser.models
from pyoma.browser.db import FastMapper
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


@shared_task(soft_time_limit=800)
def compute_msa(data_id, group_type, hog_id_or_grp_nr, *args):
    t0 = time.time()
    logger.info('starting computing MSA')
    db_entry = FileResult.objects.get(data_hash=data_id)
    db_entry.state = "running"
    db_entry.save()

    if group_type == 'hog':
        level = args[0]
        memb = utils.db.member_of_hog_id(hog_id_or_grp_nr, level)
    elif group_type == 'og':
        memb = utils.db.oma_group_members(hog_id_or_grp_nr)
    members = [pyoma.browser.models.ProteinEntry(utils.db, e) for e in memb]
    seqs = []
    for prot in members:
        if IUPAC is not None:
            seq = Seq(prot.sequence, IUPAC.protein)
        else:
            seq = Seq(prot.sequence)
        seqs.append(SeqRecord(seq, id=prot.omaid, annotations={"molecule_type": "protein"}))
    logger.info(u"msa for {:d} sequences (avg length: {:.1f})"
                .format(len(seqs),
                        sum([len(str(s.seq)) for s in seqs])/len(seqs)))
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
        arglist = [group_type, str(hog_id_or_grp_nr)]
        arglist.extend(args)
        logger.exception('error while computing msa for dataset: {}'.format(
            ', '.join(arglist)))
        db_entry.state = 'error'
    except SoftTimeLimitExceeded as e:
        arglist = [group_type, str(hog_id_or_grp_nr)]
        arglist.extend(args)
        logger.warning('computing msa timed out for dataset: {}'.format(', '.join(arglist)))
        db_entry.state = 'timeout'
    db_entry.save()


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

@shared_task
def assign_go_function_to_user_sequences(data_id, sequence_file, tax_limit=None, result_url=None):
    t0 = time.time()
    logger.info('starting projecting GO functions')
    db_entry = FileResult.objects.get(data_hash=data_id)
    db_entry.state = "running"
    db_entry.save()

    name = os.path.join('function_projection', data_id[-2:], data_id[-4:-2], data_id+".txt.gz")
    path = os.path.join(settings.MEDIA_ROOT, name)
    try:
        sequences = SeqIO.parse(sequence_file, 'fasta')
        projector = FastMapper(utils.db)

        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        with gzip.open(path, 'wt') as fout:
            projector.write_annotations(fout, sequences)

        if db_entry.email != '':
            logger.info('sending ready mail to {}'.format(db_entry.email))
            context = {'e': db_entry, 'result_url': result_url}
            message = get_template('email_function_projection_ready.html').render(context)
            sender = "noreply@omabrowser.org"
            msg = EmailMessage("GO Function Predictions ready", message, to=[db_entry.email], from_email=sender)
            msg.content_subtype = "html"
            try:
                msg.send()
            except OSError as e:
                logger.error('cannot send confirmation mail: {}'.format(e))

        db_entry.result = name
        db_entry.state = 'done'
        tot_time = time.time() - t0
        logger.info('finished assign_go_function_to_user_sequences task. took {:.3f}sec'.format(tot_time))
    except:
        logger.exception('error while computing assign_go_function_to_user_sequences for dataset: {}'
            .format(data_id))
        db_entry.state = 'error'
    finally:
        os.remove(sequence_file)
    db_entry.save()