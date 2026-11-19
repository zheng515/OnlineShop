"""Browsing, search, filters, sorting, pagination and the product page (FR15-FR17, FR60-FR66)."""

import re

from playwright.sync_api import expect


def test_pagination_and_back_button(shop):
    shop.login("bob")
    shop.page.wait_for_selector(".product-card")
    assert len(shop.card_names()) == 12
    expect(shop.page.locator(".pagination-summary")).to_have_text("Showing 1–12 of 16 products")

    shop.after_api("/api/products", lambda: shop.page.click(".page-btn[aria-label='Page 2']"))
    assert len(shop.card_names()) == 4
    assert shop.page.url.endswith("/shop.html?page=2")
    shop.after_api("/api/products", shop.page.go_back)
    assert len(shop.card_names()) == 12

    shop.goto("/shop.html?page=99")
    shop.page.wait_for_selector(".product-card")
    expect(shop.page).to_have_url(re.compile(r"/shop\.html\?page=2$"))


def test_filters_sorting_and_url_state(shop):
    shop.login("bob")
    shop.page.wait_for_selector(".product-card")
    shop.after_api("/api/products", lambda: shop.page.click("#category-list button:has-text('Jackets')"))
    expect(shop.page.locator("#page-title")).to_have_text("Jackets")
    assert shop.card_names() == ["Windbreaker", "Puffer Jacket", "Lightweight Bomber Jacket", "Denim Jacket"]

    shop.after_api("/api/products", lambda: shop.page.select_option("#sort-select", "price_desc"))
    assert shop.card_names() == ["Puffer Jacket", "Lightweight Bomber Jacket", "Denim Jacket", "Windbreaker"]
    shop.after_api("/api/products", lambda: shop.page.check("#in-stock-filter"))
    shop.after_api("/api/products", lambda: shop.page.select_option("#size-filter", "XL"))
    assert shop.card_names() == ["Puffer Jacket", "Denim Jacket", "Windbreaker"]
    expect(shop.page.locator("#active-filters")).to_contain_text("Size XL in stock")

    shop.page.reload()
    shop.page.wait_for_selector(".product-card")
    assert shop.card_names() == ["Puffer Jacket", "Denim Jacket", "Windbreaker"]
    assert shop.page.input_value("#sort-select") == "price_desc"

    shop.after_api("/api/products", lambda: shop.page.click("[data-clear=all]"))
    assert len(shop.card_names()) == 12
    assert shop.page.input_value("#sort-select") == "price_desc"  # sorting is not a filter


def test_price_range_and_description_search(shop):
    shop.login("bob")
    shop.page.wait_for_selector(".product-card")
    shop.page.fill("#min-price", "50")
    shop.page.fill("#max-price", "20")
    shop.page.click("#price-form button")
    expect(shop.page.locator("#search-message")).to_have_text("The minimum price is higher than the maximum price.")

    shop.page.fill("#min-price", "40")
    shop.page.fill("#max-price", "60")
    shop.after_api("/api/products", lambda: shop.page.click("#price-form button"))
    assert set(shop.card_names()) == {
        "Hooded Sweatshirt", "Windbreaker", "Oxford Button-Down Shirt", "Crew Neck Sweatshirt", "Linen Summer Shirt",
    }

    shop.goto("/shop.html")
    shop.page.wait_for_selector(".product-card")
    shop.page.fill("#search-input", "FLEECE")
    shop.after_api("/api/products", lambda: shop.page.press("#search-input", "Enter"))
    assert shop.card_names() == ["Hooded Sweatshirt"]


def test_product_page_gallery_description_and_breadcrumb(shop):
    shop.login("bob")
    shop.goto("/product.html?id=3")
    shop.page.wait_for_selector("#thumbs")
    expect(shop.page.locator(".breadcrumb")).to_have_text("Products › Hoodies & Sweatshirts › Hooded Sweatshirt")
    expect(shop.page.locator(".description")).to_contain_text("Brushed fleece hoodie")
    assert shop.page.get_attribute("#main-image", "src").endswith("demo-3.svg")
    shop.page.click("#thumbs button[data-index='1']")
    assert shop.page.get_attribute("#main-image", "src").endswith("demo-3-back.svg")
    expect(shop.page.locator("[data-size=S]")).to_be_disabled()  # not offered

    shop.after_api("/api/products", lambda: shop.page.click(".breadcrumb a:nth-of-type(2)"))
    expect(shop.page.locator("#page-title")).to_have_text("Hoodies & Sweatshirts")


def test_filters_collapse_on_phones(shop):
    shop.page.set_viewport_size({"width": 390, "height": 844})
    shop.login("bob")
    shop.page.wait_for_selector(".product-card")
    assert shop.page.evaluate("document.getElementById('filters').open") is False
    assert shop.page.evaluate("document.documentElement.scrollWidth <= innerWidth")
