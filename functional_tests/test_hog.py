from django.test import tag
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By

from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.wait import WebDriverWait
from selenium.common.exceptions import StaleElementReferenceException


from functional_tests.base import FunctionalTest


class HOGPageTest(FunctionalTest):



    def test_iham(self):


        # Jean-Claude go to the oma browser
        self.browser.get("https://omabrowser.org/oma/home/")

        # select the first example "Entry HUMAN22168"
        self.browser.find_element(By.CSS_SELECTOR, ".ex:nth-child(2)").click()
        self.browser.find_element(By.CSS_SELECTOR, "#searchForm img").click()

        # JC wait that the amuse bouche is over and all the data is loaded into the table
        element = WebDriverWait(self.browser, 10).until(
            EC.invisibility_of_element_located((By.CLASS_NAME, "toolbar"))
        )

        # click on the group button adn select hog
        self.browser.find_element(By.CSS_SELECTOR, ".group_back").click()
        self.browser.find_element(By.LINK_TEXT, "HOG").click()

        # JC verify that he arrives on the  HOG:0449427.3b page that contains 4 member open at Hominiae
        assert self.browser.find_element(By.CSS_SELECTOR, ".group_title").text == "HOG:0449427.3b with 4 members (S100 calcium binding protein P)"

        # JC verify that the iham tab is open by default
        assert self.browser.find_elements(By.XPATH, "//li[@class=\' active selected \']/a/span")[0].text.startswith("Graphical viewer")

        # JC click on the Cryptodira node in the iham tree
        svgObject = self.browser.find_element(By.XPATH, '//*[@id="tnt_tree_node_tnt_tree_container_hogvis_38"]')
        actions = ActionChains(self.browser)
        x = svgObject.location['x']
        y = svgObject.location['y'] - 400
        scroll_by_coord = 'window.scrollTo(%s,%s);' % (x,y)
        self.browser.execute_script(scroll_by_coord)
        svgObject = self.browser.find_element(By.XPATH, '//*[@id="tnt_tree_node_tnt_tree_container_hogvis_38"]')
        actions = ActionChains(self.browser)
        actions.click(svgObject).perform()

        # and select the freeze option
        tooltip = self.browser.find_element(By.XPATH, '//*[@id="tnt_tooltip_node_click_tooltip"]/table/tr[3]/td')
        actions = ActionChains(self.browser)
        actions.click(tooltip).perform()

        #JC check hog integrity
        squares = WebDriverWait(self.browser, 10).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".hog_gene")))
        try:
            for square in squares:
                assert square.get_attribute('fill') == "#95a5a6"
        except StaleElementReferenceException as Exception:
            squares = WebDriverWait(self.browser, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".hog_gene")))
            for square in squares:
                assert square.get_attribute('fill') == "#95a5a6"

        assert len(squares) == 5
        assert len(self.browser.find_elements(By.CSS_SELECTOR, ".hog_boundary")) == 3



        # JC checks that the first hog is correct
        WebDriverWait(self.browser, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".hog_1 > text"))
        ).click()
        assert self.browser.find_element(By.CSS_SELECTOR, ".tnt_zmenu_header").text == "HOG:0449427.3b"
        assert self.browser.find_elements(By.CSS_SELECTOR, ".tnt_zmenu_row > td")[0].text == "3 genes"


        # JC checks that the second hog is correct
        WebDriverWait(self.browser, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".hog_0 > text"))
        ).click()
        assert self.browser.find_element(By.CSS_SELECTOR, ".tnt_zmenu_header").text == "HOG:0449427.3a"
        assert self.browser.find_elements(By.CSS_SELECTOR, ".tnt_zmenu_row > td")[0].text == "2 genes"


        # JC opens the settings menu
        self.browser.find_element(By.ID, "btn_display_settings").click()

        # JC opens the color schema options and select protein length
        self.browser.find_element(By.ID, "dropdownMenuButton").click()
        self.browser.find_element(By.LINK_TEXT, "Protein Length").click()
        squares = WebDriverWait(self.browser, 10).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".hog_gene")))

        for square in squares:
            assert square.get_attribute('fill') != "#95a5a6"


        # JC opens the color schema options and select GC content
        self.browser.find_element(By.ID, "dropdownMenuButton").click()
        self.browser.find_element(By.LINK_TEXT, "GC Content").click()
        squares = WebDriverWait(self.browser, 10).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".hog_gene")))

        for square in squares:
            assert square.get_attribute('fill') != "#95a5a6"

        # JC opens the color schema options and select exons
        self.browser.find_element(By.ID, "dropdownMenuButton").click()
        self.browser.find_element(By.LINK_TEXT, "Number of Exons").click()
        squares = WebDriverWait(self.browser, 10).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".hog_gene")))

        for square in squares:
            assert square.get_attribute('fill') != "#95a5a6"


        # JC opens the color schema options and select Gene fonction
        self.browser.find_element(By.ID, "dropdownMenuButton").click()
        self.browser.find_element(By.LINK_TEXT, "Gene Function Similarity").click()
        squares = self.browser.find_elements(By.CSS_SELECTOR, ".hog_gene")
        for square in squares:
            assert square.get_attribute('fill') != "#95a5a6"


        # JC set the miminum coverage to 100 and verify filtering occured
        self.browser.find_element(By.ID, "set_min_coverage").send_keys("10")
        self.browser.find_element(By.ID, "set_min_coverage").send_keys(Keys.ENTER)

        squares = WebDriverWait(self.browser, 10).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".hog_gene")))

        assert len(squares) == 3
        assert len(self.browser.find_elements(By.CSS_SELECTOR, ".hog_boundary")) == 0


        #JC remove the column coverage restriction and open at Theria level
        reset = self.browser.find_element(By.ID, "reset_column_filter")

        actions = ActionChains(self.browser)
        x = reset.location['x']
        y = reset.location['y'] - 200
        scroll_by_coord = 'window.scrollTo(%s,%s);' % (x, y)
        self.browser.execute_script(scroll_by_coord)
        self.browser.find_element(By.ID, "reset_column_filter").click()

        # JC click on the Theria node in the iham tree
        svgObject = self.browser.find_element(By.XPATH, '//*[@id="tnt_tree_node_tnt_tree_container_hogvis_53"]')
        actions = ActionChains(self.browser)
        x = svgObject.location['x']
        y = svgObject.location['y'] - 400
        scroll_by_coord = 'window.scrollTo(%s,%s);' % (x, y)
        self.browser.execute_script(scroll_by_coord)
        svgObject = self.browser.find_element(By.XPATH, '//*[@id="tnt_tree_node_tnt_tree_container_hogvis_53"]')
        actions = ActionChains(self.browser)
        actions.click(svgObject).perform()

        # and select the freeze option
        tooltip = self.browser.find_element(By.XPATH, '//*[@id="tnt_tooltip_node_click_tooltip"]/table/tr[4]/td')
        actions = ActionChains(self.browser)
        actions.click(tooltip).perform()

        # JC check hog integrity
        squares = WebDriverWait(self.browser, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".hog_gene")))

        assert len(squares) == 40
        assert len(self.browser.find_elements(By.CSS_SELECTOR, ".hog_boundary")) == 0


