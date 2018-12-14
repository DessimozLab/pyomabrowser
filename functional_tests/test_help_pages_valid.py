from .base import FunctionalTest


class HelpPagesTest(FunctionalTest):
    def test_can_navigate_through_help_pages(self):
        # Tom navigates to OMA Browser page
        self.browser.get(self.server_url)

        # he sees a box which has links for first time here users
        boxes = self.browser.find_elements_by_class_name('oma-3-panels')
        self.assertIn('First time here', boxes[0].text)

        # Tom clicks on the link with a brief introduction
        boxes[0].find_element_by_link_text('brief introduction to OMA').click()
        # the browser shows a different page with 'About' as title.
        self.assertIn('About', self.browser.title)
        # It contains a paragraph with 'OMA in a nutshell' as header
        nutshell_div = self.browser.find_element_by_id('nut')
        self.assertIn('OMA in a nutshell', nutshell_div.text)

        # Now, we are interested in some of the use cases of orthology.
        # Tom clicks on the "typical uses" menu.
        self.browser.find_element_by_link_text('Help').click()
        self.browser.find_element_by_link_text('Typical uses').click()
        # we check the active tab corresponds to the active tab and that only one tab is active
        container = self.browser.find_element_by_class_name('container')
        active_tab_id = [el.get_attribute('id') for el in container.find_elements_by_class_name('active') if el.tag_name == "div"]
        active_li = [el for el in container.find_elements_by_class_name('active') if el.tag_name == 'li']
        self.assertEqual(1, len(active_li))
        self.assertEqual(1, len(active_tab_id))
        self.assertTrue(active_li[0].find_element_by_tag_name('a').get_attribute('href').endswith(active_tab_id[0]))

        # Tom realizes that his favorite genome is not available in OMA yet and wants to add it
        self.browser.find_element_by_link_text('Help').click()
        self.browser.find_element_by_partial_link_text('Suggesting a genome').click()
        self.assertIn('Suggesting', self.browser.title)
        form = self.browser.find_element_by_class_name('form-horizontal')
        self.assertIn('NCBI Taxonomy Identifier', form.text)


class ExplorePagesTester(FunctionalTest):
    def test_hog_landing_page_has_valid_examples(self):
        # Tom navigates to OMA Browser page
        self.browser.get(self.server_url)
        # and continues to the landing page of the HOGs through the Explore menu
        self.browser.find_element_by_link_text("Explore").click()
        self.browser.find_element_by_link_text("Hierarchical orthologous groups (HOGs)").click()
        examples = [z.get_property('id') for z in self.browser.find_elements_by_xpath("//*[contains(@id, 'exMemb')]")]
        self.assertGreater(len(examples), 0, 'no examples found on page')
        for example in examples:
            lnk_el = self.browser.find_element_by_id(example)
            lnk_txt = lnk_el.text
            lnk_el.click()
            self.browser.find_element_by_xpath("//div[@class='col-sm-6']/div/span/button").click()
            self.assertNotIn("is not part of any hierarchical", self.browser.page_source,
                             "HOG example {} is not part of any hog".format(lnk_txt))
            self.assertIn(lnk_txt, self.browser.page_source)
            self.browser.back()
