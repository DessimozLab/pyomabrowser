from django import forms

class FellowshipApplicationForm(forms.Form):
    name = forms.CharField(label="Name", required=True)
    email = forms.EmailField(label="Email", required=True)
    interest = forms.CharField(widget=forms.Textarea(attrs={'rows': "10", }),
                               label="Statement of interest", required=False)
    interestAsFile = forms.FileField(label="or as PDF")
    cvAsFile = forms.FileField(label="CV", required=True)
