from django import forms
from captcha.fields import ReCaptchaField


class FellowshipApplicationForm(forms.Form):
    name = forms.CharField(label="Name", required=True)
    email = forms.EmailField(label="Email", required=True)
    interest = forms.CharField(widget=forms.Textarea(attrs={'rows': "10", }),
                               label="Statement of interest", required=False)
    interestAsFile = forms.FileField(label="or as PDF")
    cvAsFile = forms.FileField(label="CV", required=True)


class GenomeSuggestionFrom(forms.Form):
    required_css_class = 'required'
    taxon_id = forms.IntegerField(label="NCBI Taxonomy Identifier", required=True)
    name = forms.CharField(label="Species Name", required=False)
    new_or_update = forms.ChoiceField(label="Update or New Genome?",
                                      choices=[('new', "New Genome"), ('update', "Update of existing Genome")])
    info = forms.URLField(label="Genome Information page", required=False)
    source = forms.URLField(label="Genome Source URL", required=True)
    formats = forms.MultipleChoiceField(label="Available Formats",
                                        choices=[('EMBL', 'EMBL'), ('GenBank', 'Genbank'),
                                                 ('fasta', 'Fasta & GFF'), ('other', "Other Format")])
    quality = forms.CharField(widget=forms.Textarea(
                                attrs={"rows": "3",
                                       "placeholder": "Any known quality measure, e.g. N50 length, BUSCO score, ..."}),
                              label="Genome Quality Measures", required=False)
    reason = forms.CharField(widget=forms.Textarea(
                                attrs={'rows': "5",
                                       'placeholder': "Briefly explain why this genome is important, "
                                                      "e.g. underrepresented clade, model organism, ..."}),
                             label="Reason / Interest for Inclusion")

    suggested_from_name = forms.CharField(label="Your Name", required=True)
    suggested_from_email = forms.EmailField(label="Your Email", required=True)
    captcha = ReCaptchaField()


class FunctionProjectionUploadForm(forms.Form):
    required_css_class = 'required'
    email = forms.EmailField(label='Email')
    dataset = forms.CharField(label='Description of Dataset', max_length=50)
    file = forms.FileField(label='Sequence File (fasta format)', required=True)
    #tax_limit = forms.IntegerField(label="Limit Taxonomic Clade", required=False, initial=2,
    #                               help_text="The NCBI Taxonomic ID of the clade from which "
    #                                         "functions are propagated.")
    captcha = ReCaptchaField()
