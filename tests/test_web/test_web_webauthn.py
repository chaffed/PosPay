import webauthn

from pospay.config import get_settings
from tests.conftest import TenantFactory
from tests.test_auth.webauthn_helpers import FakeAuthenticator


def _web_login(client, tenant_slug: str, email: str, password: str = TenantFactory.PASSWORD):
    client.get("/ui/login")
    csrf = client.cookies.get("csrf_token")
    return client.post(
        "/ui/login",
        data={"tenant_slug": tenant_slug, "email": email, "password": password, "csrf_token": csrf, "next": "/ui/"},
        follow_redirects=False,
    )


def _register_via_web(client, fake: FakeAuthenticator, nickname: str = "Test Key") -> dict:
    csrf = client.cookies.get("csrf_token")
    options_resp = client.post("/ui/security/webauthn/register/options", headers={"X-CSRF-Token": csrf})
    assert options_resp.status_code == 200, options_resp.text
    options = webauthn.helpers.parse_registration_options_json(options_resp.text)
    credential = fake.create_registration_credential(options.challenge)

    verify_resp = client.post(
        "/ui/security/webauthn/register/verify",
        headers={"X-CSRF-Token": csrf},
        json={"credential": credential, "nickname": nickname},
    )
    assert verify_resp.status_code == 200, verify_resp.text
    return verify_resp.json()


def test_security_page_requires_auth(client):
    resp = client.get("/ui/security", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/ui/login")


def test_register_credential_via_web_endpoints(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-webauthn-register")
    _web_login(client, tenant.slug, users["admin"].email)
    fake = FakeAuthenticator(get_settings().webauthn_rp_id, get_settings().webauthn_origin)

    registered = _register_via_web(client, fake, nickname="Office Key")
    assert registered["nickname"] == "Office Key"

    page = client.get("/ui/security")
    assert "Office Key" in page.text


def test_login_with_registered_key_redirects_to_webauthn_page(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-webauthn-login-redirect")
    _web_login(client, tenant.slug, users["admin"].email)
    fake = FakeAuthenticator(get_settings().webauthn_rp_id, get_settings().webauthn_origin)
    _register_via_web(client, fake)

    # Log out, then log back in with the same password — must now require the key.
    logout_csrf = client.cookies.get("csrf_token")
    client.post("/ui/logout", data={"csrf_token": logout_csrf})

    resp = _web_login(client, tenant.slug, users["admin"].email)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/ui/login/webauthn")
    assert "mfa_token" in resp.cookies
    assert "access_token" not in resp.cookies


def test_full_web_login_mfa_flow(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-webauthn-full-flow")
    _web_login(client, tenant.slug, users["admin"].email)
    fake = FakeAuthenticator(get_settings().webauthn_rp_id, get_settings().webauthn_origin)
    _register_via_web(client, fake)

    logout_csrf = client.cookies.get("csrf_token")
    client.post("/ui/logout", data={"csrf_token": logout_csrf})

    login_resp = _web_login(client, tenant.slug, users["admin"].email)
    assert login_resp.status_code == 303

    webauthn_page = client.get("/ui/login/webauthn")
    assert webauthn_page.status_code == 200

    csrf = client.cookies.get("csrf_token")
    options_resp = client.post("/ui/login/webauthn/options", headers={"X-CSRF-Token": csrf})
    assert options_resp.status_code == 200, options_resp.text
    auth_options = webauthn.helpers.parse_authentication_options_json(options_resp.text)
    assertion = fake.create_authentication_credential(auth_options.challenge)

    verify_resp = client.post(
        "/ui/login/webauthn/verify",
        headers={"X-CSRF-Token": csrf},
        params={"next": "/ui/"},
        json={"credential": assertion},
    )
    assert verify_resp.status_code == 200, verify_resp.text
    assert verify_resp.json()["redirect"] == "/ui/"
    assert "access_token" in verify_resp.cookies

    dashboard = client.get("/ui/")
    assert dashboard.status_code == 200


def test_webauthn_options_rejects_missing_csrf_header(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-webauthn-csrf")
    _web_login(client, tenant.slug, users["admin"].email)

    resp = client.post("/ui/security/webauthn/register/options")  # no X-CSRF-Token header
    assert resp.status_code == 403


def test_delete_credential_via_web_form(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-webauthn-delete")
    _web_login(client, tenant.slug, users["admin"].email)
    fake = FakeAuthenticator(get_settings().webauthn_rp_id, get_settings().webauthn_origin)
    registered = _register_via_web(client, fake)

    csrf = client.cookies.get("csrf_token")
    resp = client.post(
        f"/ui/security/webauthn/{registered['id']}/delete",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    page = client.get("/ui/security")
    assert "No security keys registered" in page.text
