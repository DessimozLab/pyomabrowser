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
from .tasks import submit_export
from oma.utils import db
logger = logging.getLogger(__name__)


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
                res_file_abs = os.path.join(settings.MEDIA_ROOT, res_file_rel)
                release = db.get_release_name()
                logger.info("Export job for {}, hash: {}, result: {}".format(release, data_id, res_file_abs))
                res = submit_export(data_id, res_file_abs, genomes, release=release)
                r = StandaloneExportJobs(data_hash=data_id, state=res.state, result=res_file_rel,
                                         genomes=genomes_as_txt, processing=False)
                r.save()
            return HttpResponseRedirect(reverse('export-download', args=(data_id,)))
    return render(request, "export.html", context={'max_nr_genomes': 50})


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
        return context
