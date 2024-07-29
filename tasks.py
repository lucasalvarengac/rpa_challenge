import os
from pathlib import Path
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
import re
from logging import getLogger

from robocorp import browser, workitems
from RPA.Browser.Selenium import Selenium, ElementNotFound, ChromeOptions
from robocorp.tasks import get_output_dir, task
from RPA.Excel.Files import Files as Excel

logger = getLogger(__name__)

os.environ["RC_WORKITEM_INPUT_PATH"] = (
    "devdata/work-items-in/workitems.json"
)

class Crawler():
    def __init__(self, url, search_term, number_of_months, category):
        self.selenium = self._start_selenium()
        self.target_date = self._get_target_date(number_of_months)
        self.url = url
        self.search_term = search_term
        self.category = category

    def _start_selenium(self, timeout):
        browser.configure(
            browser_engine="chromium",
            screenshot="only-on-failure",
            headless=True,
        )
        try:
            selenium = Selenium(timeout=timeout)
            logger.info("Selenium object instantiated successfully")
        except Exception as e:
            logger.error(f"An error occurred trying to instantiate the Selenium object: {e}")
        return selenium
    
    def _get_target_date(self, number_of_months):
        if number_of_months in [0, 1]:
            target_date = datetime.now().replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
        elif number_of_months == 2:
            target_date = (datetime.now() - relativedelta(months=1)).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
        elif number_of_months == 3:
            target_date = (datetime.now() - relativedelta(months=2)).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
        logger.info(f"Target date: {target_date}")
        return target_date
    
    def load_initial_page(self, url):
        try:
            self.selenium.open_available_browser()
            page = browser.go_to(url)
        except Exception as e:
            logger.error(f"An error occurred trying to load the initial page: {e}")
        return
    
    def search_term_and_category(self, search_term, category):
        try:
            search_box = self.selenium.find_element("class:SearchBox-input")
            search_box.send_keys(search_term)
            search_box.submit()
        except ElementNotFound as e:
            logger.error(f"Search box with missing elements: {e}")
            return
        
        try:
            self.selenium.click('xpath:bsp-toggler["@data-toggle=search-filter"]')
            category_list = self.selenium.find_element("xpath:li[@class='SearchFilter-items-item']")
            for item in category_list:
                if category in item.text:
                    item.click()
                    break
            self.selenium.click('xpath:button["@data-toggle-trigger=see-all"]')
        except ElementNotFound as e:
            logger.error(f"Category with missing elements: {e}")
        except Exception as e:
            logger.error(f"An error occurred trying to click on the category: {e}")
        return
    
    def get_news_list(self):
        try:
            page = self.selenium.find_element('tag:bsp-search-results-module')
        except ElementNotFound as e:
            logger.error(f": {e}")
            return 
        try:
            results = self.selenium.find_element("class:SearchResultsModule-results", page)
            news_list = self.selenium.find_elements("class:PageList-items-item", results)
        except ElementNotFound as e:
            logger.error(f"News with missing elements: {e}")
            return 
        return news_list
    
    def get_news_from_list(self, news_list):
        news_data = []
        for news in news_list:
            try:
                description = self.selenium.find_element("class:PagePromo-description", news)
                title = self.selenium.find_element("class:PagePromo-title", news)
                link = self.selenium.find_element("class:Link", title)
                description = self.selenium.find_element("tag:span", description)
                date = self.selenium.find_element("tag:bsp-timestamp", news)

                title = title.text
                description = description.text
                link = link.get_attribute("href")
                timestamp = date.get_attribute("data-timestamp")
                timestamp = datetime.fromtimestamp(int(timestamp) / 1000)
                re_exp1 = r"\$?[0-9,.]+"
                re_exp2 = r"\d+[dollars|usd]"
                amount_of_money = (re.findall(re_exp1, title+description, re.IGNORECASE) or 
                                            re.findall(re_exp2, title+description, re.IGNORECASE))
                amount_of_money = True if len(amount_of_money) > 0 else False
                count_search_phrase = len(re.findall(self.search_term, title+description, re.IGNORECASE))

                news_data.append(
                    {
                        "title": title,
                        "description": description,
                        "link": link,
                        "timestamp": timestamp,
                        "amount_of_money": amount_of_money,
                        "count_search_phrase": count_search_phrase
                    }
                )
            except ElementNotFound as e:
                logger.error(f"Element not found in news object: {e}")
                continue
            except Exception as e:
                logger.error(f"An error occurred: {e}")
                break
        return news_data
    
    def next_page(self):
        try:
            self.selenium.click('xpath:div["@class=Pagination-nextPage"]')
            self.selenium.find_element('xpath:div["@class=Pagination-nextPage"]')
        except ElementNotFound as e:
            logger.warning(f"No more pagination found: {e}")
            return
        except Exception as e:
            logger.error(f"An error occurred trying to click on the next page: {e}")
        
        return
    
    def close_browser(self):
        self.selenium.close_browser()
        return

class Consumer():
    def __init__(self, data, search_term):
        self.data = data
        self.df = self._create_dataframe()
        self.search_term = search_term

    def _create_dataframe(self):
        data = pd.DataFrame(self.data)
        return data

    def save_to_excel(self,path):
        output = get_output_dir() or Path("output")
        file_name = "news_data.xlsx"
        path = output / file_name
        excel = Excel()
        try:
            excel.create_workbook(path)
            excel.write_to_worksheet(path, self.search_term, self.df)
        except Exception as e:
            logger.error(f"An error occurred trying to save the data to an Excel file: {e}")
        return

@task
def solve_challenge():
    news_data = []
    for item in workitems.inputs:
        url = item.payload["url"]
        search_term = item.payload["search_term"]
        number_of_months = item.payload["number_of_months"]
        category = item.payload["category"]
        crawler = Crawler(url, search_term, number_of_months, category)
        crawler.load_initial_page(url)
        crawler.search_term_and_category(search_term, category)
        while True:
            news_list = crawler.get_news_list()
            page_data = crawler.get_news_from_list(news_list)
            news_data.append(page_data)
            crawler.next_page()
            if len(news_list) == 0:
                break
        crawler.close_browser()
    consumer = Consumer(news_data)
    consumer.save_to_excel("news_data.xlsx")
    return

@task
def crawler():
    def configure_browser(timeout=120):
        options = ChromeOptions()
        options.page_load_strategy = "none"
        browser.configure(
            browser_engine="chromium",
            screenshot="only-on-failure",
            headless=True,
        )
        try:
            selenium = Selenium(timeout=timeout)
        except Exception as e:
            print(f"An error occurred: {e}")
        return selenium

    def get_news_search_page():
        def get_target_date(number_of_months):
            if number_of_months in [0, 1]:
                target_date = datetime.now().replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0
                )
            elif number_of_months == 2:
                target_date = (datetime.now() - relativedelta(months=1)).replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0
                )
            elif number_of_months == 3:
                target_date = (datetime.now() - relativedelta(months=2)).replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0
                )
            return target_date

        def get_news_from_list(news_list, search_term):
            news_data = []
            for news in news_list:
                try:
                    description = selenium.find_element("class:PagePromo-description", news)
                    title = selenium.find_element("class:PagePromo-title", news)
                    link = selenium.find_element("class:Link", title)
                    description = selenium.find_element("tag:span", description)
                    date = selenium.find_element("tag:bsp-timestamp", news)

                    title = title.text
                    description = description.text
                    link = link.get_attribute("href")
                    timestamp = date.get_attribute("data-timestamp")
                    timestamp = datetime.fromtimestamp(int(timestamp) / 1000)
                    re_exp1 = r"\$?[0-9,.]+"
                    re_exp2 = r"\d+[dollars|usd]"
                    amount_of_money = (re.findall(re_exp1, title+description, re.IGNORECASE) or 
                                                re.findall(re_exp2, title+description, re.IGNORECASE))
                    amount_of_money = True if len(amount_of_money) > 0 else False
                    count_search_phrase = len(re.findall(search_term, title+description, re.IGNORECASE))

                    news_data.append(
                        {
                            "title": title,
                            "description": description,
                            "link": link,
                            "timestamp": timestamp,
                            "amount_of_money": amount_of_money,
                            "count_search_phrase": count_search_phrase
                        }
                    )
                except ElementNotFound as e:
                    print(f"{e}")
                    continue
            return news_data
        
        def check_duplicate_news(news_data):
                unique_data = []
                urls = []
                for news in news_data:
                    if news["link"] not in urls:
                        unique_data.append(news)
                return unique_data
        
        def run_search(selenium, url, search_term, number_of_months):
            selenium.open_available_browser()
            page_num = 1
            url = f"{url}search?q={search_term}+&s=3&p={page_num}"
            min_timestamp = datetime.now()
            target_date = get_target_date(number_of_months)
            print(f"Target date: {target_date}")
            selenium.go_to(url)
            all_data = []
            while min_timestamp > target_date:
                try:
                    page = selenium.find_element('tag:bsp-search-results-module')

                except ElementNotFound as e:
                    print("News with missing elements")
                    break
                try:
                    results = selenium.find_element(
                        "class:SearchResultsModule-results", page
                    )
                    news_list = selenium.find_elements("class:PageList-items-item", results)
                    news_data = get_news_from_list(news_list, search_term)
                    news_data = [news for news in news_data if news["timestamp"] > target_date]
                    min_timestamp = min(news_data, key=lambda x: x["timestamp"])[
                        "timestamp"
                    ]
                except ElementNotFound as e:
                    print("News with missing elements")
                    continue
                all_data.extend(news_data)
                
                page_num += 1
                url = url.replace(f"p={page_num-1}", f"p={page_num}")
                try:
                    selenium.go_to(url)
                except ElementNotFound as e:
                    print("No more news found")
                    break
            all_data = check_duplicate_news(all_data)
            data = all_data
            for data in all_data:
                data["timestamp"] = data["timestamp"].isoformat()
            workitems.outputs.create(all_data)
            selenium.close_browser()

        selenium = configure_browser()
        for item in workitems.inputs:
            search_term = item.payload["search_term"]
            number_of_months = item.payload["number_of_months"]
            url = item.payload["url"]
            run_search(selenium, url, search_term, number_of_months)
        return 

    return get_news_search_page()
    

@task
def consumer():
    data = []
    for item in workitems.outputs:
        try:
            data.append(item.payload)
        except Exception as e:
            print(f"An error occurred: {e}")
    data = pd.DataFrame(data)
    
    return