"""Backend: CRUD de productos, validaciones, búsqueda y ordenamiento."""
from decimal import Decimal

import pytest

from conftest import unique

pytestmark = pytest.mark.api


@pytest.mark.smoke
def test_list_products(api):
    r = api.get("/api/products")
    assert r.status == 200
    body = r.json()
    assert body["total"] >= len(body["items"]) and isinstance(body["items"], list)


def test_create_product(api, cleanup):
    sku = unique("new").upper()
    r = api.post("/api/products", data={"sku": sku, "name": "Cable HDMI", "price": "149.50", "stock": 30,
                                         "category": "Accesorios", "description": "2 metros"})
    assert r.status == 201
    p = r.json()
    cleanup(f"/api/products/{p['id']}")
    assert p["sku"] == sku and p["name"] == "Cable HDMI" and Decimal(p["price"]) == Decimal("149.50")
    assert p["stock"] == 30 and p["id"] > 0 and p["created_at"]


def test_sku_is_stored_uppercase(make_product):
    p = make_product(sku=unique("low").lower())
    assert p["sku"] == p["sku"].upper()


def test_get_product_by_id(api, make_product):
    p = make_product()
    r = api.get(f"/api/products/{p['id']}")
    assert r.status == 200 and r.json()["sku"] == p["sku"]


def test_update_product(api, make_product):
    p = make_product()
    r = api.put(f"/api/products/{p['id']}", data={"name": "Nombre editado", "price": "120.00", "stock": 7})
    assert r.status == 200
    u = r.json()
    assert u["name"] == "Nombre editado" and Decimal(u["price"]) == Decimal("120.00") and u["stock"] == 7
    assert u["sku"] == p["sku"]  # lo no enviado no cambia


def test_delete_product(api, make_product):
    p = make_product()
    assert api.delete(f"/api/products/{p['id']}").status == 204
    assert api.get(f"/api/products/{p['id']}").status == 404


def test_product_not_found(api):
    for method in ("get", "put", "delete"):
        kwargs = {"data": {"name": "x" * 3}} if method == "put" else {}
        assert getattr(api, method)("/api/products/99999999", **kwargs).status == 404


def test_duplicate_sku_is_rejected(api, make_product):
    p = make_product()
    r = api.post("/api/products", data={"sku": p["sku"].lower(), "name": "Otro", "price": "1.00", "stock": 1})
    assert r.status == 409
    assert "SKU" in r.json()["detail"]


def test_update_to_existing_sku_is_rejected(api, make_product):
    a, b = make_product(), make_product()
    assert api.put(f"/api/products/{b['id']}", data={"sku": a["sku"]}).status == 409


@pytest.mark.parametrize("field,value", [
    ("price", "0"), ("price", "-5"), ("stock", -1), ("sku", "ab"), ("sku", "con espacio"),
    ("name", "x"), ("price", "abc"),
])
def test_product_validation(api, field, value):
    body = {"sku": unique("VAL").upper(), "name": "Producto válido", "price": "10.00", "stock": 1} | {field: value}
    r = api.post("/api/products", data=body)
    assert r.status == 422
    assert field in [e["field"] for e in r.json()["errors"]]


def test_search_by_name_and_sku(api, make_product):
    tag = unique("busca")
    p = make_product(name=f"Producto {tag}")
    by_name = api.get(f"/api/products?q={tag}").json()
    assert by_name["total"] == 1 and by_name["items"][0]["id"] == p["id"]
    by_sku = api.get(f"/api/products?q={p['sku'].lower()}").json()
    assert [i["id"] for i in by_sku["items"]] == [p["id"]]


def test_filter_by_category(api, make_product):
    cat = unique("Cat")
    make_product(category=cat)
    make_product(category=cat)
    r = api.get(f"/api/products?category={cat}").json()
    assert r["total"] == 2 and all(i["category"] == cat for i in r["items"])
    assert cat in api.get("/api/products/categories").json()


def test_sort_by_price_desc(api):
    items = api.get("/api/products?sort=-price&limit=200").json()["items"]
    prices = [Decimal(i["price"]) for i in items]
    assert prices == sorted(prices, reverse=True)


def test_invalid_sort_is_rejected(api):
    assert api.get("/api/products?sort=password").status == 422


def test_pagination(api, make_product):
    make_product()
    make_product()
    page = api.get("/api/products?limit=1&skip=1").json()
    assert len(page["items"]) == 1 and page["total"] >= 2
