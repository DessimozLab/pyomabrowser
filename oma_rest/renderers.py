from rest_framework_csv.renderers import CSVRenderer
from rest_framework.renderers import BaseRenderer
import logging
logger = logging.getLogger(__name__)


class NewickRenderer(BaseRenderer):
    media_type = 'application/x-newick'
    format = 'newick'
    charset = 'utf-8'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if isinstance(data, dict) and "newick" in data:
            data = data["newick"]
        if isinstance(data, str):
            return data.encode(self.charset)
        return data


class NewickTextNhRenderer(NewickRenderer):
    """Alias for clients sending ``Accept: text/x-nh``."""
    media_type = 'text/x-nh'


class PhyloXMLRenderer(BaseRenderer):
    media_type = 'application/vnd.phyloxml+xml'
    format = 'phyloxml'
    charset = 'utf-8'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if isinstance(data, str):
            return data.encode(self.charset)
        return data


class PhyloXMLLegacyRenderer(PhyloXMLRenderer):
    """Alias for clients sending ``Accept: application/xml``."""
    media_type = 'application/xml'


class TSVRenderer(CSVRenderer):
    media_type = "text/tsv"
    format = "tsv"
    writer_opts = {"dialect": "excel-tab"}

    def render(self, data, media_type=None, renderer_context={}, writer_opts=None):
        return super().render(data, media_type=media_type, renderer_context=renderer_context, writer_opts=self.writer_opts)
