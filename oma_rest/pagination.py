import drf_link_header_pagination
from rest_framework.settings import api_settings


class LinkHeaderPagination(drf_link_header_pagination.LinkHeaderPagination):
    page_size_query_param = 'per_page'
    max_page_size = 10000

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
