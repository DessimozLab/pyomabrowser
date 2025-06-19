from django.urls import reverse
from django.http import HttpResponseRedirect, Http404
from django.shortcuts import render
from django.conf import settings
import hashlib
import os
import json
import logging

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import TemplateView

from .models import StandaloneExportJobs
from .tasks import submit_export, run_fastoma_export
from oma.utils import db
logger = logging.getLogger(__name__)


def str_to_bool(v):
    return v.lower() in ("yes", "true", "t", "on", "1")


# Create your views here.
def export_omastandalone(request):
    if request.method == 'GET' and 'genomes' in request.GET:
        genomes = sorted(request.GET.getlist('genomes'))
        if 2 <= len(genomes) <= 50:
            data_id = hashlib.md5(str(genomes).encode('utf-8')).hexdigest()
            try:
                r = StandaloneExportJobs.objects.get(data_hash=data_id)
                do_compute = r.remove_erroneous_or_long_pending()
            except StandaloneExportJobs.DoesNotExist:
                do_compute = True

            logger.info("Export job with {} genomes ({}). Compute: {}"
                        .format(len(genomes), genomes, do_compute))
            if do_compute:
                genomes_as_txt = json.dumps(genomes)
                res_file_rel = os.path.join("AllAllExport", "AllAll-{}.tgz".format(data_id))
                release = db.get_release_name()
                logger.info("Export job for %s, hash: %s, result: %s", release, data_id, res_file_rel)
                # create, but not save the job. saving is done by submit_export once engine is determined
                r = StandaloneExportJobs(data_hash=data_id, result=res_file_rel, state="pending",
                                         genomes=genomes_as_txt, processing=False)
                submit_export(r, genomes, release=release)
            return HttpResponseRedirect(reverse('export-download', args=(data_id,)))
    return render(request, "dlOMA_exportAllAll.html", context={'max_nr_genomes': 50})

@method_decorator(never_cache, name='dispatch')
class StandaloneExportResultDownloader(TemplateView):
    template_name = "export_download.html"
    reload_frequency = 20

    def get_context_data(self, data_id, **kwargs):
        context = super(StandaloneExportResultDownloader, self).get_context_data(**kwargs)
        try:
            result = StandaloneExportJobs.objects.get(data_hash=data_id)
        except StandaloneExportJobs.DoesNotExist:
            raise Http404('Invalid dataset')
        context['file_result'] = result
        context['genomes'] = json.loads(result.genomes)
        context['reload_every_x_sec'] = self.reload_frequency
        context['days_stored_before_remove'] = settings.EXPORT_OMA.get('store_files_in_days', 7)
        return context


class FastOMAExportResultDownloader(StandaloneExportResultDownloader):
    template_name = "fastoma_download.html"


def export_fastoma(request):
    if request.method == 'GET' and 'genomes' in request.GET:
        genomes = sorted(request.GET.getlist('genomes'))
        allow_huge = str_to_bool(request.GET.get('allow_huge', 'false'))
        if 1 <= len(genomes) and (len(genomes) <= 250 or allow_huge):
            data_id = hashlib.md5(b"fastoma" + str(genomes).encode('utf-8')).hexdigest()
            try:
                r = StandaloneExportJobs.objects.get(data_hash=data_id)
                do_compute = r.remove_erroneous_or_long_pending()
            except StandaloneExportJobs.DoesNotExist:
                do_compute = True

            logger.info("FastOMA Export job with {} genomes ({}). Compute: {}"
                        .format(len(genomes), genomes, do_compute))
            if do_compute:
                genomes_as_txt = json.dumps(genomes)
                res_file_rel = os.path.join("FastOMA", "FastOMA-{}.tgz".format(data_id))
                release = db.get_release_name()
                logger.info("FastOMA Export job for %s, hash: %s, result: %s", release, data_id, res_file_rel)
                # create, but not save the job. saving is done by submit_export once engine is determined
                r = StandaloneExportJobs(data_hash=data_id, result=res_file_rel, state="pending",
                                         genomes=genomes_as_txt, processing=False)
                r.save()
                run_fastoma_export.delay(r, genomes, release=release)
            return HttpResponseRedirect(reverse('fastoma-export-download', args=(data_id,)))
    return render(request, "dlOMA_exportFastOMA.html", context={'max_nr_genomes': 250})
