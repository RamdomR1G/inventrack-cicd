"""Frontend: pantalla de inicio de sesión, sesión y navegación."""
import re

import pytest
from playwright.sync_api import Page, expect

from conftest import ADMIN_EMAIL, BASE_URL

pytestmark = pytest.mark.e2e


@pytest.mark.smoke
def test_login_page_renders(page: Page):
    page.goto(f"{BASE_URL}/login")
    expect(page).to_have_title("InvenTrack")
    expect(page.get_by_role("heading", name="Iniciar sesión")).to_be_visible()
    expect(page.get_by_test_id("login-email")).to_be_visible()
    expect(page.get_by_test_id("login-password")).to_have_attribute("type", "password")


@pytest.mark.smoke
def test_login_success_shows_products(ui_login):
    page = ui_login()
    expect(page.get_by_role("heading", name="Productos")).to_be_visible()
    expect(page.get_by_test_id("whoami")).to_contain_text("Administrador")


def test_login_wrong_password_shows_error(page: Page):
    page.goto(f"{BASE_URL}/login")
    page.get_by_test_id("login-email").fill(ADMIN_EMAIL)
    page.get_by_test_id("login-password").fill("incorrecta")
    page.get_by_test_id("login-submit").click()
    expect(page.get_by_test_id("login-error")).to_have_text("Correo o contraseña incorrectos")
    expect(page).to_have_url(re.compile(r"/login$"))


def test_login_empty_fields(page: Page):
    page.goto(f"{BASE_URL}/login")
    page.get_by_test_id("login-submit").click()
    expect(page.get_by_test_id("login-error")).to_have_text("Ingresa tu correo y tu contraseña")


def test_login_invalid_email_format(page: Page):
    page.goto(f"{BASE_URL}/login")
    page.get_by_test_id("login-email").fill("no-es-correo")
    page.get_by_test_id("login-password").fill("algo")
    page.get_by_test_id("login-submit").click()
    expect(page.get_by_test_id("login-error")).to_have_text("Correo electrónico inválido")


def test_login_with_enter_key(page: Page):
    page.goto(f"{BASE_URL}/login")
    page.get_by_test_id("login-email").fill(ADMIN_EMAIL)
    page.get_by_test_id("login-password").fill(__import__("conftest").ADMIN_PASSWORD)
    page.get_by_test_id("login-password").press("Enter")
    expect(page).to_have_url(f"{BASE_URL}/productos")


@pytest.mark.parametrize("path", ["/productos", "/usuarios", "/"])
def test_private_routes_redirect_to_login(page: Page, path):
    page.goto(f"{BASE_URL}{path}")
    expect(page).to_have_url(f"{BASE_URL}/login")


def test_logout(admin_page: Page):
    admin_page.get_by_test_id("logout").click()
    expect(admin_page).to_have_url(f"{BASE_URL}/login")
    admin_page.goto(f"{BASE_URL}/productos")
    expect(admin_page).to_have_url(f"{BASE_URL}/login")


def test_session_survives_reload(admin_page: Page):
    admin_page.reload()
    expect(admin_page.get_by_test_id("products-table")).to_be_visible()


def test_logged_user_is_sent_away_from_login(admin_page: Page):
    admin_page.goto(f"{BASE_URL}/login")
    expect(admin_page).to_have_url(f"{BASE_URL}/productos")


def test_navigation_between_modules(admin_page: Page):
    admin_page.get_by_test_id("nav-usuarios").click()
    expect(admin_page).to_have_url(f"{BASE_URL}/usuarios")
    expect(admin_page.get_by_role("heading", name="Usuarios")).to_be_visible()
    expect(admin_page.get_by_test_id("nav-usuarios")).to_have_class(re.compile("active"))
    admin_page.get_by_test_id("nav-productos").click()
    expect(admin_page.get_by_role("heading", name="Productos")).to_be_visible()


def test_unknown_page_shows_404(admin_page: Page):
    admin_page.goto(f"{BASE_URL}/no-existe")
    expect(admin_page.get_by_test_id("not-found")).to_contain_text("404")


def test_regular_user_has_no_users_menu(page: Page, make_user, ui_login):
    u = make_user()
    ui_login(u["email"], u["password"])
    expect(page.get_by_test_id("whoami")).to_contain_text("Usuario")
    expect(page.get_by_test_id("nav-usuarios")).to_have_count(0)
    page.goto(f"{BASE_URL}/usuarios")
    expect(page).to_have_url(f"{BASE_URL}/productos")
