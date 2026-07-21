import logging

from django.http import Http404
from django.shortcuts import redirect

from .models import DownloadEvent, Release, ReleaseFile

logger = logging.getLogger(__name__)


def _serve_releasefile_redirect(request, release, filename):
    try:
        release_file = release.files.get(filename=filename)
    except ReleaseFile.DoesNotExist:
        raise Http404
    if not release_file.download_url:
        # File is registered as locally-served; nginx should have handled it.
        # If we reach here (e.g. in dev without nginx), there's nothing to redirect to.
        raise Http404
    DownloadEvent.objects.create(file=release_file)
    logger.info("Redirecting download: %s/%s -> %s", release.name, filename, release_file.download_url)
    response = redirect(release_file.download_url)
    response["Access-Control-Allow-Origin"] = "*"
    return response


def download_latest(request, filename):
    try:
        release = Release.objects.get(release_group='All', is_latest=True)
    except Release.DoesNotExist:
        raise Http404("No latest release configured for group 'All'")
    return _serve_releasefile_redirect(request, release, filename)


def download_release(request, release_name, filename):
    try:
        release = Release.objects.get(name=release_name)
    except Release.DoesNotExist:
        raise Http404(f"Release {release_name!r} not found")
    return _serve_releasefile_redirect(request, release, filename)
