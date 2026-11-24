"""Backend: CRUD de usuarios (solo administradores) y reglas de negocio."""
import pytest

from conftest import ADMIN_EMAIL, unique

pytestmark = pytest.mark.api


@pytest.mark.smoke
def test_list_users_contains_admin(api):
    r = api.get("/api/users")
    assert r.status == 200
    assert ADMIN_EMAIL in [u["email"] for u in r.json()["items"]]


def test_create_user(api, cleanup, anon):
    email = f"{unique()}@example.com"
    r = api.post("/api/users", data={"name": "Ana López", "email": email, "password": "Segura2026", "role": "user"})
    assert r.status == 201
    u = r.json()
    cleanup(f"/api/users/{u['id']}")
    assert u["email"] == email and u["role"] == "user" and u["is_active"] is True
    assert "password" not in u and "password_hash" not in u
    assert anon.post("/api/auth/login", data={"email": email, "password": "Segura2026"}).status == 200


def test_email_is_stored_lowercase(make_user):
    u = make_user(email=f"{unique().upper()}@EXAMPLE.COM")
    assert u["email"] == u["email"].lower()


def test_get_user(api, make_user):
    u = make_user()
    r = api.get(f"/api/users/{u['id']}")
    assert r.status == 200 and r.json()["email"] == u["email"]


def test_update_user(api, make_user):
    u = make_user()
    r = api.put(f"/api/users/{u['id']}", data={"name": "Nombre Nuevo", "role": "admin"})
    assert r.status == 200
    assert r.json()["name"] == "Nombre Nuevo" and r.json()["role"] == "admin"


def test_change_password(api, make_user, anon):
    u = make_user()
    assert api.put(f"/api/users/{u['id']}", data={"password": "OtraClave99"}).status == 200
    assert anon.post("/api/auth/login", data={"email": u["email"], "password": u["password"]}).status == 401
    assert anon.post("/api/auth/login", data={"email": u["email"], "password": "OtraClave99"}).status == 200


def test_delete_user(api, make_user):
    u = make_user()
    assert api.delete(f"/api/users/{u['id']}").status == 204
    assert api.get(f"/api/users/{u['id']}").status == 404


def test_duplicate_email_is_rejected(api, make_user):
    u = make_user()
    r = api.post("/api/users", data={"name": "Copia", "email": u["email"], "password": "Secreta123"})
    assert r.status == 409


def test_update_to_existing_email_is_rejected(api, make_user):
    a, b = make_user(), make_user()
    assert api.put(f"/api/users/{b['id']}", data={"email": a["email"]}).status == 409


@pytest.mark.parametrize("field,value", [
    ("email", "sin-arroba"), ("password", "corta"), ("name", "A"), ("role", "superusuario"),
])
def test_user_validation(api, field, value):
    body = {"name": "Usuario Válido", "email": f"{unique()}@example.com", "password": "Secreta123"} | {field: value}
    r = api.post("/api/users", data=body)
    assert r.status == 422
    assert field in [e["field"] for e in r.json()["errors"]]


def test_admin_cannot_delete_himself(api, admin_token):
    r = api.delete(f"/api/users/{admin_token['user']['id']}")
    assert r.status == 400


def test_admin_cannot_demote_himself(api, admin_token):
    r = api.put(f"/api/users/{admin_token['user']['id']}", data={"role": "user"})
    assert r.status == 400


def test_search_users(api, make_user):
    tag = unique("persona")
    u = make_user(name=f"Persona {tag}")
    r = api.get(f"/api/users?q={tag}").json()
    assert r["total"] == 1 and r["items"][0]["id"] == u["id"]
