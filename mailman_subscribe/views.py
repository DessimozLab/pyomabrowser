from django.http import JsonResponse, HttpResponseRedirect
from django import forms
from django.urls import reverse
from captcha.fields import ReCaptchaField
from . import tasks

import logging
logger = logging.getLogger(__name__)



class MailmanForm(forms.Form):
    email = forms.EmailField(label="Email", required=True)
    captcha = ReCaptchaField()


# Create your views here.
def subscribe(request):
    if request.method == "POST":
        form = MailmanForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            logger.info("sending subscription email with async task...")
            tasks.subscribe_to_mailing_list.delay(data['email'])
            return HttpResponseRedirect(reverse('mailman-thanks'))
        logger.warning(f"form data is not valid: {form}")
    return HttpResponseRedirect(reverse('home'))
