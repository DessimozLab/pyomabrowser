import time
from .base import FunctionalTest


class EntryViewPageTest(FunctionalTest):

    def test_wheat_pages_for_homeologs(self):
        # Cecile navigates to OMA Browser page
        self.browser.get(self.server_url)

        # she wants to search for her favorite wheat gene - AVLA1_WHEAT
        # she first finds the search field
        query = 'AVLA1_WHEAT'
        inputbox = self.browser.find_element_by_id('inputBrowser')
        # she enters the query gene into it, and presses enter
        inputbox.send_keys('{}\n'.format(query))
        # she gets a page with lot of information, in the title is the query gene id
        self.assertIn(query, self.browser.find_element_by_partial_link_text(query).text)

        # she knows that wheat is a polyploid genome and expects to find a tab on Homeologs
        tab_lnks = self.browser.find_elements_by_css_selector('.nav-tabs>li>a')
        self.assertIn('Homoeologs', "".join([tab.text for tab in tab_lnks]))

        # is this also true if she starts from a django served page?
        synteny_lnks = [lnk for lnk in tab_lnks if 'Local synteny' in lnk.text]
        self.assertEqual(1, len(synteny_lnks))
        synteny_lnks[0].click()
        tab_lnks = self.browser.find_elements_by_css_selector('.nav-tabs>li>a')
        self.assertIn('Homoeologs', "".join([tab.text for tab in tab_lnks]))

    def test_human_pages(self):
        # Cecile now want's to verify that on non-polyploid genomes there are no homeologs
        self.browser.get(self.server_url+'/oma/hogs/P53_HUMAN')
        tab_lnks = self.browser.find_elements_by_css_selector('.nav-tabs>li>a')
        self.assertNotIn('Homoeologs', "".join([tab.text for tab in tab_lnks]))

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
        for g in ('PANTR', 'PONAB', 'MACMU', 'MOUSE', 'BOVIN', 'LOXAF'):
            try:
                pos = species_column.index(g)
            except ValueError:
                self.assertTrue(False, '{} not in list of species of syntenic genes'.format(g))
            row_nr_of_species.append(pos)
        self.assertTrue(all(row_nr_of_species[i] < row_nr_of_species[i + 1] for i in range(len(row_nr_of_species) - 1)))


class ExploreMenuTest(FunctionalTest):

    def input_in_autocomplete_and_select(self, field, typed, expected):
        field.click()
        field.clear()
        field.send_keys(typed)
        self.wait_for(
            lambda: self.assertIsNotNone(self.browser.find_element_by_css_selector('.tt-dataset-genomes .tt-suggestion'))
        )
        suggestions = self.browser.find_elements_by_css_selector('.tt-dataset-genomes .tt-suggestion')
        fnd = False
        for sug in suggestions:
            if expected in sug.text:
                fnd = True
                sug.click()
                time.sleep(0.1)
                break
        self.assertTrue(fnd, 'could not find "{}" in proposed auto-complete values'.format(expected))

    def test_synteny_dotplot(self):
        # we navigate to the synteny dotplot genome selection page
        self.browser.get(self.server_url + "/oma/home/")
        self.browser.find_element_by_link_text("Explore").click()
        self.browser.find_element_by_link_text("Synteny dotplot").click()
        # here, we type as genome 1 "Homo" and select Homo sapiens from the autocomplete dropdown
        time.sleep(1)  # wait until genomes have been loaded, nothing we could wait for...
        g1_input = self.browser.find_element_by_id("g1_name")
        self.input_in_autocomplete_and_select(g1_input, 'Homo', 'Homo sapiens')

        # as second genome we select Mus musculus by typing Mus and selecting from dropdown
        g2_input = self.browser.find_element_by_id("g2_name")
        self.input_in_autocomplete_and_select(g2_input, 'Mus', 'Mus musculus')

        # we select chromosome 2
        self.wait_for(
            lambda: self.assertIsNotNone(
                self.browser.find_element_by_css_selector('#selectchr1 option')),
            timeout=10,
        )
        time.sleep(2)
        self.browser.find_element_by_xpath("//select[@id='selectchr1']//option[text()='2']").click()

        # we select chromosome 2
        self.wait_for(
            lambda: self.assertIsNotNone(
                self.browser.find_element_by_css_selector('#selectchr2 option')),
            timeout=10
        )
        self.browser.find_element_by_xpath("//select[@id='selectchr2']//option[text()='2']").click()
        # let's submit this pair (HUMAN/2 vs MOUSE/2) and see the dotplot
        self.browser.find_element_by_id('launch_PP').click()
        self.wait_for_element_with_id('dotplot_container')
        time.sleep(1)
        # between these two choromosomes we expect at least 200 pairs.
        circles = self.browser.find_elements_by_css_selector('svg circle')
        self.assertLess(200, len(circles))