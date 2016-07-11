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