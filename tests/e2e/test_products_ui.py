"""Frontend: CRUD de productos desde la interfaz."""
import pytest
from playwright.sync_api import Page, expect

from conftest import unique

pytestmark = pytest.mark.e2e


def fill_product(page: Page, sku, name, price="250.00", stock="12", category="Pruebas UI", description=""):
    page.get_by_test_id("product-sku").fill(sku)
    page.get_by_test_id("product-name").fill(name)
    page.get_by_test_id("product-category").fill(category)
    page.get_by_test_id("product-price").fill(price)
    page.get_by_test_id("product-stock").fill(stock)
    page.get_by_test_id("product-description").fill(description)


def row(page: Page, text):
    return page.get_by_test_id("product-row").filter(has_text=text)


@pytest.mark.smoke
def test_products_table_shows_seed_data(admin_page: Page):
    expect(admin_page.get_by_test_id("product-row").first).to_be_visible()
    expect(admin_page.get_by_test_id("products-table").locator("th")).to_have_text(
        ["SKU", "Nombre", "Categoría", "Precio", "Stock", ""])


def test_create_product_ui(admin_page: Page, api):
    sku, name = unique("UI").upper(), f"Audífonos {unique()}"
    admin_page.get_by_test_id("product-new").click()
    expect(admin_page.get_by_role("dialog")).to_contain_text("Nuevo producto")
    fill_product(admin_page, sku, name, price="899.00", stock="5", description="Bluetooth 5.3")
    admin_page.get_by_test_id("product-save").click()
    expect(admin_page.get_by_test_id("toast")).to_have_text("Producto creado")
    expect(admin_page.get_by_role("dialog")).to_have_count(0)
    r = row(admin_page, sku)
    expect(r).to_contain_text(name)
    expect(r).to_contain_text("$899.00")
    created = api.get(f"/api/products?q={sku}").json()["items"][0]
    api.delete(f"/api/products/{created['id']}")


def test_create_product_validation_ui(admin_page: Page):
    admin_page.get_by_test_id("product-new").click()
    fill_product(admin_page, "x", "", price="0", stock="-2", category="")
    admin_page.get_by_test_id("product-save").click()
    expect(admin_page.get_by_test_id("error-sku")).to_be_visible()
    expect(admin_page.get_by_test_id("error-name")).to_have_text("El nombre debe tener al menos 2 caracteres")
    expect(admin_page.get_by_test_id("error-price")).to_have_text("El precio debe ser mayor que 0")
    expect(admin_page.get_by_test_id("error-stock")).to_be_visible()
    expect(admin_page.get_by_test_id("error-category")).to_be_visible()
    expect(admin_page.get_by_role("dialog")).to_be_visible()


def test_duplicate_sku_ui(admin_page: Page, make_product):
    p = make_product()
    admin_page.get_by_test_id("product-new").click()
    fill_product(admin_page, p["sku"], "Duplicado")
    admin_page.get_by_test_id("product-save").click()
    expect(admin_page.get_by_test_id("error-sku")).to_have_text("Ya existe un producto con ese SKU")


def test_edit_product_ui(admin_page: Page, make_product):
    p = make_product()
    admin_page.reload()
    row(admin_page, p["sku"]).get_by_test_id("product-edit").click()
    expect(admin_page.get_by_test_id("product-sku")).to_have_value(p["sku"])
    admin_page.get_by_test_id("product-name").fill("Producto editado en UI")
    admin_page.get_by_test_id("product-stock").fill("3")
    admin_page.get_by_test_id("product-save").click()
    expect(admin_page.get_by_test_id("toast")).to_have_text("Producto actualizado")
    r = row(admin_page, p["sku"])
    expect(r).to_contain_text("Producto editado en UI")
    expect(r.locator(".badge-low")).to_have_text("3")


def test_delete_product_ui(admin_page: Page, make_product):
    p = make_product()
    admin_page.reload()
    row(admin_page, p["sku"]).get_by_test_id("product-delete").click()
    expect(admin_page.get_by_test_id("confirm-dialog")).to_contain_text(p["sku"])
    admin_page.get_by_test_id("confirm-delete").click()
    expect(admin_page.get_by_test_id("toast")).to_have_text("Producto eliminado")
    expect(row(admin_page, p["sku"])).to_have_count(0)


def test_cancel_delete_keeps_product(admin_page: Page, make_product):
    p = make_product()
    admin_page.reload()
    row(admin_page, p["sku"]).get_by_test_id("product-delete").click()
    admin_page.get_by_role("button", name="Cancelar").click()
    expect(row(admin_page, p["sku"])).to_have_count(1)


def test_close_modal_with_escape(admin_page: Page):
    admin_page.get_by_test_id("product-new").click()
    expect(admin_page.get_by_role("dialog")).to_be_visible()
    admin_page.keyboard.press("Escape")
    expect(admin_page.get_by_role("dialog")).to_have_count(0)


def test_search_products_ui(admin_page: Page, make_product):
    tag = unique("lupa")
    p = make_product(name=f"Lámpara {tag}")
    admin_page.get_by_test_id("product-search").fill(tag)
    expect(admin_page.get_by_test_id("product-row")).to_have_count(1)
    expect(admin_page.get_by_test_id("product-row")).to_contain_text(p["sku"])
    admin_page.get_by_test_id("product-search").fill("zzz-no-existe-zzz")
    expect(admin_page.get_by_test_id("products-empty")).to_be_visible()


def test_sort_products_by_price_ui(admin_page: Page):
    with admin_page.expect_response(lambda r: "sort=-price" in r.url):
        admin_page.get_by_test_id("product-sort").select_option("-price")
    expect(admin_page.get_by_test_id("product-row").first).to_be_visible()
    prices = admin_page.get_by_test_id("product-row").locator("td.num:nth-child(4)").all_inner_texts()
    values = [float(p.replace("$", "").replace(",", "")) for p in prices]
    assert values == sorted(values, reverse=True)


def test_stats_total_matches_api(admin_page: Page, api):
    total = api.get("/api/products").json()["total"]
    expect(admin_page.get_by_test_id("stat-total")).to_have_text(str(total))
