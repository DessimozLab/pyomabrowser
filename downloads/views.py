import logging

from django.http import Http404
from django.shortcuts import redirect

from .models import DownloadEvent, Release, ZenodoFile

logger = logging.getLogger(__name__)


def _serve_zenodo_redirect(request, release, filename):
    try:
        zenodo_file = release.files.get(filename=filename)
    except ZenodoFile.DoesNotExist:
        raise Http404
    DownloadEvent.objects.create(file=zenodo_file)
    logger.info("Redirecting download: %s/%s -> %s", release.name, filename, zenodo_file.zenodo_url)
    return redirect(zenodo_file.zenodo_url)


def download_latest(request, filename):
    try:
        release = Release.objects.get(release_group='All', is_latest=True)
    except Release.DoesNotExist:
        raise Http404("No latest release configured for group 'All'")
    return _serve_zenodo_redirect(request, release, filename)


def download_release(request, release_name, filename):
    try:
        release = Release.objects.get(name=release_name)
    except Release.DoesNotExist:
        raise Http404(f"Release {release_name!r} not found")
    return _serve_zenodo_redirect(request, release, filename)
