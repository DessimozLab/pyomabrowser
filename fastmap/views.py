from django.shortcuts import render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control, never_cache
from django.views.generic import TemplateView
from django.http import HttpResponseRedirect, Http404
from django.conf import settings
from . import forms
from .models import FastMappingJobs
from .tasks import submit_mapping
from oma import misc
import os
import hashlib
import logging
logger = logging.getLogger(__name__)


if 'captcha' in settings.INSTALLED_APPS:
    fastmap_form_cls = forms.FastMappingUploadForm
else:
    fastmap_form_cls = forms.FastMappingUploadFormWithoutReCaptcha


# Create your views here.
def fastmapping(request):
    if request.method == 'POST':
        form = fastmap_form_cls(request.POST, request.FILES)
        if form.is_valid():
            upload_dir = os.path.join(settings.MEDIA_ROOT, "uploads")
            user_file_info = misc.handle_uploaded_file(request.FILES['file'], dir=upload_dir)
            map_method = form.cleaned_data['map_method']
            target = form.cleaned_data['target']
            job_name = form.cleaned_data['name']
            email = form.cleaned_data['email']
            h = hashlib.md5(user_file_info['md5'].encode('utf-8'))
            h.update(map_method.encode('utf-8'))
            h.update(target.encode('utf-8'))
            data_id = h.hexdigest()

            try:
                r = FastMappingJobs.objects.get(data_hash=data_id)
                do_compute = r.remove_erroneous_or_long_pending()
            except FastMappingJobs.DoesNotExist:
                do_compute = True
            logger.info(f"received fasta file {request.FILES['file']} for fastmapping: map_method {map_method}, hash {data_id}, need computing: {do_compute}")
            result_page_url = reverse('fastmapping-download', args=(data_id,))
            if do_compute:
                res_file_rel = os.path.join("FastMappingExport", "FastMapping-{}.txt.gz".format(data_id))
                # instantiate job, but don't save so far
                job = FastMappingJobs(data_hash=data_id, state="pending", result=res_file_rel,
                                      map_method=map_method, fasta=os.path.basename(user_file_info['fname']),
                                      name=job_name, email=email, processing=False,
                                      result_url=request.build_absolute_uri(result_page_url))
                submit_mapping(job, user_file_info['fname'], map_method, target)
            return HttpResponseRedirect(reverse('fastmapping-download', args=(data_id,)))

    else:
        form = fastmap_form_cls()

    return render(request, "fastmapping.html",
                  {'form': form, 'max_upload_size': form.fields['file'].max_upload_size / (2**20)})



@method_decorator(never_cache, name='dispatch')
class FastMappingResultDownloader(TemplateView):

    template_name = "fastmapping_download.html"
    reload_frequency = 20

    def get_context_data(self, data_id, **kwargs):
        context = super(FastMappingResultDownloader, self).get_context_data(**kwargs)
        try:
            result = FastMappingJobs.objects.get(data_hash=data_id)
        except FastMappingJobs.DoesNotExist:
            raise Http404('Invalid dataset')
        context['file_result'] = result
        context['fasta'] = result.fasta
        context['reload_every_x_sec'] = self.reload_frequency
        return context