import collections
import csv
import logging
import subprocess
import tempfile
import textwrap
import time
from typing import List, Dict
from pathlib import Path

from pyoma.browser.db import Database
from pyoma.browser.models import Genome
from .export_standalone import DarwinExporter, GenomeData
logger = logging.getLogger(__name__)


_GFF3_ESCAPE = {
    "%": "%25", ";": "%3B", "=": "%3D", "&": "%26", ",": "%2C",
    "\t": "%09", "\n": "%0A", "\r": "%0D",
}


def _gff3_escape(value) -> str:
    return "".join(_GFF3_ESCAPE.get(c, c) for c in str(value))


def _gff3_line(seqid, ftype, start, end, strand, attrs, source="OMA", score=".", phase="."):
    attr_str = ";".join(f"{k}={_gff3_escape(v)}" for k, v in attrs.items())
    return f"{seqid}\t{source}\t{ftype}\t{start}\t{end}\t{score}\t{strand}\t{phase}\t{attr_str}\n"


class FastaExporter(DarwinExporter):
    def process_genome(self, genome:str, folder:Path) -> Genome:
        t0 = time.perf_counter()
        genome_data = self.data_for_genome(genome)
        t1 = time.perf_counter()
        fasta = folder / "proteome" / (genome + ".fa")
        self._write_fasta_sequences(fasta, genome_data)
        t2 = time.perf_counter()

        if len(genome_data.splice_map) > 0:
            self._write_splice_file(folder / "splice" / (genome + ".splice"), genome_data)
        t3 = time.perf_counter()
        self._write_gff3(folder / "gff3" / (genome + ".gff3"), genome, genome_data)
        gs = Genome(self.db, genome)
        t4 = time.perf_counter()
        msg = [f"Writing files for genome {genome} took {t4 - t0:.2f}s:",
               f"   Loading genome data: {t1-t0:.2f}s"
               f"   protein sequences:   {t2-t1:.2f}s",
               f"   splice file:         {t3-t2:.2f}s",
               f"   gff3:                {t4-t3:.2f}s"]
        logger.info("\n".join(msg))
        return gs

    def _get_go_in_darwin_format_for_entrynr_range(self, start:int, stop:int) -> Dict[int, str]:
        """we don't need this"""
        return {}

    def _write_gff3(self, fname: Path, genome: str, genome_data: GenomeData):
        fname.parent.mkdir(parents=True, exist_ok=True)
        # Bulk-read the whole entry/locus tables for this genome up-front instead of
        # issuing one HDF5 `where` query per gene (ProteinEntry.alternative_isoforms /
        # Database.get_exons) -- with tens of thousands of genes those per-gene queries
        # dominate the runtime (minutes for a mid-size genome).
        proteins = self.db.all_proteins_of_genome(genome)
        locus_tab = self.db.get_hdf5_handle().get_node(f"/Protein/Locus/{genome}").read()

        exons_by_entry = collections.defaultdict(list)
        for row in locus_tab:
            exons_by_entry[int(row["EntryNr"])].append((int(row["Start"]), int(row["End"])))

        genes_by_key = collections.defaultdict(list)
        for prot in proteins:
            key = int(prot["EntryNr"]) if prot["AltSpliceVariant"] == 0 else int(prot["AltSpliceVariant"])
            genes_by_key[key].append(prot)

        chrom_max_end = {}
        genes = []
        for key, transcripts in genes_by_key.items():
            main = next(t for t in transcripts if int(t["EntryNr"]) == key)
            chrom = main["Chromosome"].decode()
            gene_start = min(int(t["LocusStart"]) for t in transcripts)
            gene_end = max(int(t["LocusEnd"]) for t in transcripts)
            chrom_max_end[chrom] = max(chrom_max_end.get(chrom, 0), gene_end)
            genes.append((chrom, gene_start, gene_end, main, transcripts))
        genes.sort(key=lambda x: (x[0], x[1]))

        with open(fname, "wt") as fh:
            fh.write("##gff-version 3\n")
            for chrom in sorted(chrom_max_end):
                fh.write(f"##sequence-region {chrom} 1 {chrom_max_end[chrom]}\n")

            for chrom, gene_start, gene_end, main, transcripts in genes:
                strand = "+" if main["LocusStrand"] > 0 else "-"
                xrefs = genome_data.xrefs[int(main["EntryNr"])]
                gene_omaid = xrefs["OMA_ID"]
                gene_id = f"gene_{gene_omaid}"
                gene_attrs = {"ID": gene_id, "Name": gene_omaid}
                if xrefs.get("ID"):
                    gene_attrs["gene_id"] = xrefs["ID"]
                fh.write(_gff3_line(chrom, "gene", gene_start, gene_end, strand, gene_attrs))

                for t in transcripts:
                    t_enr = int(t["EntryNr"])
                    t_strand = "+" if t["LocusStrand"] > 0 else "-"
                    t_xrefs = genome_data.xrefs[t_enr]
                    t_omaid = t_xrefs["OMA_ID"]
                    mrna_id = f"mRNA_{t_omaid}"
                    mrna_attrs = {"ID": mrna_id, "Parent": gene_id, "Name": t_omaid}
                    acs = t_xrefs.get("AC")
                    if acs:
                        mrna_attrs["transcript_id"] = acs
                    fh.write(_gff3_line(chrom, "mRNA", int(t["LocusStart"]), int(t["LocusEnd"]), t_strand, mrna_attrs))

                    exons = sorted(exons_by_entry.get(t_enr, ())) or [(int(t["LocusStart"]), int(t["LocusEnd"]))]
                    for nr, (ex_start, ex_end) in enumerate(exons, start=1):
                        exon_attrs = {"ID": f"exon_{t_omaid}_{nr}", "Parent": mrna_id}
                        fh.write(_gff3_line(chrom, "exon", ex_start, ex_end, t_strand, exon_attrs))


def build_export_tarball(db:Database, genomes:List[str], outfn, tmpfolder=None):
    with tempfile.TemporaryDirectory(dir=tmpfolder) as tmp:
        tmpdir = Path(tmp)
        basedir = tmpdir / "FastOMA_dataset"
        basedir.mkdir(exist_ok=True)
        with open(basedir / "README.export", 'wt') as readme:
            readme.write(textwrap.dedent(f"""
                This dataset has been exported from OMA release '{db.get_release_name()}' 
                and contains the following {len(genomes)} proteomes:
                """))

            exporter = FastaExporter(db)
            ignored_genomes = set()
            GenomeSums = {}
            for g in genomes:
                try:
                    gs = exporter.process_genome(g, basedir)
                    GenomeSums[g] = gs
                    readme.write(f"  - {gs.uniprot_species_code}: {gs.sciname} (DB release: {gs.release})\n")
                except Exception as e:
                    ignored_genomes.add(g)
                    logger.warning("cannot convert {}: {}", g, e)
                    readme.write(f"  !SKIPPING {g}. Reason: {e}")
            readme.write("The proteome data are stored under /proteome, the splice files \n"
                         "under /splice (if alternative splicing variants exist), and the \n"
                         "gene positions (GFF3 format) under /gff3.\n")

        genomes = set(genomes) - ignored_genomes
        with open(basedir / "species_info.txt", "wt") as fh:
            writer = csv.writer(fh, dialect='excel-tab')
            writer.writerow(("Name", "NCBITaxonId", "Scientific_name", "DBRelease", "Source"))
            for g, gsum in GenomeSums.items():
                writer.writerow((g, gsum.ncbi_taxon_id, gsum.sciname, gsum.release, gsum.source))

        subtax = db.tax.get_induced_taxonomy([gsum.ncbi_taxon_id for g, gsum in GenomeSums.items()], collapse=True,
                                             augment_parents=True)
        nwk = subtax.newick(leaf="uniprot_species_code", quoted=True)
        with open(basedir / "species_tree.nwk", "wt") as fh:
            fh.write(nwk)

        Path(outfn).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["tar", "czf", outfn, basedir.name], cwd=tmpdir, capture_output=True, check=True)
