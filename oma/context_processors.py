from django.conf import settings # import the settings file
from .utils import id_mapper


def xref_order(request):
    # provide xref_order variable in every template
    return {'xref_order': id_mapper['Xref'].canonical_source_order()}


def oma_instance_name(request):
    # return the value you want as a dictionnary. you may add multiple values in there.
    return {'oma_instance_name': settings.OMA_INSTANCE_NAME}
