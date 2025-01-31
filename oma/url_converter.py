import urllib.parse


class LevelConverter:
    regex = r"[A-Za-z0-9 _.()-/:]+"

    def to_python(self, value):
        return urllib.parse.unquote(value)

    def to_url(self, value):
        return str(value)


class HogIdConverter:
    # regex = r"(?P<id>HOG:(?P<rel>[A-Z]+)?(?P<fam>\d+)(?:[a-z0-9.]*))(?:_(?P<taxid>-?\d+))?"
    regex = "(HOG:)?([A-Z]+)?\d+(?:[a-z0-9.]*)(?:_(-?\d+))?"

    def to_python(self, value):
        return str(value)

    def to_url(self, value):
        return str(value)