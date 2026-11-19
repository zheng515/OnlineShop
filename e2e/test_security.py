"""Cross-site request protection, login throttling and security headers (FR52, FR53, FR55)."""

from playwright.sync_api import expect


def test_security_headers_on_pages(shop):
    response = shop.page.goto(shop.url + "/login.html")
    headers = response.headers
    assert "script-src 'self'" in headers["content-security-policy"]
    assert headers["x-frame-options"] == "DENY"
    assert headers["x-content-type-options"] == "nosniff"


def test_requests_from_another_site_are_rejected(shop, other_origin):
    shop.login("bob")
    cart_before = shop.page.evaluate("async () => (await api('/api/cart')).item_count")

    attacker = shop.page.context.new_page()
    attacker.goto(f"{other_origin}/index.html?target={shop.url}")
    expect(attacker).to_have_title("fetch sent")
    with attacker.expect_navigation():
        attacker.evaluate("document.getElementById('logout-form').submit()")
    expect(attacker.locator("body")).to_contain_text("came from another website")
    attacker.close()

    shop.page.reload()
    shop.page.wait_for_selector(".product-card")
    assert shop.page.url.endswith("/shop.html")  # still logged in
    assert shop.page.evaluate("async () => (await api('/api/cart')).item_count") == cart_before


def test_login_is_locked_after_repeated_failures(shop):
    for attempt in range(5):
        shop.goto("/login.html")
        shop.page.fill("#username", "alice")
        shop.page.fill("#password", f"wrong-{attempt}")
        shop.page.click("#login-btn")
        expect(shop.page.locator("#login-error")).to_contain_text("Invalid username or password")
    shop.page.fill("#username", "alice")
    shop.page.fill("#password", "alice123")
    shop.page.click("#login-btn")
    expect(shop.page.locator("#login-error")).to_have_text("Too many failed login attempts. Please try again in 15 minutes.")
