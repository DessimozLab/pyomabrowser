import time
import logging
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
