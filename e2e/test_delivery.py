"""Address book, delivery at checkout, delivery methods (FR100-FR108)."""

import re

from playwright.sync_api import expect
from test_shopping import on_mock_provider

NEW_ADDRESS = {
    "full_name": "Alice at Work",
    "phone": "+1 555 0199",
    "line1": "500 Office Park",
    "city": "Chicago",
    "region": "IL",
    "postal_code": "60601",
}


def fill_address(form, values: dict) -> None:
    for key, value in values.items():
        form.locator(f"[name={key}]").fill(value)


def buy_now(shop, product_id: int, size: str, quantity: int) -> None:
    shop.goto(f"/product.html?id={product_id}")
    shop.page.click(f"[data-size={size}]")
    shop.page.fill("#qty-input", str(quantity))
    shop.page.click("#buy-now-btn")
    shop.page.wait_for_url("**/checkout.html?*")


def test_choose_address_and_method_at_checkout(shop):
    shop.login("alice")
    buy_now(shop, 1, "M", 1)  # Classic Cotton T-Shirt, 19.99

    # Default address and the cheapest method are chosen at first (FR105).
    expect(shop.page.locator("#address-choices input:checked")).to_have_count(1)
    expect(shop.page.locator("#address-choices .choice:has(input:checked)")).to_contain_text("Alice Example")
    standard = shop.page.locator("#method-choices .choice", has_text="Standard delivery")
    expect(standard.locator("input")).to_be_checked()
    expect(standard).to_contain_text("Free if you add $30.01 more")
    expect(shop.page.locator("#delivery-fee")).to_have_text("$5.00")
    expect(shop.page.locator("#total-payable")).to_have_text("$24.99")

    shop.after_api("/api/checkout", lambda: shop.page.locator("#method-choices .choice", has_text="Express").click())
    expect(shop.page.locator("#delivery-fee")).to_have_text("$15.00")
    expect(shop.page.locator("#total-payable")).to_have_text("$34.99")

    # A new address is saved to the address book and chosen.
    shop.page.click("#add-address-btn")
    fill_address(shop.page.locator("#new-address-form"), NEW_ADDRESS)
    shop.after_api("/api/checkout", lambda: shop.page.click("#save-address-btn"))
    expect(shop.page.locator("#address-choices .choice:has(input:checked)")).to_contain_text("Alice at Work")
    expect(shop.page.locator("#total-payable")).to_have_text("$34.99")

    shop.page.click("#continue-btn")
    shop.page.wait_for_url("**/payment.html?*")
    expect(shop.page.locator("#delivery-address")).to_contain_text("500 Office Park")
    expect(shop.page.locator("#delivery-method")).to_contain_text("Express delivery")
    expect(shop.page.locator("#place-order-btn")).to_contain_text("$34.99")

    # Going back keeps the choice.
    shop.page.click("#change-delivery")
    shop.page.wait_for_url("**/checkout.html?*")
    expect(shop.page.locator("#address-choices .choice:has(input:checked)")).to_contain_text("Alice at Work")
    expect(shop.page.locator("#method-choices .choice:has(input:checked)")).to_contain_text("Express delivery")

    shop.page.click("#continue-btn")
    shop.page.click("#place-order-btn")
    on_mock_provider(shop)
    expect(shop.page.locator(".order-meta")).to_contain_text("Paid")
    expect(shop.page.locator("#order-delivery-fee")).to_have_text("$15.00")
    expect(shop.page.locator("#order-delivery")).to_contain_text("Chicago, IL 60601")
    expect(shop.page.locator("#order-delivery")).to_contain_text("Express delivery")


def test_free_delivery_over_the_threshold(shop):
    shop.login("alice")
    buy_now(shop, 1, "S", 3)  # 59.97 reaches the 50.00 threshold of standard delivery
    expect(shop.page.locator("#method-choices .choice", has_text="Standard delivery")).to_contain_text("Free")
    expect(shop.page.locator("#delivery-fee")).to_have_text("Free")
    expect(shop.page.locator("#total-payable")).to_have_text("$59.97")


def test_address_book_and_checkout_without_addresses(shop):
    shop.login("bob")
    shop.page.click(".nav >> text=Account")
    expect(shop.page.locator(".address-card")).to_have_count(1)

    shop.page.click("#add-address-btn")
    fill_address(shop.page.locator("#address-form"), {**NEW_ADDRESS, "full_name": "Bob at Work"})
    shop.page.check("[name=make_default]")
    shop.after_api("/api/account/addresses", lambda: shop.page.click("#address-save-btn"))
    expect(shop.page.locator("#address-message")).to_have_text("The address has been saved.")
    expect(shop.page.locator(".address-card.is-default")).to_contain_text("Bob at Work")

    work = shop.page.locator(".address-card", has_text="Bob at Work")
    work.locator("[data-act=edit]").click()
    shop.page.fill("#address-form [name=city]", "Evanston")
    shop.after_api("/api/account/addresses", lambda: shop.page.click("#address-save-btn"))
    expect(work).to_contain_text("Evanston, IL 60601")

    # Problems are listed together.
    shop.page.click("#add-address-btn")
    shop.page.fill("#address-form [name=phone]", "abc")
    shop.after_api("/api/account/addresses", lambda: shop.page.click("#address-save-btn"))
    expect(shop.page.locator("#address-message")).to_contain_text("Full name is required.")
    expect(shop.page.locator("#address-message")).to_contain_text("Phone number must have at least 6 digits")
    shop.page.click("#address-cancel-btn")

    for _ in range(2):
        shop.page.locator(".address-card [data-act=delete]").first.click()
        shop.after_api("/api/account/addresses", lambda: shop.page.click("[data-answer=yes]"))
    expect(shop.page.locator("#address-list")).to_contain_text("You have no saved addresses yet.")

    # Without addresses, checkout asks for one straight away (FR105).
    buy_now(shop, 7, "S", 1)
    expect(shop.page.locator("#new-address-form")).to_contain_text("Where should we deliver your order?")
    expect(shop.page.locator("#continue-btn")).to_be_disabled()
    expect(shop.page.locator("#new-address-form")).to_contain_text("United States")  # the only delivery country
    fill_address(shop.page.locator("#new-address-form"), {**NEW_ADDRESS, "full_name": "Bob Again"})
    shop.after_api("/api/checkout", lambda: shop.page.click("#save-address-btn"))
    expect(shop.page.locator("#address-choices .choice:has(input:checked)")).to_contain_text("Bob Again")
    expect(shop.page.locator("#continue-btn")).to_be_enabled()


def test_admin_manages_delivery_methods(shop):
    shop.login("admin", role="admin")
    shop.page.click(".nav >> text=Delivery")
    shop.page.wait_for_url("**/admin-shipping.html")
    expect(shop.page.locator("#method-rows tr")).to_have_count(2)

    shop.page.click("#add-btn")
    shop.page.fill("#name-input", "Store pickup")
    shop.page.fill("#description-input", "Collect from our store")
    shop.page.fill("#fee-input", "abc")
    shop.after_api("/api/admin/shipping-methods", lambda: shop.page.click("#save-btn"))
    expect(shop.page.locator("#form-message")).to_contain_text("Fee must be an amount from 0.00 to 1000.00")
    shop.page.fill("#fee-input", "0")
    shop.after_api("/api/admin/shipping-methods", lambda: shop.page.click("#save-btn"))
    pickup = shop.page.locator("#method-rows tr", has_text="Store pickup")
    expect(pickup).to_contain_text("Free")
    expect(pickup).to_contain_text("Active")

    shop.after_api("/api/admin/shipping-methods", lambda: pickup.locator("[data-act=toggle]").click())
    expect(pickup).to_contain_text("Inactive")
    pickup.locator("[data-act=delete]").click()
    shop.after_api("/api/admin/shipping-methods", lambda: shop.page.click("[data-answer=yes]"))
    expect(shop.page.locator("#method-rows tr")).to_have_count(2)

    # With no active method nobody can order, and the page says so (FR104).
    for name in ("Standard delivery", "Express delivery"):
        row = shop.page.locator("#method-rows tr", has_text=name)
        shop.after_api("/api/admin/shipping-methods", lambda row=row: row.locator("[data-act=toggle]").click())
    expect(shop.page.locator("#list-message")).to_contain_text("No delivery method is active")
    for name in ("Standard delivery", "Express delivery"):
        row = shop.page.locator("#method-rows tr", has_text=name)
        shop.after_api("/api/admin/shipping-methods", lambda row=row: row.locator("[data-act=toggle]").click())
    expect(shop.page.locator("#list-message")).not_to_contain_text("No delivery method is active")
    expect(shop.page.locator("#method-rows")).not_to_contain_text(re.compile("Inactive"))
