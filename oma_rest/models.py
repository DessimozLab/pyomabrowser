class HOG(object):
    def __init__(self, hog_id=None, level=None, **kwargs):
        self.hog_id = hog_id
        self.level = level
        for k, v in kwargs.items():
            setattr(self, k, v)
        if hog_id is not None:
            start = hog_id.find(':') + 1
            end = hog_id.find('.')
            if end >= 0:
                self.roothog_id = int(hog_id[start:end])
            else:
                self.roothog_id = int(hog_id[start:])


class OMAGroup(object):
    def __init__(self, GroupNr=None, fingerprint=None, members=None, **kwargs):
        self.GroupNr = GroupNr
        self.fingerprint = fingerprint
        self.members = members
        for k, v in kwargs.items():
            setattr(self, k, v)