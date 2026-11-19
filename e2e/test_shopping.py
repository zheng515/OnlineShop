"""Cart, checkout, placing, paying and cancelling orders, and admin order management (FR19-FR34, FR41-FR49, FR78-FR86)."""

import re

from playwright.sync_api import expect


def stock_label(shop, product_id: int, size: str) -> str:
    shop.goto(f"/product.html?id={product_id}")
    return shop.page.locator(f"[data-size={size}] small").inner_text()


def on_mock_provider(shop, outcome: str = "succeed") -> None:
    """On the mock provider's page, choose an outcome and come back to the order (FR84)."""
    shop.page.wait_for_url("**/mock-pay.html?session=mock_*")
    expect(shop.page.locator(".mockpay-banner")).to_contain_text("No real money is charged")
    shop.page.click(f"[data-outcome={outcome}]")
    shop.page.wait_for_url(re.compile(r"/order\.html\?id=\d+"))


def add(shop, product_id: int, size: str, quantity: int) -> None:
    shop.goto(f"/product.html?id={product_id}")
    shop.page.click(f"[data-size={size}]")
    shop.page.fill("#qty-input", str(quantity))
    shop.after_api("/api/cart/items", lambda: shop.page.click("#add-cart-btn"))


def test_cart_order_and_cancellation(shop):
    shop.login("alice")
    assert stock_label(shop, 1, "S") == "12 in stock"
    add(shop, 1, "S", 2)
    add(shop, 1, "S", 1)  # merged with the existing entry
    add(shop, 3, "M", 1)
    expect(shop.page.locator("#cart-count")).to_have_text("4")

    shop.goto("/cart.html")
    shop.page.wait_for_selector("#cart-rows")
    assert shop.page.locator("#cart-rows tr").count() == 2
    first_row = shop.page.locator("#cart-rows tr").first
    shop.after_api("/api/cart/items", lambda: first_row.locator("[data-step='-1']").click())
    expect(shop.page.locator(".summary-box .total")).to_contain_text("$98.98")  # 2 × 19.99 + 59.00

    shop.page.click("#checkout-btn")
    shop.page.wait_for_url("**/checkout.html?source=cart")
    shop.page.click("#continue-btn")
    shop.page.wait_for_url("**/payment.html**")
    expect(shop.page.locator("#place-order-btn")).to_have_text("Place Order and Pay · $98.98")
    expect(shop.page.locator(".alert-warning")).to_contain_text("no real money is charged")
    shop.page.click("#place-order-btn")
    expect(shop.page.locator(".mockpay-amount")).to_contain_text("$98.98")
    on_mock_provider(shop)
    expect(shop.page.locator("#order-message")).to_contain_text("Your payment has been received.")
    expect(shop.page.locator(".order-meta")).to_contain_text("Paid")
    expect(shop.page.locator(".payment-list")).to_contain_text("Payment $98.98 · Paid")
    assert stock_label(shop, 1, "S") == "10 in stock"

    shop.goto("/orders.html")
    shop.page.click("tbody tr >> nth=0")
    shop.page.click("[data-action=cancelled]")
    expect(shop.page.locator("[role=alertdialog]")).to_contain_text("$98.98 will be refunded")
    shop.page.click("[role=alertdialog] [data-answer=yes]")
    expect(shop.page.locator(".order-meta")).to_contain_text("Cancelled")
    expect(shop.page.locator(".payment-list")).to_contain_text("Refund $98.98 · Refunded · Order cancelled")
    expect(shop.page.locator(".timeline")).to_contain_text("Cancelled by alice")
    assert stock_label(shop, 1, "S") == "12 in stock"


def test_stock_limits_and_buy_now_return(shop):
    shop.login("bob")
    shop.goto("/product.html?id=3")
    shop.page.click("[data-size=XL]")
    shop.page.fill("#qty-input", "2")
    shop.after_api("/api/cart/items", lambda: shop.page.click("#add-cart-btn"))
    shop.page.fill("#qty-input", "1")
    shop.after_api("/api/cart/items", lambda: shop.page.click("#add-cart-btn"))
    expect(shop.page.locator("#action-message")).to_have_text("Only 2 available in size XL. You already have 2 in your cart.")

    shop.page.click("[data-size=M]")
    shop.page.click("#buy-now-btn")
    shop.page.wait_for_url("**/checkout.html?source=buy_now**")
    shop.page.wait_for_selector("#continue-btn")
    shop.page.click("#back-link")
    expect(shop.page.locator(".size-option.selected")).to_contain_text("M")


def test_price_change_while_paying_and_double_click(shop):
    shop.login("bob")
    shop.goto("/product.html?id=6")
    shop.page.click("[data-size=L]")
    shop.page.click("#buy-now-btn")
    shop.page.click("#continue-btn")
    shop.page.wait_for_selector("#place-order-btn")

    # An administrator changes the price meanwhile, in another browser.
    admin = shop.page.context.browser.new_context().new_page()
    admin.goto(shop.url + "/")
    admin.click("[data-role=admin]")
    admin.fill("#username", "admin")
    admin.fill("#password", "admin123")
    admin.click("#login-btn")
    admin.wait_for_url("**/admin.html")
    admin.evaluate(
        """async () => {
          const p = await api('/api/admin/products/6');
          await api('/api/admin/products/6', { method: 'PUT', json: {
            name: p.name, price: '79.99', description: p.description, category_id: p.category && p.category.id,
            stock: Object.fromEntries(p.sizes.map(s => [s.size, s.stock])), image_ids: p.images.map(i => i.id) } });
        }"""
    )
    admin.context.close()

    shop.page.click("#place-order-btn")
    expect(shop.page.locator("#payment-message")).to_contain_text("Prices have changed")
    expect(shop.page.locator("#place-order-btn")).to_have_text("Place Order and Pay · $79.99")
    shop.page.dblclick("#place-order-btn")
    on_mock_provider(shop)
    assert shop.page.evaluate("async () => (await api('/api/orders')).count") == 1


def test_admin_moves_an_order_through_its_statuses(shop):
    shop.login("alice")
    shop.goto("/product.html?id=7")
    shop.page.click("[data-size=S]")
    shop.page.click("#buy-now-btn")
    shop.page.click("#continue-btn")
    shop.page.click("#place-order-btn")
    on_mock_provider(shop)
    shop.logout()

    shop.login("admin", role="admin")
    shop.page.click(".nav >> text=Orders")
    shop.page.wait_for_selector("tr[data-id]")
    shop.after_api("/api/admin/orders", lambda: shop.page.select_option("#status-filter", "paid"))
    shop.page.click("tr[data-id] >> nth=0")
    expect(shop.page.locator("#detail-actions")).to_have_text(re.compile("Mark as Shipped.*Cancel Order", re.S))
    shop.after_api("/status", lambda: shop.page.click("[data-action=shipped]"))
    shop.after_api("/status", lambda: shop.page.click("[data-action=completed]"))
    expect(shop.page.locator("#detail-body .timeline")).to_contain_text("Completed by administrator admin")
    expect(shop.page.locator("#detail-actions")).to_have_text("")


def test_declined_payment_then_pay_now(shop):
    shop.login("bob")
    shop.goto("/product.html?id=8")
    shop.page.click("[data-size=M]")
    shop.page.click("#buy-now-btn")
    shop.page.click("#continue-btn")
    shop.page.click("#place-order-btn")
    on_mock_provider(shop, "fail")
    expect(shop.page.locator("#order-message")).to_contain_text("The card was declined (simulated).")
    expect(shop.page.locator(".order-meta")).to_contain_text("Awaiting payment")
    expect(shop.page.locator("#countdown")).to_have_text(re.compile(r"^(29|30):\d\d$"))

    shop.page.click("#pay-btn")
    on_mock_provider(shop)
    expect(shop.page.locator(".order-meta")).to_contain_text("Paid")
    expect(shop.page.locator(".payment-list li")).to_have_count(2)
    expect(shop.page.locator("#pay-btn")).to_have_count(0)


def test_leaving_the_payment_page_keeps_the_order_waiting(shop):
    shop.login("bob")
    shop.goto("/product.html?id=12")
    shop.page.click("[data-size=L]")
    shop.page.click("#buy-now-btn")
    shop.page.click("#continue-btn")
    shop.page.click("#place-order-btn")
    on_mock_provider(shop, "cancel")
    expect(shop.page.locator("#order-message")).to_contain_text("You left the payment page without paying")
    shop.goto("/orders.html")
    expect(shop.page.locator("tbody tr").first).to_contain_text(re.compile(r"Awaiting payment.*Pay within (29|30) min", re.S))

    # An unpaid order cannot be shipped.
    order_id = shop.page.evaluate("async () => (await api('/api/orders')).orders[0].id")
    shop.logout()
    shop.login("admin", role="admin")
    shop.goto("/admin-orders.html")
    shop.page.wait_for_selector("tr[data-id]")
    shop.page.click(f"tr[data-id='{order_id}']")
    expect(shop.page.locator("#detail-actions")).to_have_text("Cancel Order")
