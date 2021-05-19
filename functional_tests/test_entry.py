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


    def test_pairwise_relations(self):


        # Variable to change between release (if required)
        _p53_ortholgs = "120"
        _p53_ortholgs_vertebrata = "110"
        _p53_ortholgs_hog_induced = "99"
        _p53_paralogs = "34"


        # Jean-Claude open his browser and go to the oma browser
        self.browser.get("https://omabrowser.org")
        self.browser.set_window_size(1910, 1057)

        #JC click on the p_53 example
        self.browser.find_element(By.CSS_SELECTOR, ".ex:nth-child(3)").click()
        # and click on the search icon
        self.browser.find_element(By.CSS_SELECTOR, "#searchForm img").click()

        # JC verify that the correct Ids are displayed
        self.assertRegex(self.browser.find_element(By.CSS_SELECTOR, ".gene_title").text,
                         r"Gene RATNO\d{5} \(P53_RAT\)",
                         "Gene title not as expected")


        # JC verify that the orhologs tab is open by default with the correct number of ortholog
        self.assertGreaterEqual(int(self.browser.find_element(By.CSS_SELECTOR, "li:nth-child(1) > a .badge").text),
                                int(_p53_ortholgs),
                                "Number of orthologs too small.")
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
        self.assertEqual(len(rows), len(svgs), "Not all proteins have an domain svg loaded")

        # JC verify number of protein loaded in the tables
        nr_orthologs = int(self.browser.find_element(By.CLASS_NAME, "pagination-info").text.split(" ")[-2])
        self.assertGreaterEqual(nr_orthologs, int(_p53_ortholgs), "Not as many orthologs as expected")

        # JC filter his research to Vertebrata only and verify number of filter protein matches
        self.browser.find_element(By.ID, "Vertebrata").click()
        nr_vertebrata_orthologs = int(self.browser.find_element(By.CLASS_NAME, "pagination-info").text.split(" ")[-2])
        self.assertGreaterEqual(nr_vertebrata_orthologs, int(_p53_ortholgs_vertebrata), "Not enough vertebrata orthologs")
        self.assertLess(nr_vertebrata_orthologs, nr_orthologs, "vertebrata should be fewer orthologs than total")

        # JC remove the filter by taxonn and now filter by hog inferences evidence
        self.browser.find_element(By.ID, "reset_taxon_filter").click()
        self.browser.find_element(By.ID, "hogFilter").click()
        # JC verify number of protein loaded in the tables
        self.assertGreaterEqual(int(self.browser.find_element(By.CLASS_NAME, "pagination-info").text.split(" ")[-2]),
                                int(_p53_ortholgs_hog_induced),
                                "Too few hog-based orthologs")

        # JC now move to the paralogy tab and verify the tab and badge is updated correctly
        self.browser.find_element(By.CSS_SELECTOR, ".gene-orthology > li:nth-child(2) > a > span").click()
        self.assertGreaterEqual(int(self.browser.find_element(By.CSS_SELECTOR, "li:nth-child(2) > a .badge").text),
                                int(_p53_paralogs),
                                "Too few paralogs")
        assert self.browser.find_elements(By.XPATH, "//li[@class=\' active selected \']/a/span")[0].text.startswith(
            "Paralogs")

        # JC wait that the amuse bouche is over and all the data is loaded into the table
        element = WebDriverWait(self.browser, 10).until(
            EC.invisibility_of_element_located((By.CLASS_NAME, "toolbar"))
        )

        # JC verify number of protein loaded in the tables
        self.assertGreaterEqual(int(self.browser.find_element(By.CLASS_NAME, "pagination-info").text.split(" ")[-2]),
                                int(_p53_paralogs),
                                "nr of paralogs in table too small")






