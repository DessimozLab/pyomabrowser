from django.conf import settings # import the settings file
from .utils import id_mapper


def xref_order(request):
    # provide xref_order variable in every template
    return {'xref_order': id_mapper['Xref'].canonical_source_order()}


def oma_instance(request):
    # return the value you want as a dictionnary. you may add multiple values in there.
    res = {'oma_instance_name': settings.OMA_INSTANCE_NAME}
    try:
        res['google_tracker_code'] = settings.GOOGLE_ANALYTICS['google_analytics_id']
    except AttributeError:
        pass
    return res


def oma_academy(request):
    if 'academy' in settings.INSTALLED_APPS:
        return {'oma_academy': True}
    return {'oma_academy': False}
