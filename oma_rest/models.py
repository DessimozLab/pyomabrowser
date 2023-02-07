from rest_framework.exceptions import APIException, status
import re
import random
re_hogid = re.compile(r"HOG:(?P<rel>[A-Z]*)(?P<fam>\d+)(?P<subhog>[a-z0-9.]+)?")


class HOG(object):
    def __init__(self, hog_id=None, **kwargs):
        self.hog_id = hog_id
        for k, v in kwargs.items():
            setattr(self, k, v)
        if hog_id is not None:
            m = re_hogid.match(hog_id)
            self.roothog_id = int(m.group("fam"))


class OMAGroup(object):
    def __init__(self, GroupNr=None, fingerprint=None, members=None, **kwargs):
        self.GroupNr = GroupNr
        self.fingerprint = fingerprint
        self.members = members
        for k, v in kwargs.items():
            setattr(self, k, v)


class IdGoneException(APIException):
    status_code = status.HTTP_410_GONE
    default_detail = 'ID {outdated} is no longer valid.'
    default_code = 'id_gone'

    def __init__(self, outdated, replacements=None, detail=None, code=None):
        if detail is None:
            detail = self.default_detail.format(outdated=outdated)
        if replacements is not None:
            self.replacement_ids = replacements
        super(IdGoneException, self).__init__(detail, code)