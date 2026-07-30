# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from pospay.auth.security import decode_token
from pospay.config import get_settings
from tests.conftest import TenantFactory


def _login(client, tenant_slug, email, password=TenantFactory.PASSWORD):
    client.get("/ui/login")
    csrf = client.cookies.get("csrf_token")
    client.post(
        "/ui/login", data={"tenant_slug": tenant_slug, "email": email, "password": password, "csrf_token": csrf, "next": "/ui/"}
    )
    return csrf


def test_settings_page_requires_permission(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-settings-forbidden")
    _login(client, tenant.slug, users["viewer"].email)

    resp = client.get("/ui/settings", follow_redirects=False)
    assert resp.status_code == 403


def test_update_name_and_color(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-settings-name-color")
    csrf = _login(client, tenant.slug, users["admin"].email)

    resp = client.post(
        "/ui/settings",
        data={"csrf_token": csrf, "name": "Renamed Corp", "accent_color": "#112233"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    page = client.get("/ui/")
    assert "Renamed Corp" in page.text
    assert "#112233" in page.text


def test_upload_and_serve_logo_and_favicon(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-settings-upload")
    csrf = _login(client, tenant.slug, users["admin"].email)

    resp = client.post(
        "/ui/settings",
        data={"csrf_token": csrf, "name": tenant.name, "accent_color": ""},
        files={
            "logo": ("logo.png", b"fake-png-bytes", "image/png"),
            "favicon": ("favicon.ico", b"fake-ico-bytes", "image/x-icon"),
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303

    logo_resp = client.get(f"/ui/branding/{tenant.slug}/logo")
    assert logo_resp.status_code == 200
    assert logo_resp.content == b"fake-png-bytes"
    assert logo_resp.headers["content-type"] == "image/png"

    favicon_resp = client.get(f"/ui/branding/{tenant.slug}/favicon")
    assert favicon_resp.status_code == 200
    assert favicon_resp.content == b"fake-ico-bytes"

    nav_page = client.get("/ui/")
    assert f'/ui/branding/{tenant.slug}/logo' in nav_page.text
    assert f'/ui/branding/{tenant.slug}/favicon' in nav_page.text


def test_branding_assets_404_when_unset(client, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="web-settings-no-assets")
    resp = client.get(f"/ui/branding/{tenant.slug}/logo")
    assert resp.status_code == 404


def test_branding_assets_404_for_unknown_slug(client):
    resp = client.get("/ui/branding/does-not-exist/logo")
    assert resp.status_code == 404


def test_rejects_malformed_color_without_500(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-settings-bad-color")
    csrf = _login(client, tenant.slug, users["admin"].email)

    resp = client.post("/ui/settings", data={"csrf_token": csrf, "name": tenant.name, "accent_color": "nope"})
    assert resp.status_code == 422
    assert "not a valid hex color" in resp.text


def test_rejects_disallowed_image_type_without_500(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-settings-bad-image")
    csrf = _login(client, tenant.slug, users["admin"].email)

    resp = client.post(
        "/ui/settings",
        data={"csrf_token": csrf, "name": tenant.name, "accent_color": ""},
        files={"logo": ("evil.pdf", b"not-an-image", "application/pdf")},
    )
    assert resp.status_code == 422
    assert "Unsupported image type" in resp.text


def test_session_timeout_override_reflected_in_issued_token(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-settings-session-timeout")
    csrf = _login(client, tenant.slug, users["admin"].email)

    resp = client.post(
        "/ui/settings/session-timeout",
        data={"csrf_token": csrf, "access_token_expire_minutes": "5", "refresh_token_expire_minutes": "120"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    # Log back in (session-timeout only affects tokens minted after saving) and confirm
    # the new access token's exp claim reflects the override, not the global default.
    client.post("/ui/logout", data={"csrf_token": csrf})
    csrf = _login(client, tenant.slug, users["admin"].email)
    claims = decode_token(client.cookies.get("access_token"))
    assert abs((claims["exp"] - claims["iat"]) - 5 * 60) < 2


def test_session_timeout_blank_resets_to_global_default(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-settings-session-timeout-reset")
    csrf = _login(client, tenant.slug, users["admin"].email)
    client.post(
        "/ui/settings/session-timeout",
        data={"csrf_token": csrf, "access_token_expire_minutes": "5", "refresh_token_expire_minutes": "120"},
    )

    resp = client.post(
        "/ui/settings/session-timeout",
        data={"csrf_token": csrf, "access_token_expire_minutes": "", "refresh_token_expire_minutes": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    client.post("/ui/logout", data={"csrf_token": csrf})
    csrf = _login(client, tenant.slug, users["admin"].email)
    claims = decode_token(client.cookies.get("access_token"))
    settings = get_settings()
    assert abs((claims["exp"] - claims["iat"]) - settings.jwt_access_token_expire_minutes * 60) < 2


def test_session_timeout_rejects_non_positive_value(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-settings-session-timeout-bad")
    csrf = _login(client, tenant.slug, users["admin"].email)

    resp = client.post(
        "/ui/settings/session-timeout",
        data={"csrf_token": csrf, "access_token_expire_minutes": "0", "refresh_token_expire_minutes": ""},
    )
    assert resp.status_code == 422


def test_data_export_timeout_persists_override(client, db_session, tenant_factory):
    from pospay.domain.tenant import Tenant

    tenant, _account, users = tenant_factory.make(slug="web-settings-export-timeout")
    csrf = _login(client, tenant.slug, users["admin"].email)

    resp = client.post(
        "/ui/settings/data-export-timeout",
        data={"csrf_token": csrf, "timeout_seconds": "900"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    db_session.expire_all()
    assert db_session.get(Tenant, tenant.id).data_export_timeout_seconds == 900


def test_data_export_timeout_blank_resets_to_global_default(client, db_session, tenant_factory):
    from pospay.domain.tenant import Tenant

    tenant, _account, users = tenant_factory.make(slug="web-settings-export-timeout-reset")
    csrf = _login(client, tenant.slug, users["admin"].email)
    client.post("/ui/settings/data-export-timeout", data={"csrf_token": csrf, "timeout_seconds": "900"})

    resp = client.post(
        "/ui/settings/data-export-timeout",
        data={"csrf_token": csrf, "timeout_seconds": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    db_session.expire_all()
    assert db_session.get(Tenant, tenant.id).data_export_timeout_seconds is None


def test_data_export_timeout_rejects_non_positive_value(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-settings-export-timeout-bad")
    csrf = _login(client, tenant.slug, users["admin"].email)

    resp = client.post("/ui/settings/data-export-timeout", data={"csrf_token": csrf, "timeout_seconds": "0"})
    assert resp.status_code == 422


def test_branded_login_page_shows_name_and_logo(client, db_session, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-settings-branded-login")
    csrf = _login(client, tenant.slug, users["admin"].email)
    client.post(
        "/ui/settings",
        data={"csrf_token": csrf, "name": "Branded Login Co", "accent_color": ""},
        files={"logo": ("logo.png", b"fake-png-bytes", "image/png")},
    )
    client.post("/ui/logout", data={"csrf_token": csrf})

    resp = client.get(f"/ui/login/{tenant.slug}")
    assert resp.status_code == 200
    assert "Branded Login Co" in resp.text
    assert f"/ui/branding/{tenant.slug}/logo" in resp.text
    assert f'value="{tenant.slug}"' in resp.text


def test_unbranded_login_falls_back_to_generic(client):
    resp = client.get("/ui/login/does-not-exist-at-all")
    assert resp.status_code == 200
    assert "PosPay" in resp.text


def test_plain_login_page_still_works(client):
    resp = client.get("/ui/login")
    assert resp.status_code == 200
