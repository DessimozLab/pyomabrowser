from django.conf import settings  # import the settings file
from .utils import id_mapper, db

def release_info(request):
    # provide release information in every template
    return {"release_char": db.release_char,
            "oma_release": db.get_release_name(),
           }

def xref_order(request):
    # provide xref_order variable in every template
    return {"xref_order": id_mapper["Xref"].canonical_source_order()}


def oma_instance(request):
    # return the value you want as a dictionary. you may add multiple values in there.
    res = {
        "oma_instance_name": settings.OMA_INSTANCE_NAME,
        "oma_academy_enabled": "academy" in settings.INSTALLED_APPS,
        "fastmap_enabled": "fastmap" in settings.INSTALLED_APPS,
        "export_enabled": "export" in settings.INSTALLED_APPS,
        "omamo_enabled": "omamo" in settings.INSTALLED_APPS,
        "matomo_tracker_code": "matomo_api_tracking" in settings.INSTALLED_APPS,
    }
    return res
