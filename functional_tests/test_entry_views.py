from .base import FunctionalTest


class EntryViewPageTest(FunctionalTest):

    def test_wheat_pages_for_homeologs(self):
        # Cecile navigates to OMA Browser page
        self.browser.get(self.server_url)

        # she wants to search for her favorite wheat gene - W4ZUH7
        # she first finds the search field
        query = 'W4ZUH7'
        inputbox = self.browser.find_element_by_id('inputBrowser')
        # she enters the query gene into it, and presses enter
        inputbox.send_keys('{}\n'.format(query))
        # she gets a page with lot of information, in the title is the query gene id
        self.assertIn(query, self.browser.find_element_by_partial_link_text(query).text)

        # she knows that wheat is a polyploid genome and expects to find a tab on Homeologs
        tab_lnks = self.browser.find_elements_by_css_selector('.nav-tabs>li>a')
        self.assertIn('Homeologs', "".join([tab.text for tab in tab_lnks]))

        # is this also true if she starts from a django served page?
        synteny_lnks = [lnk for lnk in tab_lnks if 'Synteny' in lnk.text]
        self.assertEqual(1, len(synteny_lnks))
        synteny_lnks[0].click()
        tab_lnks = self.browser.find_elements_by_css_selector('.nav-tabs>li>a')
        self.assertIn('Homeologs', "".join([tab.text for tab in tab_lnks]))

    def test_human_pages(self):
        # Cecile now want's to verify that on non-polyploid genomes there are no homeologs
        self.browser.get(self.server_url+'/oma/hogs/P53_HUMAN')
        tab_lnks = self.browser.find_elements_by_css_selector('.nav-tabs>li>a')
        self.assertNotIn('Homeologs', "".join([tab.text for tab in tab_lnks]))