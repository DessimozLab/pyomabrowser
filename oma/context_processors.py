from django.conf import settings  # import the settings file


def oma_instance(request):
    # return the value you want as a dictionnary. you may add multiple values in there.
    return {'oma_instance_name': settings.OMA_INSTANCE_NAME,
            'google_tracker_code': settings.GOOGLE_ANALYTICS['google_analytics_id'],
            }