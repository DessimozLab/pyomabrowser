import time
from .base import FunctionalTest
import requests


class DownloadPagesTester(FunctionalTest):

    def check_all_link_exist_on_page(self):
        # iterate over all anchor tags within the "container" div
        for anchor in self.browser.find_elements_by_xpath('//div[@class="container"]//a'):
            url = anchor.get_property('href')
            # for performance reason we won't download the file but
            # just stat it with head using requests
            resp = requests.head(url)
            self.assertEqual(200, resp.status_code, "cannot stat {}".format(url))

    def test_current_release_downloads(self):
        # we navigate to the download section from the landing page on
        self.browser.get(self.server_url)
        self.browser.find_element_by_link_text("Download").click()
        self.browser.find_element_by_link_text("Current release").click()
        self.check_all_link_exist_on_page()
