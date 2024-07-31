import os
from pathlib import Path
from datetime import datetime
from dateutil.relativedelta import relativedelta
import re
from logging import getLogger
from dataclasses import dataclass
from typing import Optional

from robocorp import browser, workitems
from RPA.Browser.Selenium import Selenium, ElementNotFound
from robocorp.tasks import task
from RPA.Excel.Files import Files as Excel

logger = getLogger(__name__)

@dataclass
class Crawler():
    url: str
    search_term: str
    number_of_months: int
    category: Optional[str] = None

    def __init__(self, url, search_term, number_of_months, category = None):
        self.selenium = self._start_selenium(60)
        self.number_of_months = number_of_months
        self.target_date = self._get_target_date()
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
    
    def _get_target_date(self):
        if self.number_of_months in [0, 1]:
            target_date = datetime.now().replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
        elif self.number_of_months == 2:
            target_date = (datetime.now() - relativedelta(months=1)).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
        elif self.number_of_months == 3:
            target_date = (datetime.now() - relativedelta(months=2)).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
        logger.info(f"Target date: {target_date}")
        return target_date
    
    def load_initial_page(self):
        try:
            self.selenium.open_available_browser()
            self.selenium.go_to(self.url)
        except Exception as e:
            logger.error(f"An error occurred trying to load the initial page: {e}")
        return 
    
    def search_term_and_category(self):
        try:
            search_box = self.selenium.find_element('xpath://button[@class="SearchOverlay-search-button"]')
            search_box.click()
            input_box = self.selenium.find_element('tag:input')
            input_box.send_keys(self.search_term)
            search_button = self.selenium.find_element('xpath://button[@class="SearchOverlay-search-submit"]')
            search_button.click()
        except ElementNotFound as e:
            logger.error(f"Search box with missing elements: {e}")
            return
        except Exception as e:
            logger.error(f"An error occurred trying to search for the term: {e}")
            logger.info("Trying to search for the term in the URL")
            page = self.url + "search?q=" + self.search_term
            self.selenium.go_to(page)
        
        try:
            category_filter = self.selenium.find_element('class:SearchFilter')
        except ElementNotFound as e:
            category_filter = None
            logger.warning(f"Category filter not found: {e} skipping category filter")

        if self.category and category_filter:
            try:
                category_filter.click()
                self.selenium.wait_until_element_is_visible("xpath:ul[@class='SearchFilter-items']", 10)
                category_list = self.selenium.find_element("xpath:ul[@class='SearchFilter-items']")
                categoy_items = self.selenium.find_elements("xpath:li[@class='SearchFilter-items-item']", category_list)
                for item in categoy_items:
                    if self.category.lower() in item.text.lower():
                        self.selenium.find_element("xpath://input[@type='checkbox']", item).submit()
                        break
                self.selenium.find_element('xpath://button[@class="data-toggle-trigger=see-all"]').click()
            except ElementNotFound as e:
                logger.error(f"Category with missing elements: {e}")
            except Exception as e:
                logger.error(f"An error occurred trying to click on the category: {e}")
        return
    
    def get_news_list(self):
        try:
            page = self.selenium.find_element('tag:bsp-search-results-module')
        except ElementNotFound as e:
            logger.error(f"Error trying to find news div: {e}")
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
        news_data = [news for news in news_data if news["timestamp"] >= self.target_date]
        return news_data
    
    def next_page(self):
        try:
            self.selenium.find_element('class:Pagination-nextPage').click()
        except ElementNotFound as e:
            logger.warning(f"No more pagination found: {e}")
            return
        except Exception as e:
            logger.error(f"An error occurred trying to click on the next page: {e}")
        
        return
    
    def close_browser(self):
        self.selenium.close_browser()
        return
    

@dataclass
class Consumer():
    data: list
    search_term: str
    def __init__(self, data, search_term):
        self.data = data
        self.search_term = search_term

    def save_to_excel(self):
        search_term = self.search_term.replace(" ", "").lower()
        path = f"./output/{search_term}_data.xlsx"
        path = Path(path)
        excel = Excel()
        wb = excel.create_workbook(path, sheet_name="news")
        for row in self.data:
            try:
                wb.append_worksheet("news", row)
            except Exception as e:
                logger.warning(f"Data is not valid: {e}")
                continue

        wb.save()
        return path

@task
def solve_challenge():
    for item in workitems.inputs:
        item_data = []
        url = item.payload.get("url", None)
        search_term = item.payload.get("search_term", None)
        number_of_months = item.payload.get("number_of_months", None)
        category = item.payload.get("category", None)
        crawler = Crawler(url, search_term, number_of_months, category)
        crawler.load_initial_page()
        crawler.search_term_and_category()
        crawler.selenium.wait_until_element_is_visible("tag:bsp-search-results-module", 15)
        step_date = datetime.now()
        while crawler.target_date <= step_date:
            news_list = crawler.get_news_list()
            if not news_list:
                break
            page_data = crawler.get_news_from_list(news_list)
            if len(page_data) == 0:
                break
            item_data.append(page_data)
            crawler.next_page()
            step_date = min([news["timestamp"] for news in page_data])
            logger.info(f"Step date: {step_date}")
        crawler.close_browser()
        consumer = Consumer(item_data, search_term)
        path = consumer.save_to_excel()
        item.add_file(path=path)
        item.done()
    return