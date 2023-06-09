from django import forms
from captcha.fields import ReCaptchaField
from django.template.defaultfilters import filesizeformat
from django.conf import settings
from .models import FastMappingJobs


class RestrictedFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        self.max_upload_size = kwargs.pop('max_upload_size', None)
        if not self.max_upload_size:
            self.max_upload_size = settings.MAX_UPLOAD_SIZE
        super(RestrictedFileField, self).__init__(*args, **kwargs)

    def clean(self, *args, **kwargs):
        data = super(RestrictedFileField, self).clean(*args, **kwargs)
        try:
            if data.size > self.max_upload_size:
               raise forms.ValidationError('File size must be under {}. Current file size is {}.'
                                           .format(filesizeformat(self.max_upload_size), filesizeformat(data.size)))
        except AttributeError:
            pass
        return data


class FastMappingUploadFormWithoutReCaptcha(forms.Form):
    required_css_class = 'required'
    email = forms.EmailField(label='Email', required=False,
                             help_text="We will send an email to this address once the predictions are ready.")
    name = forms.CharField(label='Name of Dataset', max_length=64, required=False)
    map_method = forms.ChoiceField(label="Mapping method", choices=FastMappingJobs.MAP_METHODS, required=True)
    target = forms.CharField(label="Mapping restricted to target", max_length=5, required=False)
    file = RestrictedFileField(label='Sequence File (fasta format)', required=True)


class FastMappingUploadForm(FastMappingUploadFormWithoutReCaptcha):
    captcha = ReCaptchaField()