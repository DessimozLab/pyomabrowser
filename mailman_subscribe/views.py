from django.http import JsonResponse, HttpResponseRedirect
from django import forms
from django.urls import reverse
from . import tasks

import logging
logger = logging.getLogger(__name__)



class EmailForm(forms.Form):
    email = forms.EmailField(label="Email", required=True)


# Create your views here.
def subscribe(request):
    if request.method == "POST":
        form = EmailForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            logger.error("sending email...")
            tasks.subscribe_to_mailing_list.delay(data['email'])
            return HttpResponseRedirect(reverse('mailman-thanks'))
    return HttpResponseRedirect(reverse('home'))
