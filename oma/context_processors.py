from django.conf import settings  # import the settings file
from .utils import id_mapper


def xref_order(request):
    # provide xref_order variable in every template
    return {"xref_order": id_mapper["Xref"].canonical_source_order()}


def oma_instance(request):
    # return the value you want as a dictionnary. you may add multiple values in there.
    res = {
        "oma_instance_name": settings.OMA_INSTANCE_NAME,
        "oma_academy_enabled": "academy" in settings.INSTALLED_APPS,
        "fastmap_enabled": "fastmap" in settings.INSTALLED_APPS,
        "export_enabled": "export" in settings.INSTALLED_APPS,
    }
    try:
        res["google_tracker_code"] = settings.GOOGLE_ANALYTICS["google_analytics_id"]
    except AttributeError:
        pass
    return res
