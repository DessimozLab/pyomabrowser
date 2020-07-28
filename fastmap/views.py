from django.shortcuts import render
from django.urls import reverse
from . import views
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control, never_cache
from django.views.generic import TemplateView, View
from django.http import HttpResponseRedirect, Http404
from django.conf import settings
from . import forms

from .models import FastMappingJobs
from .tasks import submit_mapping
from oma import misc
import hashlib
import os
import json



# Create your views here.
def fastmapping(request):

    if request.method == 'POST':

        form = forms.FastMappingUploadForm(request.POST, request.FILES)

        if form.is_valid():

            print(request.FILES['file'])

            user_file_info = misc.handle_uploaded_file(request.FILES['file'])
            data_id = hashlib.md5(user_file_info['md5'].encode('utf-8')).hexdigest()

            try:
                r = FastMappingJobs.objects.get(data_hash=data_id)
                do_compute = r.remove_erroneous_or_long_pending()
            except FastMappingJobs.DoesNotExist:
                do_compute = True

            if do_compute:
                res_file_rel = os.path.join("FastMappingExport", "FastMapping-{}.tgz".format(data_id))
                res_file_abs = os.path.join(settings.MEDIA_ROOT, res_file_rel)
                res = submit_mapping(data_id, res_file_abs, user_file_info['fname'])
                r = FastMappingJobs(data_hash=data_id, state=res.state, result=res_file_rel,
                                         fasta=request.FILES['file'], processing=False)
                r.save()
            return HttpResponseRedirect(reverse('fastmapping-download', args=(data_id,)))

    else:
        form = forms.FastMappingUploadForm()

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
        context['fasta'] = json.loads(result.fasta)
        context['reload_every_x_sec'] = self.reload_frequency
        return context