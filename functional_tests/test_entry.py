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


class EntryPageTest(FunctionalTest):


    def atest_pairwise_relations(self):


        # Variable to change between release (if required)
        _p53_ortholgs = "107"
        _p53_ortholgs_vertebrata = "96"
        _p53_ortholgs_hog_induced = "84"
        _p53_paralogs = "29"


        # Jean-Claude open his browser and go to the oma browser
        self.browser.get("https://omabrowser.org")
        self.browser.set_window_size(1910, 1057)

        #JC click on the p_53 example
        self.browser.find_element(By.CSS_SELECTOR, ".ex:nth-child(3)").click()
        # and click on the search icon
        self.browser.find_element(By.CSS_SELECTOR, "#searchForm img").click()

        # JC verify that the correct Ids are displayed
        assert self.browser.find_element(By.CSS_SELECTOR, ".gene_title").text == "Gene RATNO03710 (P53_RAT)"


        # JC verify that the orhologs tab is open by default with the correct number of ortholog
        assert self.browser.find_element(By.CSS_SELECTOR, "li:nth-child(1) > a .badge").text == _p53_ortholgs
        assert self.browser.find_elements(By.XPATH, "//li[@class=\' active selected \']/a/span")[0].text.startswith("Orthologs")

        #JC wait that the amuse bouche is over and all the data is loaded into the table
        element = WebDriverWait(self.browser, 10).until(
            EC.invisibility_of_element_located((By.CLASS_NAME, "toolbar"))
        )

        # JC verify that all rows have a domains viewer working
        element = WebDriverWait(self.browser, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "tr.protein:last-of-type > td.domain_vis svg"))
        )
        rows = self.browser.find_elements(By.CSS_SELECTOR, "tr.protein")
        svgs = self.browser.find_elements(By.CSS_SELECTOR, "tr.protein > td.domain_vis svg")
        assert len(rows) == len(svgs)

        # JC verify number of protein loaded in the tables
        assert int(self.browser.find_element(By.CLASS_NAME, "pagination-info").text.split(" ")[-2]) == int(
            _p53_ortholgs)

        # JC filter his research to Vertebrata only and verify number of filter protein matches
        self.browser.find_element(By.ID, "Vertebrata").click()
        assert self.browser.find_element(By.CLASS_NAME, "pagination-info").text.split(" ")[
                   -2] == _p53_ortholgs_vertebrata

        # JC remove the filter by taxonn and now filter by hog inferences evidence
        self.browser.find_element(By.ID, "reset_taxon_filter").click()
        self.browser.find_element(By.ID, "hogFilter").click()
        # JC verify number of protein loaded in the tables
        assert int(self.browser.find_element(By.CLASS_NAME, "pagination-info").text.split(" ")[-2]) == int(
            _p53_ortholgs_hog_induced)

        # JC now move to the paralogy tab and verify the tab and badge is updated correctly
        self.browser.find_element(By.CSS_SELECTOR, ".gene-orthology > li:nth-child(2) > a > span").click()
        assert int(self.browser.find_element(By.CSS_SELECTOR, "li:nth-child(2) > a .badge").text) == int(_p53_paralogs)
        assert self.browser.find_elements(By.XPATH, "//li[@class=\' active selected \']/a/span")[0].text.startswith(
            "Paralogs")

        # JC wait that the amuse bouche is over and all the data is loaded into the table
        element = WebDriverWait(self.browser, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "label.checkbox"))
        )

        # JC verify number of protein loaded in the tables
        assert int(self.browser.find_element(By.CLASS_NAME, "pagination-info").text.split(" ")[-2]) == int(
            _p53_paralogs)






