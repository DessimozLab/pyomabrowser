from django import forms


class FellowshipApplicationForm(forms.Form):
    name = forms.CharField(label="Name", required=True)
    email = forms.EmailField(label="Email", required=True)
    interest = forms.CharField(widget=forms.Textarea(attrs={'rows': "10", }),
                               label="Statement of interest", required=False)
    interestAsFile = forms.FileField(label="or as PDF")
    cvAsFile = forms.FileField(label="CV", required=True)


class GenomeSuggestionFrom(forms.Form):
    taxon_id = forms.IntegerField(label="NCBI Taxonomy Identifier", required=True)
    name = forms.CharField(label="Genome Name")
    new_or_update = forms.ChoiceField(label="Update or New Genome?",
                                      choices=[('new', "New Genome"), ('update', "Update of existing Genome")])
    info = forms.URLField(label="Genome Information page")
    source = forms.URLField(label="Genome Source URL", required=True)
    formats = forms.MultipleChoiceField(label="Available Formats",
                                        choices=[('EMBL', 'EMBL'), ('GenBank', 'Genbank'),
                                                 ('fasta', 'Fasta & GFF'), ('other', "Other Format")])
    quality = forms.CharField(widget=forms.Textarea(attrs={'rows': "3", }),
                              label="Genome Quality Measures")
    reason = forms.CharField(widget=forms.Textarea(attrs={'rows': "5", }),
                             label="Reason / Interest for Inclusion")

    suggested_from_name = forms.CharField(label="Your Name", required=True)
    suggested_from_email = forms.EmailField(label="Your Email", required=True)
