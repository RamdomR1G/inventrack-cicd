"""Backend: salud del servicio, inicio de sesión y protección de rutas."""
import pytest

from conftest import ADMIN_EMAIL, ADMIN_PASSWORD

pytestmark = pytest.mark.api


@pytest.mark.smoke
def test_health(anon):
    r = anon.get("/api/health")
    assert r.status == 200
    assert r.json()["status"] == "ok"


@pytest.mark.smoke
def test_login_ok_returns_token_and_user(anon):
    r = anon.post("/api/auth/login", data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status == 200
    body = r.json()
    assert body["token_type"] == "bearer" and len(body["access_token"]) > 20
    assert body["user"]["email"] == ADMIN_EMAIL and body["user"]["role"] == "admin"
    assert "password" not in body["user"] and "password_hash" not in body["user"]


def test_login_email_is_case_insensitive(anon):
    r = anon.post("/api/auth/login", data={"email": ADMIN_EMAIL.upper(), "password": ADMIN_PASSWORD})
    assert r.status == 200


@pytest.mark.parametrize("email,password", [
    (ADMIN_EMAIL, "incorrecta"),
    ("nadie@example.com", ADMIN_PASSWORD),
])
def test_login_wrong_credentials(anon, email, password):
    r = anon.post("/api/auth/login", data={"email": email, "password": password})
    assert r.status == 401
    assert r.json()["detail"] == "Correo o contraseña incorrectos"


@pytest.mark.parametrize("body", [{}, {"email": "no-es-correo", "password": "x"}, {"email": ADMIN_EMAIL, "password": ""}])
def test_login_invalid_payload(anon, body):
    assert anon.post("/api/auth/login", data=body).status == 422


def test_me_returns_current_user(api):
    r = api.get("/api/auth/me")
    assert r.status == 200 and r.json()["email"] == ADMIN_EMAIL


@pytest.mark.parametrize("path", ["/api/auth/me", "/api/products", "/api/users", "/api/products/categories"])
def test_protected_routes_require_token(anon, path):
    r = anon.get(path)
    assert r.status == 401


def test_invalid_token_is_rejected(anon):
    r = anon.get("/api/products", headers={"Authorization": "Bearer no.es.valido"})
    assert r.status == 401
    assert r.json()["detail"] == "Token inválido"


def test_inactive_user_cannot_login(anon, make_user):
    u = make_user(is_active=False)
    r = anon.post("/api/auth/login", data={"email": u["email"], "password": u["password"]})
    assert r.status == 403


def test_regular_user_cannot_manage_users(anon, make_user, playwright, base_url):
    u = make_user()
    token = anon.post("/api/auth/login", data={"email": u["email"], "password": u["password"]}).json()["access_token"]
    ctx = playwright.request.new_context(base_url=base_url, extra_http_headers={"Authorization": f"Bearer {token}"})
    try:
        assert ctx.get("/api/users").status == 403
        assert ctx.get("/api/products").status == 200  # pero sí puede ver productos
    finally:
        ctx.dispose()
