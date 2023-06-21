import gzip
import json
import time
import os
from oma import utils
from .models import EnrichmentAnalysisModel
from django.conf import settings
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from pyoma.application.enrichment import ancestral_species_go_enrichment, extent_species_go_enrichment
from pyoma.browser.models import ProteinEntry
from pyoma.browser.exceptions import AmbiguousID, InvalidId

import logging
logger = logging.getLogger(__name__)

def _generate_media_filepath(obj):
    basename = f"GOEA-{obj.data_hash}-result.tsv.gz"
    return os.path.join("go_enrichment", obj.data_hash[-2:], obj.data_hash[-4:-2], basename)


@shared_task(soft_time_limit=800)
def go_enrichment(id):
    t0 = time.time()
    logger.info(f"starting go enrichment job {id}")
    obj = EnrichmentAnalysisModel.objects.get(id=id)
    obj.state = "RUNNING"
    obj.save()

    name = _generate_media_filepath(obj)
    path = os.path.join(settings.MEDIA_ROOT, name)
    logger.info(obj.foreground)
    foreground = obj.foreground
    logger.info(f"Foreground ({len(foreground)} elements)")
    try:
        if obj.type == "ancestral":
            level = obj.taxlevel
            logger.debug(f"ancestral enrichment on level {level}")
            hogs = {}
            for elem in foreground:
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
            go_res = ancestral_species_go_enrichment(utils.db, level=level, foreground_hogs=set(hogs.values()) - {None})
        else:
            entries = {}
            for entry in foreground:
                try:
                    entries[entry] = utils.id_resolver.resolve(entry)
                except (AmbiguousID, InvalidId) as e:
                    entries[entry] = None
            logger.info(f"mapping: {entries}")
            logger.debug(f"extend species enrichment")
            go_res = extent_species_go_enrichment(utils.db, foreground_entries=set(entries.values()) - {None})

        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        with gzip.open(path, 'wt') as fout:
            go_res.to_csv(fout, sep="\t")

        tot_time = time.time() - t0
        obj.result = name
        obj.compute_time = tot_time
        obj.state = 'DONE'
        logger.info('finished go enrichment analysis. took {:.3f}sec'.format(tot_time))
    except Exception as e:
        logger.exception('error while computing go_enrichment_analysis for dataset: {}'
                         .format(obj.id))
        obj.state = 'ERROR'
        obj.message = str(e)
    obj.save()
