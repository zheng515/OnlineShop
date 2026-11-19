"""Login, role-based access and logout (FR1-FR6, FR54)."""

from playwright.sync_api import expect


def test_invalid_credentials_show_an_error(shop):
    shop.goto("/")
    shop.page.click("[data-role=admin]")
    shop.page.fill("#username", "admin")
    shop.page.fill("#password", "wrong-password")
    shop.page.click("#login-btn")
    expect(shop.page.locator("#login-error")).to_have_text("Invalid username or password for Administrator Login.")


def test_login_page_shows_no_credentials(shop):
    shop.goto("/")
    for secret in ("admin123", "alice123", "bob12345"):
        assert secret not in shop.page.content()


def test_each_role_lands_on_its_home_and_cannot_open_the_other(shop):
    shop.login("admin", role="admin")
    expect(shop.page.locator("h1")).to_have_text("Product Management")
    shop.goto("/shop.html")
    shop.page.wait_for_url("**/admin.html")
    shop.logout()

    shop.login("alice")
    shop.goto("/admin-orders.html")
    shop.page.wait_for_url("**/shop.html")
    shop.logout()
    shop.goto("/cart.html")
    shop.page.wait_for_url("**/index.html")


def test_session_cookie_is_hidden_from_page_scripts(shop):
    shop.login("bob")
    assert "shop_session" not in shop.page.evaluate("document.cookie")
    assert "shop_csrf" in shop.page.evaluate("document.cookie")
    cookies = {c["name"]: c for c in shop.page.context.cookies()}
    assert cookies["shop_session"]["httpOnly"] and cookies["shop_session"]["sameSite"] == "Lax"
    stored = shop.page.evaluate("JSON.stringify(Object.values(localStorage))")
    assert cookies["shop_session"]["value"] not in stored
