import time
import logging
from django.utils.deprecation import MiddlewareMixin
from pyoma.browser.db import OutdatedHogId
from . import utils
from django.shortcuts import redirect, resolve_url
from django.template.response import TemplateResponse
logger = logging.getLogger(__name__)


class LongRunningLogger(object):
    def __init__(self, get_response=None):
        self.get_response = get_response

    def __call__(self, request):
        t0 = time.time()
        response = self.get_response(request)
        t1 = time.time()
        if t1 - t0 > 10:
            logger.warning("long running request: {:.2f}sec: {}".format(t1 - t0, request))
        return response


class OutdatedHogIdRedirector(MiddlewareMixin):

    def process_exception(self, request, exception):
        if isinstance(exception, OutdatedHogId):
            try:
                candidates = utils.hogid_forward_mapper.map_hogid(exception.outdated_hog_id)
            except AttributeError:
                candidates = {}

            target_view_name = request.resolver_match.view_name
            if len(candidates) == 1:
                new_hogid, jaccard = candidates.popitem()
                logger.info("redirect view '{}' with old hog request {} -> {}"
                            .format(target_view_name, exception.outdated_hog_id.decode(), new_hogid))
                return redirect(request.resolver_match.view_name, new_hogid)

            new_hogs = []
            for new_id, jaccard in candidates.items():
                h = utils.HOG(utils.db.get_hog(new_id))
                h.jaccard = jaccard
                h.redirect_url = resolve_url(target_view_name, h.hog_id)
                new_hogs.append(h)
            new_hogs.sort(key=lambda h: -h.jaccard)
            context = {"outdated_hog_id": exception.outdated_hog_id.decode(),
                       "candidate_hogs": new_hogs,
                       }
            return TemplateResponse(request, template="outdated_hog.html", context=context)