"""Frontend: CRUD de usuarios desde la interfaz (rol administrador)."""
import pytest
from playwright.sync_api import Page, expect

from conftest import ADMIN_EMAIL, BASE_URL, unique

pytestmark = pytest.mark.e2e


@pytest.fixture
def users_page(admin_page: Page) -> Page:
    admin_page.get_by_test_id("nav-usuarios").click()
    expect(admin_page.get_by_test_id("users-table")).to_be_visible()
    return admin_page


def row(page: Page, text):
    return page.get_by_test_id("user-row").filter(has_text=text)


@pytest.mark.smoke
def test_users_table_lists_admin(users_page: Page):
    expect(row(users_page, ADMIN_EMAIL)).to_contain_text("(tú)")
    expect(row(users_page, ADMIN_EMAIL).get_by_test_id("user-delete")).to_have_count(0)


def test_create_user_ui(users_page: Page, api, page: Page):
    email = f"{unique()}@example.com"
    users_page.get_by_test_id("user-new").click()
    users_page.get_by_test_id("user-name").fill("María Pérez")
    users_page.get_by_test_id("user-email").fill(email)
    users_page.get_by_test_id("user-password").fill("ClaveSegura1")
    users_page.get_by_test_id("user-save").click()
    expect(users_page.get_by_test_id("toast")).to_have_text("Usuario creado")
    r = row(users_page, email)
    expect(r).to_contain_text("María Pérez")
    expect(r).to_contain_text("Usuario")
    expect(r).to_contain_text("Activo")
    created = api.get(f"/api/users?q={email}").json()["items"][0]
    api.delete(f"/api/users/{created['id']}")


def test_create_user_validation_ui(users_page: Page):
    users_page.get_by_test_id("user-new").click()
    users_page.get_by_test_id("user-email").fill("correo-malo")
    users_page.get_by_test_id("user-password").fill("123")
    users_page.get_by_test_id("user-save").click()
    expect(users_page.get_by_test_id("error-name")).to_be_visible()
    expect(users_page.get_by_test_id("error-email")).to_have_text("Correo electrónico inválido")
    expect(users_page.get_by_test_id("error-password")).to_have_text("La contraseña debe tener al menos 8 caracteres")


def test_duplicate_email_ui(users_page: Page, make_user):
    u = make_user()
    users_page.get_by_test_id("user-new").click()
    users_page.get_by_test_id("user-name").fill("Repetido")
    users_page.get_by_test_id("user-email").fill(u["email"])
    users_page.get_by_test_id("user-password").fill("ClaveSegura1")
    users_page.get_by_test_id("user-save").click()
    expect(users_page.get_by_test_id("error-email")).to_have_text("Ya existe un usuario con ese correo")


def test_edit_user_role_ui(users_page: Page, make_user):
    u = make_user()
    users_page.reload()
    row(users_page, u["email"]).get_by_test_id("user-edit").click()
    expect(users_page.get_by_test_id("user-email")).to_have_value(u["email"])
    users_page.get_by_test_id("user-role").select_option("admin")
    users_page.get_by_test_id("user-save").click()
    expect(users_page.get_by_test_id("toast")).to_have_text("Usuario actualizado")
    expect(row(users_page, u["email"])).to_contain_text("Administrador")


def test_deactivate_user_ui_blocks_login(users_page: Page, make_user, anon):
    u = make_user()
    users_page.reload()
    row(users_page, u["email"]).get_by_test_id("user-edit").click()
    users_page.get_by_test_id("user-active").uncheck()
    users_page.get_by_test_id("user-save").click()
    expect(row(users_page, u["email"])).to_contain_text("Inactivo")
    assert anon.post("/api/auth/login", data={"email": u["email"], "password": u["password"]}).status == 403


def test_delete_user_ui(users_page: Page, make_user):
    u = make_user()
    users_page.reload()
    row(users_page, u["email"]).get_by_test_id("user-delete").click()
    expect(users_page.get_by_test_id("confirm-dialog")).to_contain_text(u["email"])
    users_page.get_by_test_id("confirm-delete").click()
    expect(users_page.get_by_test_id("toast")).to_have_text("Usuario eliminado")
    expect(row(users_page, u["email"])).to_have_count(0)


def test_search_users_ui(users_page: Page, make_user):
    tag = unique("buscado")
    u = make_user(name=f"Persona {tag}")
    users_page.get_by_test_id("user-search").fill(tag)
    expect(users_page.get_by_test_id("user-row")).to_have_count(1)
    expect(users_page.get_by_test_id("user-row")).to_contain_text(u["email"])


def test_new_user_can_login_ui(make_user, page: Page, ui_login):
    u = make_user(name="Usuario Nuevo Login")
    ui_login(u["email"], u["password"])
    expect(page.get_by_test_id("whoami")).to_contain_text("Usuario Nuevo Login")
    expect(page).to_have_url(f"{BASE_URL}/productos")
