import smtplib
from email.message import EmailMessage
import re
from enum import Enum
from functools import total_ordering
import time

from selenium import webdriver

from selenium.common import NoSuchElementException
from selenium.webdriver.common.by import By


class Condition(Enum):
    NEAR_MINT = "Near Mint"
    LIGHTLY_PLAYED = "Lightly Played"
    MODERATELY_PLAYED = "Moderately Played"
    HEAVILY_PLAYED = "Heavily Played"
    DAMAGED = "Damaged"
    NEAR_MINT_FOIL = "Near Mint Foil"
    LIGHTLY_PLAYED_FOIL = "Lightly Played Foil"
    MODERATELY_PLAYED_FOIL = "Moderately Played Foil"
    HEAVILY_PLAYED_FOIL = "Heavily Played Foil"
    DAMAGED_FOIL = "Damaged Foil"


class Listing:
    def __init__(self, condition: Condition, price: float, quantity: int):
        self.condition = condition
        self.price = price
        self.quantity = quantity

    @property
    def total_price(self):
        return self.price * self.quantity

    def __str__(self):
        return f"${self.price} - {self.quantity} {self.condition.value}"


@total_ordering
class Store:
    def __init__(self, name, shipping, free_threshold):
        self.name = name
        self.shipping = shipping
        self.free_threshold = free_threshold
        self.listings = []

    def add_listing(self, condition: Condition, price: float, quantity: int):
        self.listings.append(Listing(condition, price, quantity))

    @property
    def card_price(self):
        price = 0
        for listing in self.listings:
            price += listing.total_price
        return price

    @property
    def shipping_price(self):
        if self.free_threshold is None or self.card_price < self.free_threshold:
            return self.shipping
        else:
            return 0

    @property
    def money_to_free_shipping(self):
        if self.free_threshold is None or self.card_price > self.free_threshold:
            return None
        return self.free_threshold - self.card_price

    @property
    def total_price(self):
        return self.card_price + self.shipping_price

    @property
    def total_quantity(self):
        quantity = 0
        for listing in self.listings:
            quantity += listing.quantity
        return quantity

    @property
    def price_per_card(self):
        return self.total_price / self.total_quantity

    @property
    def has_foil(self):
        for listing in self.listings:
            if "FOIL" in listing.condition.name:
                return True
        return False

    def __str__(self):
        s = f'{self.name} - ${self.price_per_card:.2f} per - ${self.total_price:.2f} - {self.total_quantity}'
        for listing in self.listings:
            s += f'\n\t{listing.condition.value} - ${listing.price:.2f} - {listing.quantity}'
        if self.money_to_free_shipping is not None:
            if self.money_to_free_shipping < self.shipping:
                s += f"\n\tFREE SHIPPING IN ${self.money_to_free_shipping:.2f}"
        return s

    def __lt__(self, other):
        return self.price_per_card < other.price_per_card

    def __eq__(self, other):
        return self.price_per_card == other.price_per_card


class TCGPlayerParser:
    def __init__(self, url, blacklist):
        self.url = url
        self.blacklist = blacklist
        self.stores = {}

        self.driver = webdriver.Firefox()
        self.driver.implicitly_wait(5)
        self.driver.get(url)

    def scrape_prices(self):
        while True:
            self.parse_page()
            if self.can_click_next():
                self.click_next()
                time.sleep(3)
            else:
                results = list(self.stores.values())
                results.sort()
                return results

    @staticmethod
    def find_price(s):
        if s is None:
            return None
        return float(re.search(r"(\d+(\.\d{2})?)", s).group(1))

    def parse_page(self):
        listings = self.driver.find_elements(By.CLASS_NAME, "listing-item")
        self.driver.implicitly_wait(0.01)

        for listing in listings:
            seller_name = listing.find_element(By.CLASS_NAME, "seller-info__name").text
            price = listing.find_element(By.CLASS_NAME, "listing-item__listing-data__info__price").text
            quantity = listing.find_element(By.CLASS_NAME, "add-to-cart__available").text
            condition = listing.find_element(By.CLASS_NAME, "listing-item__listing-data__info__condition").text

            try:
                shipping_price = listing.find_element(By.CLASS_NAME, "shipping-messages__price").text
            except NoSuchElementException:
                # This means it's direct
                shipping_price = "$3.99"

            try:
                free_shipping = listing.find_element(By.CLASS_NAME, "free-shipping-over-min").text
            except NoSuchElementException:
                free_shipping = None

            price = self.find_price(price)
            shipping_price = self.find_price(shipping_price)
            free_shipping = self.find_price(free_shipping)
            quantity = int(re.search(r"\d+", quantity).group(0))

            if seller_name in self.blacklist:
                continue
            if seller_name not in self.stores.keys():
                self.stores[seller_name] = Store(seller_name, shipping_price, free_shipping)

            if condition not in [listing.condition for listing in self.stores[seller_name].listings]:
                self.stores[seller_name].add_listing(Condition(condition), price, quantity)

    def can_click_next(self):
        button = self.driver.find_element(By.CSS_SELECTOR, "a[aria-label='Next page']")
        if button.get_attribute('aria-disabled') == 'true':
            return False
        return True

    def click_next(self):
        button = self.driver.find_element(By.CSS_SELECTOR, "a[aria-label='Next page']")
        button.click()

my_url = "https://www.tcgplayer.com/product/10583/magic-onslaught-break-open?Language=English"
blacklist = ['Mtgaok']
t = TCGPlayerParser(my_url, blacklist)
stores = t.scrape_prices()
for s in stores:
    print(s)
    print()