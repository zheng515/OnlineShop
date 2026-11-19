"""Browsing without an account, registration, email confirmation, password reset, account page
(FR88-FR92, FR98)."""

import re

from playwright.sync_api import expect


def test_visitors_browse_and_are_brought_back_after_logging_in(shop):
    shop.goto("/")
    shop.page.wait_for_url("**/shop.html")
    shop.page.wait_for_selector(".product-card")
    expect(shop.page.locator(".site-header")).to_contain_text("Log in")
    expect(shop.page.locator(".site-header")).to_contain_text("Register")

    shop.goto("/product.html?id=1")
    shop.page.click("[data-size=L]")
    shop.page.fill("#qty-input", "2")
    shop.page.click("#add-cart-btn")
    shop.page.wait_for_url("**/login.html?next=*")
    expect(shop.page.locator("#login-error")).to_have_text("Please log in or create an account to continue.")

    shop.page.fill("#username", "bob")
    shop.page.fill("#password", "bob12345")
    shop.page.click("#login-btn")
    shop.page.wait_for_url(re.compile(r"/product\.html\?id=1&size=L&quantity=2$"))
    expect(shop.page.locator(".size-option.selected")).to_contain_text("L")
    shop.after_api("/api/cart/items", lambda: shop.page.click("#add-cart-btn"))
    expect(shop.page.locator("#cart-count")).to_have_text("2")


def test_login_only_returns_to_shop_pages(shop):
    for target in ("https://evil.example/", "//evil.example/x", "/\\evil.example"):
        shop.page.goto(f"{shop.url}/login.html?next={target}")
        shop.page.fill("#username", "bob")
        shop.page.fill("#password", "bob12345")
        shop.page.click("#login-btn")
        shop.page.wait_for_url(f"{shop.url}/shop.html")
        shop.logout()


def test_register_confirm_and_log_in(shop):
    shop.goto("/login.html")
    shop.page.click("text=Create an account")
    shop.page.wait_for_url("**/register.html")
    shop.page.fill("#username", "erin")
    shop.page.fill("#email", "Erin@Example.com")
    shop.page.fill("#display-name", "Erin")
    shop.page.fill("#password", "erinPass1")
    shop.page.fill("#password-confirm", "erinPass1")
    shop.page.click("#submit-btn")
    expect(shop.page.locator("#message")).to_contain_text("Check your email")

    # Logging in before confirming is refused, with an offer to resend the email.
    shop.goto("/login.html")
    shop.page.fill("#username", "erin")
    shop.page.fill("#password", "erinPass1")
    shop.page.click("#login-btn")
    expect(shop.page.locator("#login-error")).to_contain_text("Please confirm your email address first")
    shop.page.click("#resend-btn")
    expect(shop.page.locator("#login-error")).to_contain_text("we have sent an email")

    shop.page.goto(shop.last_email_link("erin@example.com", "verify_email"))
    expect(shop.page.locator("#message")).to_contain_text("Your email address is confirmed")
    assert "token" not in shop.page.url
    shop.page.click("#message a.btn")
    shop.page.fill("#username", "erin@example.com")
    shop.page.fill("#password", "erinPass1")
    shop.page.click("#login-btn")
    shop.page.wait_for_url("**/shop.html")
    expect(shop.page.locator(".user-name")).to_have_text("Erin")


def test_used_confirmation_link_offers_a_new_one(shop):
    shop.goto("/register.html")
    for field, value in (("#username", "fay"), ("#email", "fay@example.com"), ("#display-name", "Fay"),
                         ("#password", "fayPass12"), ("#password-confirm", "fayPass12")):
        shop.page.fill(field, value)
    shop.page.click("#submit-btn")
    expect(shop.page.locator("#message")).to_contain_text("Check your email")
    link = shop.last_email_link("fay@example.com", "verify_email")
    shop.page.goto(link)
    expect(shop.page.locator("#message")).to_contain_text("confirmed")
    shop.page.goto(link)
    expect(shop.page.locator("#message")).to_contain_text("invalid or has expired")
    expect(shop.page.locator("#resend")).to_be_visible()


def test_forgotten_password(shop):
    shop.goto("/login.html")
    shop.page.click("text=Forgot your password?")
    shop.page.fill("#email", "alice@example.com")
    shop.page.click("#submit-btn")
    expect(shop.page.locator("#message")).to_contain_text("If an account with this address needs it")

    shop.page.goto(shop.last_email_link("alice@example.com", "reset_password"))
    shop.page.fill("#password", "aliceNew9")
    shop.page.fill("#password-confirm", "aliceNew9")
    shop.page.click("#submit-btn")
    expect(shop.page.locator("#message")).to_contain_text("Your password has been changed")

    shop.goto("/login.html")
    shop.page.fill("#username", "alice")
    shop.page.fill("#password", "alice123")
    shop.page.click("#login-btn")
    expect(shop.page.locator("#login-error")).to_contain_text("Invalid username or password")
    shop.login("alice", password="aliceNew9")


def test_account_page(shop):
    shop.login("bob")
    shop.page.click(".nav >> text=Account")
    shop.page.wait_for_url("**/account.html")
    expect(shop.page.locator("#email")).to_have_text("bob@example.com")
    shop.page.fill("#display-name", "Bobby")
    shop.after_api("/api/account", lambda: shop.page.click("#profile-btn"))
    expect(shop.page.locator(".user-name")).to_have_text("Bobby")

    shop.page.fill("#current-password", "wrong-one1")
    shop.page.fill("#new-password", "bobNewPass2")
    shop.page.fill("#new-password-confirm", "bobNewPass2")
    shop.after_api("/api/account/password", lambda: shop.page.click("#password-btn"))
    expect(shop.page.locator("#message")).to_have_text("The current password is not correct.")
    shop.page.fill("#current-password", "bob12345")
    shop.after_api("/api/account/password", lambda: shop.page.click("#password-btn"))
    expect(shop.page.locator("#message")).to_contain_text("logged out everywhere else")
    shop.page.reload()
    expect(shop.page.locator("#username")).to_have_text("bob")  # still logged in here
