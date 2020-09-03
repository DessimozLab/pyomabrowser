import drf_link_header_pagination
import pyoma.browser.db
from rest_framework.settings import api_settings
import itertools


class LinkHeaderPagination(drf_link_header_pagination.LinkHeaderPagination):
    page_size_query_param = 'per_page'
    max_page_size = 10000000

    def get_paginated_response(self, data):
        response = super(LinkHeaderPagination, self).get_paginated_response(data)
        response['X-Total-Count'] = self.page.paginator.count
        return response


class PaginationMixin(object):
    pagination_class = api_settings.DEFAULT_PAGINATION_CLASS

    @property
    def paginator(self):
        """
        The paginator instance associated with the view, or `None`.
        """
        if not hasattr(self, '_paginator'):
            if self.pagination_class is None:
                self._paginator = None
            else:
                self._paginator = self.pagination_class()
        return self._paginator


class LazyPagedPytablesQuery(object):
    def __init__(self, table, query=None, obj_factory=None):
        self.tab = table
        self.query = query
        self.obj_factory = obj_factory
        self._total_cnt = None

    def count(self):
        if self._total_cnt is None:
            if self.query is not None:
                self._total_cnt = pyoma.browser.db.count_elements(self.tab.where(self.query))
            else:
                self._total_cnt = len(self.tab)
        return self._total_cnt

    def __getitem__(self, item):
        if isinstance(item, slice):
            it = self.tab.where(self.query)
            for row in itertools.islice(it, item.start, item.stop, item.step):
                if self.obj_factory is not None:
                    inst = self.obj_factory(row.fetch_all_fields())
                    if inst is not None:
                        yield inst
                else:
                    yield row.fetch_all_fields()