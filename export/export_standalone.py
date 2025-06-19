import gzip
import hashlib
import io
import itertools
import logging
import shutil
import subprocess
import tempfile
import textwrap
import urllib.request
import os
import collections
from typing import Dict, List
from pathlib import Path
from pyoma.browser.decorators import timethis

import pyoma.browser.db
from pyoma.browser.db import Database
from pyoma.browser.models import Genome
from pyoma.browser.idmapper import XRefNoApproximateIdMapper
logger = logging.getLogger(__name__)


class SourceAndUniProtIdMapper(XRefNoApproximateIdMapper):
    def __init__(self, db):
        super().__init__(db)
        self.idtype = frozenset(
            [self.xrefEnum[z] for z in ("SourceID", "SourceAC", "UniProtKB/SwissProt", "UniProtKB/TrEMBL")]
        )

def convert_go_to_drwformat(go, fh):
    fh.write("_n := table([],[]): _id := table([],[]): _def := table([],[]): _is := table([],[]): _p := table([],[]): _cb := table([],[]): _hp := table([],[]):\n")
    for nr, term in go.terms.items():
        name = term.name.replace("'","''")
        def_ = term.definition.split('"')[1].replace("'", "''")
        fh.write(f"_n[{nr}] := '{name}':\n")
        fh.write(f"_id['{name}'] := {nr}:\n")
        fh.write(f"_def[{nr}] := '{def_}':\n")
        fh.write(f"_is[{nr}] := {[p.id for p in term.is_a]}:\n")
        for rel, tab in zip(('part_of', 'can_be', 'has_part'), ('_p', '_cb', '_hp')):
            if hasattr(term, rel):
                rels = ",".join([str(x.id) for x in getattr(term, rel)])
                fh.write(f"{tab}[{nr}] := [")
                fh.write(rels)
                fh.write("]:\n")
    fh.write("Ontology_name := _n: Ontology_id := _id: Ontology_def := _def: Ontology_is_a := _is: Ontology_part_of := _p: Ontology_can_be := _cb: Ontology_has_parts := _hp:\n")


class GenomeData:
    def __init__(self, code, seqs, xrefs, splice_map, go_anno):
        self.code = code
        self.seqs = seqs
        self.xrefs = xrefs
        self.splice_map = splice_map
        self.go_anno = go_anno


class DarwinExporter:
    def __init__(self, db: Database):
        self.db = db

    def _get_go_in_darwin_format_for_entrynr_range(self, start:int, stop:int) -> Dict[int, str]:
        go_anno = self.db.get_gene_ontology_annotations(start, stop)
        go_anno.sort()
        res = {}
        for enr, gos in itertools.groupby(go_anno, key=lambda x: x['EntryNr']):
            terms = []
            for goNr, anno in itertools.groupby(gos, key=lambda x: x['TermNr']):
                evidence_info = []
                for evi, ref in itertools.groupby(anno, key=lambda x: x['Evidence']):
                    refs = b"{'" + b"','".join([x['Reference'] for x in ref]) + b"'}"
                    evidence_info.append(f"[{evi.decode()},{refs.decode()}]")
                ev_str = ",".join(evidence_info)
                terms.append(f"{self.db.gene_ontology.term_by_id(goNr)}@[{ev_str}]")
            res[enr] = "; ".join(terms)
        return res

    def _get_crossref(self, start:int, stop:int) -> Dict[int, Dict[str, str]]:
        res = {}
        xref_mapper = SourceAndUniProtIdMapper(self.db)
        xrefs = xref_mapper.map_entry_nr_range(start, stop)
        xrefs.sort(order=('EntryNr', 'XRefSource', 'XRefId'))
        for enr, en_xref_it in itertools.groupby(xrefs, lambda x: x['EntryNr']):
            enr_res = collections.defaultdict(set)
            for row in en_xref_it:
                src = xref_mapper.xrefEnum(row['XRefSource'])
                src = src.replace('Source', '')
                enr_res[src].add(row['XRefId'].decode())
            res[enr] = {src: "; ".join(val) for src, val in enr_res.items()}
        return res

    def _get_splicemap(self, entry_tab):
        off = self.db.id_mapper['OMA'].genome_of_entry_nr(entry_tab[0]['EntryNr'])['EntryOff']
        splice_map = collections.defaultdict(set)
        for prot in entry_tab:
            if prot['AltSpliceVariant'] != 0:
                splice_map[prot['AltSpliceVariant']].add(prot['EntryNr'] - off)
        return list(splice_map.values())

    @timethis(level=logging.INFO)
    def data_for_genome(self, genome):
        proteins = self.db.all_proteins_of_genome(genome)
        go_anno = self._get_go_in_darwin_format_for_entrynr_range(proteins[0]['EntryNr'], stop=proteins[-1]['EntryNr'] + 1)
        xrefs = self._get_crossref(proteins[0]['EntryNr'], stop=proteins[-1]['EntryNr'] + 1)
        seqs = {enr: {"SEQ": self.db.get_sequence(enr).decode(),
                      "DNA": self.db.get_cdna(enr).decode()} for enr in range(proteins[0]['EntryNr'], proteins[-1]['EntryNr'] + 1)
                }
        splice_map = self._get_splicemap(proteins)
        for nr, prot in enumerate(proteins, start=1):
            enr = prot['EntryNr']
            xrefs[enr]['OMA_ID'] = f"{genome}{nr:06d}"
            xrefs[enr]['HOGID'] = prot['OmaHOG'].decode()
            if prot['OmaGroup'] != 0:
                xrefs[enr]['OMAGroup'] = int(prot['OmaGroup'])
            xrefs[enr]['DE'] = self.db.get_description(enr).decode()
        return GenomeData(genome, seqs, xrefs, splice_map, go_anno)

    def _produce_fasta_header(self, xrefs:Dict[str, str]):
        buf = io.StringIO()
        buf.write(xrefs['OMA_ID'])
        for tag in ('AC', 'ID', 'UniProtKB/SwissProt', 'UniProtKB/TrEMBL', 'HOGID', 'DE'):
            if tag in xrefs:
                buf.write(" | ")
                buf.write(xrefs[tag])
        return buf.getvalue()

    def _write_fasta_sequences(self, fname: Path, genome_data:GenomeData):
        with open(fname, 'wt') as fh:
            for enr, xrefs in genome_data.xrefs.items():
                fh.write(f">{self._produce_fasta_header(xrefs)}\n")
                seq = genome_data.seqs[enr]['SEQ']
                for k in range(0, len(seq), 80):
                    fh.write(f"{seq[k:k+80]}\n")

    def _write_splice_file(self, fname: Path, genome_data:GenomeData):
        with open(fname, "wt") as fh:
            for gene in genome_data.splice_map:
                splice_vars = ";".join(map(lambda nr: f"{genome_data.Genome}{nr:06d}", gene))
                fh.write(splice_vars)
                fh.write("\n")

    def process_genome(self, genome:str, folder:Path):
        genome_data = self.data_for_genome(genome)
        fasta = folder / "DB" / (genome + ".fa")
        darwin_db = folder / "Cache" / "DB" / (genome + ".db")
        self._write_fasta_sequences(fasta, genome_data)

        if len(genome_data.splice_map) > 0:
            self._write_splice_file(folder / "DB" / (genome + ".splice"), genome_data)

        #with open(folder / "data" / "GOdata.drw.gz") as fh:
        fasta_hash = darwin_hash_of_file(fasta)
        gs = Genome(self.db, genome)
        with open(darwin_db, 'wt') as fh:
            lin = "; ".join(reversed(gs.lineage))
            fh.write(f"<SCINAME>{gs.sciname}</SCINAME>\n")
            fh.write(f"<OS>{lin}</OS>\n<KINGDOM>{gs.kingdom}</KINGDOM>\n")
            fh.write(f"<5LETTERNAME>{gs.uniprot_species_code}</5LETTERNAME>\n<DBRELEASE>{gs.release}</DBRELEASE>\n")
            fh.write(f"<TAXONID>{gs.ncbi_taxon_id}</TAXONID>\n")
            fh.write(f"<FASTACHECKSUM>{fasta_hash}</FASTACHECKSUM>\n")
            if len(genome_data.splice_map) > 0:
                for chunk, start in enumerate(range(0, len(genome_data.splice_map), 1000),
                                              start=1):
                    fh.write(f"<SPLICEMAP{chunk}>")
                    for gene in genome_data.splice_map[start:start+1000]:
                        fh.write(str(gene))
                    fh.write(f"</SPLICEMAP{chunk}>\n")
            for enr, xrefs in genome_data.xrefs.items():
                fh.write(f"<E>")
                for tag in sorted(xrefs):
                    fh.write(f"<{tag}>{xrefs[tag]}</{tag}>")
                fh.write(f"<FASTAHEADER>{self._produce_fasta_header(xrefs)}</FASTAHEADER>")
                fh.write(f"<SEQ>{genome_data.seqs[enr]['SEQ']}</SEQ>")
                fh.write(f"<DNA>{genome_data.seqs[enr]['DNA'].replace('N','X')}</DNA>")
                if enr in genome_data.go_anno:
                    fh.write(f"<GO>{genome_data.go_anno[enr]}</GO>")
                fh.write('</E>\n')
        gs.dbhash = darwin_hash_of_file(darwin_db)
        gs.fastahash = fasta_hash
        return gs


def darwin_hash_of_file(fn):
    h = hashlib.sha512()
    b = bytearray(128 * 1024)
    mv = memoryview(b)
    with open(fn, 'rb', buffering=0) as f:
        while n := f.readinto(mv):
            h.update(mv[:n])
    return h.hexdigest()[:16]


def get_standalone_extracted_tarball(outpath: Path):
    try:
        urllib.request.urlretrieve("https://omabrowser.org/standalone/OMA.latest.tgz", outpath / "OMA.latest.tgz")
    except IOError as e:
        logger.warning("Cannot download oma standalone: {}", e)
        raise
    subprocess.run(['tar', "xzf", "OMA.latest.tgz"], capture_output=True, cwd=outpath, check=True)
    (outpath / "OMA.latest.tgz").unlink()
    return next(outpath.iterdir())


def build_export_tarball(db:Database, genomes:List[str], outfn, allall:Path, tmpfolder=None):
    with tempfile.TemporaryDirectory(dir=tmpfolder) as tmp:
        tmpdir = Path(tmp)
        standalone_base = get_standalone_extracted_tarball(tmpdir)
        (standalone_base / "Cache" / "DB").mkdir(parents=True, exist_ok=True)
        (standalone_base / "DB").mkdir(parents=True, exist_ok=True)

        with open(standalone_base / "README.exportedAllAll", 'wt') as readme:
            readme.write(textwrap.dedent(f"""
                Together with this OMA Standalone release you downloaded 
                the following {len(genomes)} genomes and their precomputed 
                all-against-all alignments:
                """))

            exporter = DarwinExporter(db)
            ignored_genomes = set()
            GenomeSums = {}
            for g in genomes:
                try:
                    gs = exporter.process_genome(g, standalone_base)
                    GenomeSums[g] = gs
                    readme.write(f"  - {gs.uniprot_species_code}: {gs.sciname} (DB release: {gs.release})\n")
                except Exception as e:
                    ignored_genomes.add(g)
                    logger.warning("cannot convert {}: {}", g, e)
                    readme.write(f"  !SKIPPING {g}. Reason: {e}")
            readme.write("The genome files are stored in fasta format in the folder '/DB'.\n"
                         "The Alignments are stored in '/Cache/AllAll'.\n")

        genomes = set(genomes) - ignored_genomes
        for g1, g2 in itertools.combinations_with_replacement(genomes, 2):
            if GenomeSums[g1].nr_entries > GenomeSums[g2].nr_entries or (GenomeSums[g1].nr_entries == GenomeSums[g2].nr_entries and g1 > g2):
                g1, g2 = g2, g1
            src = allall / g1 / (g2 + ".gz")
            dest = standalone_base / "Cache" / "AllAll" / g1 / (g2 + ".gz")
            if not src.exists():
                logger.warning("%s does not exist. skipping", src)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(src, dest)
            except OSError as e:
                if e.errno == 18:
                    shutil.copy(src, dest)
                else:
                    logger.error("Error linking %s to %s: %s", src, dest, e)
                    raise

            vers = dest.parent / (g2 + ".sha2.gz")
            with gzip.open(vers, 'wt') as sha2:
                sha2.write(f"AssertDatabaseVersionsInSync('{GenomeSums[g1].dbhash}','{GenomeSums[g2].dbhash}'):\n")
                sha2.write("AssertMinScoreParam(130):\n")

        with gzip.open(standalone_base / "data" / "GOdata.drw.gz", 'wt') as fh:
            convert_go_to_drwformat(db.gene_ontology, fh)

        Path(outfn).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["tar", "czf", outfn, standalone_base.name], cwd=tmpdir, capture_output=True, check=True)



if __name__ == "__main__":
    db = pyoma.browser.db.Database('/Users/adriaal/Downloads/All.Jul2023/data/OmaServer.h5')
    build_export_tarball(db, ['ECOLI', 'BACSU'], "/tmp/OMA.xx.tgz",
                         Path('/Users/adriaal/Downloads/AllAll'))