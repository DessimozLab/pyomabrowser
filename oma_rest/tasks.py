import gzip
import json
import tarfile
import tempfile
import time
import os
from oma import utils
from .models import EnrichmentAnalysisModel
from django.conf import settings
from django.urls import reverse
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from pyoma.application.enrichment import ancestral_species_go_enrichment, extant_species_go_enrichment, generate_plots
from pyoma.browser.models import ProteinEntry
from pyoma.browser.exceptions import AmbiguousID, InvalidId

import logging
logger = logging.getLogger(__name__)

def _generate_media_filepath_stub(obj):
    basename = f"GOEA-{obj.data_hash}"
    return os.path.join("go_enrichment", obj.data_hash[-2:], obj.data_hash[-4:-2], basename)


def compute_ancestral_enrichment(obj: EnrichmentAnalysisModel):
    level = obj.taxlevel
    logger.debug(f"ancestral enrichment on level {level}")
    hogs = {}
    for elem in obj.foreground:
        if elem.startswith("HOG:"):
            hogs[elem] = elem
        else:
            try:
                entry = ProteinEntry(utils.db, utils.id_resolver.resolve(elem))
                hog = utils.db.iter_hogs_at_level(entry.oma_hog, level)
                hogs[elem] = next(hog)['ID'].decode()
            except (AmbiguousID, InvalidId, StopIteration) as e:
                logger.debug(f"cannot map {elem}: {e}")
                hogs[elem] = None
    logger.info(f"mapping: {hogs}")
    go_res = ancestral_species_go_enrichment(utils.db, level=level, foreground_hogs=set(hogs.values()) - {None}, score_cutoff=0.2)
    return go_res, hogs

def compute_extant_enrichment(obj: EnrichmentAnalysisModel):
    logger.debug("extant enrichment analysis")
    entries = {}
    for entry in obj.foreground:
        try:
            entries[entry] = utils.id_resolver.resolve(entry)
        except (AmbiguousID, InvalidId) as e:
            entries[entry] = None
    logger.info(f"mapping: {entries}")
    go_res = extant_species_go_enrichment(utils.db, foreground_entries=set(entries.values()) - {None})
    return go_res, entries


def write_parameters_file(path, obj: EnrichmentAnalysisModel, mapping):
    with open(path, "wt") as fout:
        fout.write("GO Enrichment Input Data\n")
        fout.write("------------------------\n\n")
        if obj.name:
            fout.write(f"Analysis name: {obj.name}\n\n")
        fout.write(f"Type: {obj.get_type_display()}\n\n")
        if obj.type == "ancestral":
            url = reverse("ancestralgenome_genes", args=(obj.taxlevel,))
            fout.write(f"Background: {obj.taxlevel}\n\thttps://omabrowser.org{url}\n\n")
        else:
            one_gene = next(iter(mapping.values()))
            genome = utils.db.id_mapper['OMA'].genome_of_entry_nr(one_gene)
            url = reverse("genome_genes", args=(genome['UniProtSpeciesCode'].decode(),))
            fout.write(f"Background: {genome['SciName'].decode()}\n")
            fout.write(f"\thttps://omabrowser.org{url}\n\n")
        fout.write("Foreground genes/hogs:\n")
        for k, v in mapping.items():
            if v is None:
                v = "n/a"
            elif isinstance(v, int):
                v = utils.db.id_mapper['OMA'].map_entry_nr(v)
            fout.write(f" - {k} -> {v}\n")


@shared_task(soft_time_limit=800)
def go_enrichment(id):
    t0 = time.time()
    logger.info(f"starting go enrichment job {id}")
    obj = EnrichmentAnalysisModel.objects.get(id=id)
    obj.state = "RUNNING"
    obj.save()

    logger.info(obj.foreground)
    logger.info(f"Foreground ({len(obj.foreground)} elements)")
    try:
        if obj.type == "ancestral":
            go_res, mapping = compute_ancestral_enrichment(obj)
        else:
            go_res, mapping = compute_extant_enrichment(obj)
    except Exception as e:
        logger.exception('error while computing go_enrichment_analysis for dataset: {}'
                         .format(obj.id))
        obj.state = 'ERROR'
        obj.message = str(e)
        obj.save()
        return False

    name = _generate_media_filepath_stub(obj)
    analysis_name = os.path.basename(name)
    data_json = {}
    with tempfile.TemporaryDirectory(prefix=f"{analysis_name}-") as tmpdir:
        with open(os.path.join(tmpdir, analysis_name+".tsv"), 'wt') as fout:
            go_res.to_csv(fout, index=False, sep="\t")
        write_parameters_file(os.path.join(tmpdir, "input_parameters.txt"), obj, mapping)
        data_json['enrichment'] = go_res.to_dict()
        try:
            plot_dfs = generate_plots(go_res, utils.db, tmpdir, pval_col="p_fdr_bh")
            emb = {}
            for aspect, df in plot_dfs.items():
                emb[aspect] = df.to_dict()
            data_json['embedding'] = emb
        except Exception as e:
            logger.exception("plotting failed")

        path = os.path.join(settings.MEDIA_ROOT, name)
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        with tarfile.open(path+"-result.tgz", 'w:gz') as tar:
            tar.add(tmpdir, arcname=analysis_name)
        with open(path+".json", 'wt') as fout:
            json.dump(data_json, fout)


    tot_time = time.time() - t0
    obj.result = name + "-result.tgz"
    obj.result_json = name + ".json"
    obj.compute_time = tot_time
    obj.state = 'DONE'
    logger.info('finished go enrichment analysis. took {:.3f}sec'.format(tot_time))

    obj.save()
