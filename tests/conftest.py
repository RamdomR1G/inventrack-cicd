"""Fixtures compartidas por las pruebas de API (backend) y E2E (frontend).

La suite corre contra el sistema levantado con Docker Compose (en GitHub Actions)
o contra cualquier URL indicada en BASE_URL.
"""
import os
import time
import uuid

import pytest
from playwright.sync_api import APIRequestContext, Page, Playwright, expect

BASE_URL = os.getenv("BASE_URL", "http://localhost").rstrip("/")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@inventrack.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin123*")

expect.set_options(timeout=10_000)


def unique(prefix="qa"):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session", autouse=True)
def wait_for_app(playwright: Playwright):
    """Espera a que el sistema responda antes de empezar (contenedores recién creados)."""
    ctx = playwright.request.new_context(base_url=BASE_URL)
    last = None
    for _ in range(60):
        try:
            r = ctx.get("/api/health", timeout=5_000)
            if r.ok:
                ctx.dispose()
                return
            last = r.status
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(2)
    ctx.dispose()
    pytest.exit(f"El sistema no respondió en {BASE_URL}: {last}", returncode=3)


@pytest.fixture(scope="session")
def admin_token(playwright: Playwright):
    ctx = playwright.request.new_context(base_url=BASE_URL)
    r = ctx.post("/api/auth/login", data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.ok, f"No se pudo iniciar sesión como administrador: {r.status} {r.text()}"
    data = r.json()
    ctx.dispose()
    return data


@pytest.fixture(scope="session")
def api(playwright: Playwright, admin_token) -> APIRequestContext:
    """Cliente HTTP autenticado como administrador."""
    ctx = playwright.request.new_context(
        base_url=BASE_URL, extra_http_headers={"Authorization": f"Bearer {admin_token['access_token']}"})
    yield ctx
    ctx.dispose()


@pytest.fixture(scope="session")
def anon(playwright: Playwright) -> APIRequestContext:
    """Cliente HTTP sin sesión."""
    ctx = playwright.request.new_context(base_url=BASE_URL)
    yield ctx
    ctx.dispose()


@pytest.fixture
def cleanup(api):
    """Registra recursos creados y los borra al final de la prueba aunque falle."""
    created = []
    yield lambda path: created.append(path)
    for path in reversed(created):
        api.delete(path)


@pytest.fixture
def make_product(api, cleanup):
    def _make(**over):
        body = {"sku": unique("SKU").upper(), "name": f"Producto {unique()}", "category": "Pruebas",
                "price": "99.90", "stock": 15, "description": "Creado por la suite"} | over
        r = api.post("/api/products", data=body)
        assert r.status == 201, r.text()
        p = r.json()
        cleanup(f"/api/products/{p['id']}")
        return p
    return _make


@pytest.fixture
def make_user(api, cleanup):
    def _make(**over):
        body = {"name": f"Usuario {unique()}", "email": f"{unique()}@example.com",
                "password": "Secreta123", "role": "user", "is_active": True} | over
        r = api.post("/api/users", data=body)
        assert r.status == 201, r.text()
        u = r.json() | {"password": body["password"]}
        cleanup(f"/api/users/{u['id']}")
        return u
    return _make


@pytest.fixture
def ui_login(page: Page):
    """Inicia sesión por la interfaz y devuelve la página ya en /productos."""
    def _login(email=ADMIN_EMAIL, password=ADMIN_PASSWORD):
        page.goto(f"{BASE_URL}/login")
        page.get_by_test_id("login-email").fill(email)
        page.get_by_test_id("login-password").fill(password)
        page.get_by_test_id("login-submit").click()
        expect(page).to_have_url(f"{BASE_URL}/productos")
        return page
    return _login


@pytest.fixture
def admin_page(page: Page, admin_token) -> Page:
    """Página con la sesión del administrador ya guardada (sin pasar por el formulario)."""
    page.goto(f"{BASE_URL}/login")
    page.evaluate(
        "([t, u]) => { localStorage.setItem('inventrack_token', t); localStorage.setItem('inventrack_user', u) }",
        [admin_token["access_token"], __import__("json").dumps(admin_token["user"])])
    page.goto(f"{BASE_URL}/productos")
    expect(page.get_by_test_id("products-table")).to_be_visible()
    return page
