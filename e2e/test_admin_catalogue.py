"""Product, image and category management (FR7-FR14, FR60, FR62)."""

import struct
import zlib

import pytest
from playwright.sync_api import expect


def _png(rgb: tuple[int, int, int]) -> bytes:
    raw = b"".join(b"\x00" + bytes(rgb) * 20 for _ in range(20))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", 20, 20, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


@pytest.fixture
def images(tmp_path):
    files = {}
    for name, colour in (("red", (220, 40, 60)), ("blue", (40, 90, 220)), ("green", (30, 160, 80))):
        files[name] = tmp_path / f"{name}.png"
        files[name].write_bytes(_png(colour))
    files["fake"] = tmp_path / "fake.png"
    files["fake"].write_text("not an image")
    return files


def test_categories_can_be_added_and_deleted(shop):
    shop.login("admin", role="admin")
    shop.page.wait_for_selector("#product-rows tr td img")
    shop.page.click("#categories-btn")
    shop.page.fill("#new-category-input", "Accessories")
    shop.after_api("/api/categories", lambda: shop.page.click("#new-category-form button"))
    shop.page.fill("#new-category-input", "t-shirts")
    shop.after_api("/api/admin/categories", lambda: shop.page.click("#new-category-form button"))
    expect(shop.page.locator("#categories-message")).to_have_text('A category named "T-Shirts" already exists.')

    shop.page.click("#category-rows li:has(input[value='Accessories']) [data-cat-action=delete]")
    expect(shop.page.locator("[role=alertdialog]")).to_contain_text("This category has no products.")
    shop.after_api("/api/categories", lambda: shop.page.click("[role=alertdialog] [data-answer=yes]"))
    names = shop.page.locator("#category-rows input").evaluate_all("inputs => inputs.map(i => i.value)")
    assert "Accessories" not in names


def test_add_product_with_several_images(shop, images):
    shop.login("admin", role="admin")
    shop.page.wait_for_selector("#product-rows tr td img")
    shop.page.click("#add-btn")
    shop.page.set_input_files("#image-input", [images["red"], images["blue"], images["green"], images["fake"]])
    # (String predicates such as wait_for_function would be blocked by the site's CSP.)
    expect(shop.page.locator("#image-manager .image-tile img")).to_have_count(3)
    expect(shop.page.locator("#image-manager .image-tile.uploading")).to_have_count(0)
    expect(shop.page.locator("#form-error")).to_contain_text("fake.png: Unsupported image format")

    # Make the second image the main one, then drop the last.
    shop.page.click("#image-manager .image-tile[data-index='1'] [data-move='-1']")
    shop.page.click("#image-manager .image-tile[data-index='2'] [data-remove]")
    expect(shop.page.locator("#image-manager .image-tile")).to_have_count(2)

    shop.page.fill("#name-input", "Gallery Test Scarf")
    shop.page.fill("#price-input", "15.00")
    shop.page.select_option("#category-input", label="T-Shirts")
    shop.page.fill("#description-input", "Line one\nLine <two>")
    shop.page.check("[data-size=M]")
    shop.page.fill("[data-stock=M]", "3")
    shop.after_api("/api/admin/products?", lambda: shop.page.click("#save-btn"))

    row = shop.page.locator("#product-rows tr", has_text="Gallery Test Scarf")
    expect(row).to_contain_text("2 images")
    expect(row).to_contain_text("T-Shirts")

    # The customer sees the description as text, with the line break kept.
    product_id = shop.page.evaluate("async () => (await api('/api/admin/products?q=Gallery Test')).products[0].id")
    shop.logout()
    shop.login("bob")
    shop.goto(f"/product.html?id={product_id}")
    shop.page.wait_for_selector(".description")
    assert shop.page.locator(".description").inner_text() == "Line one\nLine <two>"  # markup shown as text
    assert shop.page.locator(".description br").count() == 1
    assert shop.page.locator("#thumbs button").count() == 2


def test_edit_validation_and_delete(shop):
    shop.login("admin", role="admin")
    shop.page.wait_for_selector("#product-rows tr td img")
    row = shop.page.locator("#product-rows tr", has_text="Pocket Tee")
    row.locator("[data-action=edit]").click()
    shop.page.fill("#price-input", "0")
    shop.page.click("#save-btn")
    expect(shop.page.locator("#form-error")).to_contain_text("Price must be a number greater than zero")
    shop.page.fill("#price-input", "18.50")
    shop.after_api("/api/admin/products?", lambda: shop.page.click("#save-btn"))
    expect(row).to_contain_text("$18.50")

    shop.after_api("/api/admin/products", lambda: shop.page.select_option("#sort-select", "stock_asc"))
    assert "Graphic Print Tee" in shop.page.locator("#product-rows tr").first.inner_text()

    row.locator("[data-action=delete]").click()
    expect(shop.page.locator("[role=alertdialog]")).to_contain_text("Pocket Tee")
    shop.after_api("/api/admin/products", lambda: shop.page.click("[role=alertdialog] [data-answer=yes]"))
    expect(shop.page.locator("#product-rows")).not_to_contain_text("Pocket Tee")
