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

