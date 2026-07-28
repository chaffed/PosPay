# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

def test_login_succeeds_with_correct_credentials(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="login-ok")

    resp = client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": tenant.slug, "email": users["admin"].email, "password": tenant_factory.PASSWORD},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


def test_login_records_last_login_at(client, db_session, tenant_factory):
    from pospay.repositories.user_repo import UserRepository

    tenant, _account, users = tenant_factory.make(slug="login-last-login")
    assert UserRepository(db_session).get(users["admin"].id).last_login_at is None

    resp = client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": tenant.slug, "email": users["admin"].email, "password": tenant_factory.PASSWORD},
    )
    assert resp.status_code == 200

    db_session.expire_all()
    assert UserRepository(db_session).get(users["admin"].id).last_login_at is not None


def test_login_rejects_wrong_password(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="login-bad-pw")

    resp = client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": tenant.slug, "email": users["admin"].email, "password": "wrong"},
    )

    assert resp.status_code == 401


def test_login_rejects_unknown_tenant(client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": "does-not-exist", "email": "a@b.com", "password": "x"},
    )

    assert resp.status_code == 401


def test_refresh_issues_new_token_pair(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="refresh-ok")

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": tenant.slug, "email": users["admin"].email, "password": tenant_factory.PASSWORD},
    )
    refresh_token = login_resp.json()["refresh_token"]

    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})

    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_access_token_cannot_be_used_as_refresh_token(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="refresh-bad-type")

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": tenant.slug, "email": users["admin"].email, "password": tenant_factory.PASSWORD},
    )
    access_token = login_resp.json()["access_token"]

    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})

    assert resp.status_code == 401
