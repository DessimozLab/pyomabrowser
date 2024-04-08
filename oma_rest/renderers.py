from rest_framework_csv import renderers
import logging
logger = logging.getLogger(__name__)


class TSVRenderer(renderers.CSVRenderer):
    media_type = "text/tsv"
    format = "tsv"
    writer_opts = {"dialect": "excel-tab"}

    def render(self, data, media_type=None, renderer_context={}, writer_opts=None):
        return super().render(data, media_type=media_type, renderer_context=renderer_context, writer_opts=self.writer_opts)
