from .base import FunctionalTest
import logging


class EntryViewPageTest(FunctionalTest):

    def test_wheat_pages_for_homeologs(self):
        # Cecile navigates to OMA Browser page
        self.browser.get(self.server_url)

        # she wants to search for her favorite wheat gene - A0A1D5VN70
        # she first finds the search field
        query = 'A0A1D5VN70'
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

    def test_synteny_page(self):
        # Tom navigates via the info page of the P53_HUMAN info page to the synteny page
        self.browser.get(self.server_url + '/oma/synteny/P53_HUMAN')
        # we make sure the second title row (thead) belongs to HUMAN
        tds_of_first_row = self.browser.find_elements_by_xpath("//div[@class='twotables']//table/thead/tr[2]/td")
        self.assertEqual('HUMAN', tds_of_first_row[0].text)
        # let's check that the rows are in a reasonable taxonomic order. they shoudl be
        # ordered according to the distance on the lineagetree from HUMAN
        species_column = [g.text for g in self.browser.find_elements_by_xpath("//div[@class='twotables']//table/tbody/tr/td[1]")]
        self.assertLess(5, len(species_column), 'Too few genomes containing P53 orthologs')
        row_nr_of_species = []
        for g in ('PANTR', 'PONAB', 'MACMU', 'MOUSE', 'BOVIN', 'MONDO'):
            try:
                pos = species_column.index(g)
            except ValueError:
                pos = -1
                logging.error('{} not in list of species of syntenic genes'.format(g))
            row_nr_of_species.append(pos)
        self.assertTrue(all(row_nr_of_species[i] < row_nr_of_species[i + 1] for i in range(len(row_nr_of_species) - 1)))
