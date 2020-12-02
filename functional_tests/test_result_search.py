from functional_tests.base import FunctionalTest
from django.test import tag
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class EntrySearchTest(FunctionalTest):


    def test_entry_by_uniprot(self):
        pass

    def test_entry_by_sequences(self):
        pass

    def test_entry_restricted_to_species(self):
        pass

    def test_entry_restricted_to_taxon(self):
        pass



class GroupSearchTest(FunctionalTest):

    def test_groups_by_id_and_fingerprint(self):
        pass


class GenomeSearchTest(FunctionalTest):


    def test_genomes(self):

        # Mohammed open the oma browser
        self.browser.get("https://omabrowser.org/oma/home/")
        self.browser.set_window_size(1440, 877)

        # and search for 'HUMAN'
        self.browser.find_element(By.ID, "inputBrowser").click()
        self.browser.find_element(By.ID, "inputBrowser").send_keys("HUMAN")
        self.browser.find_element(By.ID, "inputBrowser").send_keys(Keys.ENTER)

        # Momo checks that HUMAN is recognise as a species filter
        self.browser.find_element(By.LINK_TEXT, "Homo sapiens [HUMAN]")

        # Momo checks that proteins and groups section are empty
        assert int(self.browser.find_element(By.CSS_SELECTOR, "#total_entry").text) == 0
        assert int(self.browser.find_element(By.CSS_SELECTOR, "#total_group").text) == 0

        # Momo verify the number of hits
        details = self.browser.find_element(By.ID, 'genome_stat')
        self.browser.execute_script('window.scrollTo({},{});'.format(details.location['x'],details.location['y'] - 400))
        self.browser.find_element(By.ID, "genome_stat").click()

        WebDriverWait(self.browser, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".popover-body .list-group-item:nth-child(1) "))
        )

        assert "Name: 2 hits" == self.browser.find_element(By.CSS_SELECTOR, ".popover-body .list-group-item:nth-child(1) ").text
        assert "Taxid: 0 hits" == self.browser.find_element(By.CSS_SELECTOR, ".popover-body .list-group-item:nth-child(2) ").text
        assert "Taxon: 8 hits" == self.browser.find_element(By.CSS_SELECTOR, ".popover-body .list-group-item:nth-child(3) ").text
        assert int(self.browser.find_element(By.CSS_SELECTOR, "#total_genome").text) == 10


        # Momo filter the table to keep only hits "found by name"
        self.browser.find_element(By.CSS_SELECTOR, ".btn-default").click()
        self.browser.find_element(By.CSS_SELECTOR, "#f_g_taxid > input").click()
        self.browser.find_element(By.CSS_SELECTOR, "#f_g_ag > input").click()


        # and verifies that HUMAN (extant) and Acinetobacter baUMANnii (ancestral) genomes are there
        assert "Acinetobacter baumannii" == self.browser.find_element(By.XPATH, "//table[@id='matchTable_genome']/tbody/tr[@id='undefined'][1]/td[1]").text
        assert "HUMAN" == self.browser.find_element(By.XPATH, "//table[@id='matchTable_genome']/tbody/tr[@id='undefined'][2]/td[1]").text


        # Momo then filter by "derived from ancestral genomes" and verifies that the 8 Acinetobacter baumannii are there
        #self.browser.find_element(By.CSS_SELECTOR, ".btn-default").click()
        self.browser.find_element(By.CSS_SELECTOR, "#f_g_name > input").click()
        self.browser.find_element(By.CSS_SELECTOR, "#f_g_ag > input").click()

        for i in range(1,9):
            assert "ACIB" == self.browser.find_element(By.XPATH,"//table[@id='matchTable_genome']/tbody/tr[@id='undefined'][{}]/td[1]".format(i)).text[:4]


        # Momo search now for Tetrapoda
        self.browser.find_element(By.ID, "inputBrowser").clear()
        self.browser.find_element(By.ID, "inputBrowser").send_keys("Tetrapoda")
        self.browser.find_element(By.CSS_SELECTOR, "#searchForm img").click()

        # Momo checks that Tetrapoda is recognise as a species filter
        self.browser.find_element(By.LINK_TEXT, "Tetrapoda")

        # Momo checks that proteins and groups section are empty
        assert int(self.browser.find_element(By.CSS_SELECTOR, "#total_entry").text) == 0
        assert int(self.browser.find_element(By.CSS_SELECTOR, "#total_group").text) == 0

        # Momo verify the number of hits
        details = self.browser.find_element(By.ID, 'genome_stat')
        self.browser.execute_script(
            'window.scrollTo({},{});'.format(details.location['x'], details.location['y'] - 400))
        self.browser.find_element(By.ID, "genome_stat").click()

        assert "Name: 7 hits" == self.browser.find_element(By.CSS_SELECTOR,
                                                           ".popover-body .list-group-item:nth-child(1) ").text
        assert "Taxid: 0 hits" == self.browser.find_element(By.CSS_SELECTOR,
                                                            ".popover-body .list-group-item:nth-child(2) ").text
        assert "Taxon: 84 hits" == self.browser.find_element(By.CSS_SELECTOR,
                                                            ".popover-body .list-group-item:nth-child(3) ").text

        assert int(self.browser.find_element(By.CSS_SELECTOR, "#total_genome").text) == 91

        # Momo filter the table to keep only hits "found by name"
        self.browser.find_element(By.CSS_SELECTOR, ".btn-default").click()
        self.browser.find_element(By.CSS_SELECTOR, "#f_g_taxid > input").click()
        self.browser.find_element(By.CSS_SELECTOR, "#f_g_ag > input").click()

        # and verifies that Tetrapoda (Ancestral) is here
        assert "Tetrapoda" == self.browser.find_element(By.XPATH,"//table[@id='matchTable_genome']/tbody/tr[@id='undefined'][1]/td[1]").text
        assert "Ancestral" == self.browser.find_element(By.XPATH,"//table[@id='matchTable_genome']/tbody/tr[@id='undefined'][1]/td[2]").text


class QuickSearchTest(FunctionalTest):

    def test_direct_search_redirection(self):
        pass


