import re
import time
from enum import Enum
from functools import total_ordering
from typing import Optional

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
    """ Contains information on one specific listing """
    def __init__(self, condition: Condition, price: float, quantity: int):
        """
        Creates the listing storing
        :param condition: Condition representing the condition of the card
        :param price: The price of the card
        :param quantity: How many are available at this price and condition
        """
        self.condition = condition
        self.price = price
        self.quantity = quantity

    @property
    def total_price(self) -> float:
        """
        Calculates the total price of the listing
        :return: Price for all cards in this listing
        """
        return self.price * self.quantity

    def __str__(self) -> str:
        """
        Prints a string like '$0.11 - 4 Near Mint'
        :return: String representation of the listing
        """
        return f"${self.price} - {self.quantity} {self.condition.value}"


@total_ordering
class Store:
    """ A Store contains multiple listings and summarizes the total of all the listings"""
    def __init__(self, name, shipping, free_threshold):
        """
        Stores the name and how much shipping potentially costs
        :param name: Name of the store
        :param shipping: How much shipping costs
        :param free_threshold: How much needs to be spent to get free shipping
        """
        self.name = name
        self.shipping = shipping
        self.free_threshold = free_threshold
        self.listings = []

    def add_listing(self, condition: Condition, price: float, quantity: int) -> None:
        """
        Adds a listing to the store's list
        :param condition: Condition of the listing
        :param price: Price per cards in the listing
        :param quantity: How many cards are available in this listing
        """
        self.listings.append(Listing(condition, price, quantity))

    @property
    def card_price(self) -> float:
        """
        Sums all the prices of the listings at the store
        :return: Price to buy all cards at the store
        """
        price = 0
        for listing in self.listings:
            price += listing.total_price
        return price

    @property
    def achieved_free_shipping(self) -> bool:
        """
        Determines whether you already have free shipping from the store or not
        :return: True if you have free shipping, else False
        """
        if self.free_threshold is None:
            # You can not have free shipping
            return False
        else:
            return self.card_price >= self.free_threshold

    @property
    def shipping_price(self) -> float:
        """
        Returns the amount that will be spent on shipping if buying all the cards in the shop
        It will be zero if the cards sum up to greater than the amount needed to be free
        :return: Amount spent on shipping
        """
        if self.free_threshold is None:
            # You can't get free shipping
            return self.shipping
        elif self.card_price < self.free_threshold:
            # You are below the threshold for free shipping
            return self.shipping
        else:
            # You have free shipping
            return 0

    @property
    def money_to_free_shipping(self) -> Optional[float]:
        """
        Tells how much more needs to be spent to receive free shipping.
        This is useful if the amount to free shipping is less than shipping. You may as well buy more cards to fill
        the cart at that point.
        :return: The amount required for free shipping
        """
        if self.free_threshold is None:
            # You can't get free shipping
            return None
        elif self.card_price > self.free_threshold:
            # You already have free shipping
            return None
        else:
            # How much you'd need to spend for free shipping
            return self.free_threshold - self.card_price

    @property
    def total_price(self) -> float:
        """
        Calculates the total price, cards + shipping of buying all cards from the store
        :return: The total money spent to buy all the cards from the store
        """
        return self.card_price + self.shipping_price

    @property
    def total_quantity(self) -> int:
        """
        The total number of cards available at the store
        :return: Total cards available across conditions
        """
        quantity = 0
        for listing in self.listings:
            quantity += listing.quantity
        return quantity

    @property
    def price_per_card(self) -> float:
        """
        Calculates the price per card to determine the true price of the card
        :return: Price per card if all cards are purchased
        """
        return self.total_price / self.total_quantity

    @property
    def has_foil(self) -> bool:
        """
        Determines whether a specific store has a foil card available
        :return: True if the store has a foil listing, else False
        """
        for listing in self.listings:
            if "FOIL" in listing.condition.name:
                return True
        return False

    def __str__(self) -> str:
        """
        Creates a string that looks like the following:
        The Dragon's Table - $0.17 per - $11.87 - 69
            Heavily Played - $0.13 - 8
            Moderately Played - $0.14 - 40
            Lightly Played - $0.15 - 20
            Lightly Played Foil - $0.24 - 1
        :return: The string representation of the store's available cards
        """
        s = f'{self.name} - ${self.price_per_card:.2f} per - ${self.total_price:.2f} - {self.total_quantity}'
        if self.achieved_free_shipping:
            s += f'\n\t* FREE SHIPPING *'
        for listing in self.listings:
            s += f'\n\t{listing.condition.value} - ${listing.price:.2f} - {listing.quantity}'
        if self.money_to_free_shipping is not None:
            if self.money_to_free_shipping < self.shipping:
                s += f"\n\tFREE SHIPPING IN ${self.money_to_free_shipping:.2f}"
        return s

    def __lt__(self, other) -> bool:
        """
        Used for sorting, determines if a store has cheaper cards on average than the other. If they're the same,
        determine which has more cards available.
        :param other: Store being compared to
        :return: If this store is cheaper per card than the other
        """
        if self.price_per_card == other.price_per_card:
            return self.total_quantity < other.total_quantity
        else:
            return self.price_per_card < other.price_per_card

    def __eq__(self, other) -> bool:
        """
        Used for sorting, determines if stores are equal in their cost per card
        :param other: Store being compared to
        :return: If the stores have an equal
        """
        return self.price_per_card == other.price_per_card


class TCGPlayerParser:
    def __init__(self, url, blacklist):
        """
        Creates the parser. Scrapes a URL, clicking through pages, and determines how much buying out that card from
        certain stores would cost.
        :param url: URL to scrape
        :param blacklist: List of sellers to ignore (if for instance, they cancelled an order for trying to ship too
            many cards)
        """
        self.url = url
        self.blacklist = blacklist
        self.stores = {}

        self.driver = webdriver.Firefox()
        self.driver.implicitly_wait(5)
        self.driver.get(url)

    def scrape_prices(self) -> list[Store]:
        """
        Parses the page, clicks through all the pages, then presents a sorted list of all the stores and how much it
        would cost to buy them out.
        :return: Sorted list of Stores based on how much it would cost to buy them out
        """
        while True:  # We will break when we get to the last page
            self.parse_page()
            if self.can_click_next():
                self.click_next()
                time.sleep(3)  # Sleeps to allow the webpage to load
            else:
                results = list(self.stores.values())
                results.sort()
                return results

    @staticmethod
    def find_price(price_string: str) -> Optional[float]:
        """
        Given a string, finds the price in it, if it exists
        :param price_string: String to parse
        :return: Price if it's found, else None
        """
        if price_string is None:
            return None
        return float(re.search(r"(\d+(\.\d{2})?)", price_string).group(1))

    def parse_page(self) -> None:
        """
        Parses the page and grabs each store entry, figures out the name, price, quantity, condition, and free shipping
        then adds it to the dictionary of stores.
        :return: None
        """
        # listing-item contains all listings
        listings = self.driver.find_elements(By.CLASS_NAME, "listing-item")

        # Change to implicitly wait for a small amount of time because the page is already loaded
        # When we look for free shipping, this will make it quicker if it doesn't exist
        self.driver.implicitly_wait(0.01)

        for listing in listings:
            seller_name = listing.find_element(By.CLASS_NAME, "seller-info__name").text
            price = listing.find_element(By.CLASS_NAME, "listing-item__listing-data__info__price").text
            quantity = listing.find_element(By.CLASS_NAME, "add-to-cart__available").text
            condition = listing.find_element(By.CLASS_NAME, "listing-item__listing-data__info__condition").text

            # We are not sure if shipping exists, because the direct shipping doesn't use the same element
            try:
                shipping_price = listing.find_element(By.CLASS_NAME, "shipping-messages__price").text
            except NoSuchElementException:
                # This means it's direct
                shipping_price = "$3.99"

            # This element may not exist, so if it doesn't, we just say that no free shipping is available
            try:
                free_shipping = listing.find_element(By.CLASS_NAME, "free-shipping-over-min").text
            except NoSuchElementException:
                free_shipping = None

            # Parse the price, shipping, free shipping threshold, and the quantity of cards available
            price = self.find_price(price)
            shipping_price = self.find_price(shipping_price)
            free_shipping = self.find_price(free_shipping)
            quantity = int(re.search(r"\d+", quantity).group(0))

            # If the seller is on the blacklist, skip them
            if seller_name in self.blacklist:
                continue

            # If the store isn't in the dictionary yet, add it.
            # The shipping price and free shipping threshold are tied to the store, not the listing
            if seller_name not in self.stores.keys():
                self.stores[seller_name] = Store(seller_name, shipping_price, free_shipping)

            # For some reason, listings were being added twice. This makes sure that doesn't happen
            if condition not in (listing.condition for listing in self.stores[seller_name].listings):
                # Then finally add a listing to the store
                self.stores[seller_name].add_listing(Condition(condition), price, quantity)

    def can_click_next(self) -> bool:
        """
        Checks if the next arrow can be clicked
        :return: If the next arrow can be clicked
        """
        button = self.driver.find_element(By.CSS_SELECTOR, "a[aria-label='Next page']")
        if button.get_attribute('aria-disabled') == 'true':
            return False
        return True

    def click_next(self) -> None:
        """
        Performs the click on the next button to take the program to the next page
        :return: None
        """
        button = self.driver.find_element(By.CSS_SELECTOR, "a[aria-label='Next page']")
        button.click()

# I'm collecting Break Open from Onslaught
my_url = "https://www.tcgplayer.com/product/10583/magic-onslaught-break-open?Language=English"
blacklist = ['Mtgaok']  # has cancelled an order before

t = TCGPlayerParser(my_url, blacklist)
stores = t.scrape_prices()
for s in stores:
    print(s)
    print()
