import time
from .base import FunctionalTest


class RestAPI(FunctionalTest):

    def test_xref_with_alternative_splicing_variant(self):
        """test for https://trello.com/c/Aj3WJT5J

        check that for an example where we have an alternative splice variant
        with the same uniprot id (this can happen for swissprot entries)
        we return the canonical variant of OMA"""
        query = "Q6W5P4"
        self.browser.get('{}/api/protein/{}/orthologs/'.format(self.server_url, query))
        self.assertIn("<h1>Protein Entry</h1>", self.browser.page_source)