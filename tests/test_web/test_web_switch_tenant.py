# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from pospay.services import security_group_service, user_service
from tests.conftest import TenantFactory


def _login(client, tenant_slug, email, password=TenantFactory.PASSWORD):
    client.get("/ui/login")
    csrf = client.cookies.get("csrf_token")
    client.post(
        "/ui/login", data={"tenant_slug": tenant_slug, "email": email, "password": password, "csrf_token": csrf, "next": "/ui/"}
    )
    return csrf


def test_switch_tenant_page_lists_other_memberships(client, db_session, tenant_factory):
    tenant_a, _account_a, users_a = tenant_factory.make(name="Switch Corp A", slug="switch-list-a")
    tenant_b, _account_b, _users_b = tenant_factory.make(name="Switch Corp B", slug="switch-list-b")
    group_b = security_group_service.get_security_group_by_name(db_session, tenant_b.id, "Viewer")
    user_service.confirm_cross_tenant_membership(db_session, tenant_b.id, email=users_a["admin"].email, security_group_id=group_b.id)
    db_session.commit()

    _login(client, tenant_a.slug, users_a["admin"].email)
    resp = client.get("/ui/switch-tenant")
    assert resp.status_code == 200
    assert f'>{tenant_b.name} (bank-wide)</button>' in resp.text
    # the current tenant's own name legitimately appears elsewhere on the page (nav
    # brand, title) now that branding shows it — just not as a switch-target button
    assert f'>{tenant_a.name} (bank-wide)</button>' not in resp.text


def test_switch_tenant_without_membership_shows_empty_state(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="switch-none")
    _login(client, tenant.slug, users["admin"].email)

    resp = client.get("/ui/switch-tenant")
    assert resp.status_code == 200
    assert "don&#39;t belong" in resp.text or "don't belong" in resp.text


def test_switch_tenant_mints_tokens_without_reauth(client, db_session, tenant_factory):
    tenant_a, _account_a, users_a = tenant_factory.make(slug="switch-mint-a")
    tenant_b, _account_b, _users_b = tenant_factory.make(slug="switch-mint-b")
    group_b = security_group_service.get_security_group_by_name(db_session, tenant_b.id, "Admin")
    membership_b = user_service.confirm_cross_tenant_membership(
        db_session, tenant_b.id, email=users_a["admin"].email, security_group_id=group_b.id
    )
    db_session.commit()

    csrf = _login(client, tenant_a.slug, users_a["admin"].email)
    resp = client.post(
        "/ui/switch-tenant", data={"csrf_token": csrf, "membership_id": str(membership_b.id)}, follow_redirects=False
    )
    assert resp.status_code == 303

    # now operating in tenant_b's context — e.g. tenant_b's security-groups page (Admin
    # group there) is reachable without ever entering a password/MFA for tenant_b
    resp = client.get("/ui/security-groups")
    assert resp.status_code == 200


def test_switch_tenant_rejects_non_member_tenant(client, db_session, tenant_factory):
    import uuid

    tenant_a, _account_a, users_a = tenant_factory.make(slug="switch-reject-a")
    tenant_factory.make(slug="switch-reject-b")

    csrf = _login(client, tenant_a.slug, users_a["admin"].email)
    resp = client.post(
        "/ui/switch-tenant", data={"csrf_token": csrf, "membership_id": str(uuid.uuid4())}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/ui/switch-tenant?error")
