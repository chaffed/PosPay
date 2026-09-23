# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""App-wide fallbacks for errors no individual route handles: a database uniqueness
conflict becomes a friendly 409, and anything else unexpected becomes a branded 500 page
(or a JSON 500 under /api) instead of a bare "Internal Server Error" with no way back."""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import TenantFactory


def _login(client, tenant_slug, email):
    client.get("/ui/login")
    return client.post(
        "/ui/login",
        data={"tenant_slug": tenant_slug, "email": email, "password": TenantFactory.PASSWORD,
              "csrf_token": client.cookies.get("csrf_token"), "next": "/ui/"},
    )


@pytest.fixture
def lenient_client(app):
    """Like the shared `client` fixture, but lets the app's own error handlers produce the
    response instead of TestClient re-raising the server-side exception into the test."""

    @app.get("/ui/__test_boom")
    def _ui_boom():
        raise RuntimeError("internal-detail-xyz")

    @app.get("/api/v1/__test_boom")
    def _api_boom():
        raise RuntimeError("boom")

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_duplicate_security_group_name_is_a_friendly_409(lenient_client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-err-dup-group")
    _login(lenient_client, tenant.slug, users["admin"].email)
    csrf = lenient_client.cookies.get("csrf_token")

    resp = lenient_client.post(
        "/ui/security-groups", data={"name": "Admin", "csrf_token": csrf}, follow_redirects=False
    )

    assert resp.status_code == 409
    assert "already exists" in resp.text
    assert "<html" in resp.text.lower()


def test_unexpected_ui_error_renders_branded_500_page(lenient_client):
    resp = lenient_client.get("/ui/__test_boom")

    assert resp.status_code == 500
    assert "<html" in resp.text.lower()
    assert "Something went wrong" in resp.text
    assert "internal-detail-xyz" not in resp.text  # never leak exception details to the browser


def test_unexpected_api_error_returns_json_500(lenient_client):
    resp = lenient_client.get("/api/v1/__test_boom")

    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error"}
