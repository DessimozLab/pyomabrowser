import csv
import logging
import subprocess
import tempfile
import textwrap
from typing import List, Dict
from pathlib import Path

from pyoma.browser.db import Database
from pyoma.browser.models import Genome
from .export_standalone import DarwinExporter
logger = logging.getLogger(__name__)


class FastaExporter(DarwinExporter):
    def process_genome(self, genome:str, folder:Path) -> Genome:
        genome_data = self.data_for_genome(genome)
        fasta = folder / "proteome" / (genome + ".fa")
        self._write_fasta_sequences(fasta, genome_data)

        if len(genome_data.splice_map) > 0:
            self._write_splice_file(folder / "splice" / (genome + ".splice"), genome_data)

        gs = Genome(self.db, genome)
        return gs

    def _get_go_in_darwin_format_for_entrynr_range(self, start:int, stop:int) -> Dict[int, str]:
        """we don't need this"""
        return {}


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
                         "under /splice (if alternative splicing variants exist).\n")

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
