# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""Deliberately attempts to leak every tenant-owned resource type across tenants and
asserts each attempt is blocked. This is the test suite the architecture plan calls for
in Phase 6 — a bug in repositories/base.py's tenant filtering is exactly the class of bug
this exists to catch before it reaches a real multi-tenant deployment."""

from tests.conftest import login_headers


def _two_tenants(tenant_factory):
    tenant_a, account_a, users_a = tenant_factory.make(slug="xt-a")
    tenant_b, account_b, users_b = tenant_factory.make(slug="xt-b")
    return (tenant_a, account_a, users_a), (tenant_b, account_b, users_b)


def test_issued_items_not_visible_or_fetchable_across_tenants(client, tenant_factory):
    (tenant_a, account_a, users_a), (_tenant_b, _account_b, users_b) = _two_tenants(tenant_factory)
    headers_a = login_headers(client, tenant_a.slug, users_a["preparer"].email)
    headers_b = login_headers(client, "xt-b", users_b["preparer"].email)

    created = client.post(
        "/api/v1/issued-items",
        headers=headers_a,
        json={
            "account_id": str(account_a.id),
            "check_number": "1",
            "amount": "10.00",
            "payee_name": "X",
            "issue_date": "2026-01-01",
        },
    ).json()

    assert client.get(f"/api/v1/issued-items/{created['id']}", headers=headers_b).status_code == 404
    assert created["id"] not in [i["id"] for i in client.get("/api/v1/issued-items", headers=headers_b).json()]
    # Tenant B can't even void a resource it can't see.
    assert (
        client.patch(f"/api/v1/issued-items/{created['id']}/void", headers=headers_b, json={"reason": "x"}).status_code
        == 404
    )


def test_stop_payments_not_visible_or_cancelable_across_tenants(client, tenant_factory):
    (tenant_a, account_a, users_a), (_tenant_b, _account_b, users_b) = _two_tenants(tenant_factory)
    headers_a = login_headers(client, tenant_a.slug, users_a["preparer"].email)
    headers_b = login_headers(client, "xt-b", users_b["preparer"].email)

    created = client.post(
        "/api/v1/stop-payments",
        headers=headers_a,
        json={"account_id": str(account_a.id), "check_number": "1", "effective_date": "2026-01-01"},
    ).json()

    assert created["id"] not in [s["id"] for s in client.get("/api/v1/stop-payments", headers=headers_b).json()]
    assert client.patch(f"/api/v1/stop-payments/{created['id']}/cancel", headers=headers_b).status_code == 404


def test_paid_items_not_visible_across_tenants(client, tenant_factory):
    (tenant_a, account_a, users_a), (_tenant_b, _account_b, users_b) = _two_tenants(tenant_factory)
    headers_a = login_headers(client, tenant_a.slug, users_a["preparer"].email)
    headers_b = login_headers(client, "xt-b", users_b["preparer"].email)

    created = client.post(
        "/api/v1/paid-items",
        headers=headers_a,
        json={"account_id": str(account_a.id), "check_number": "1", "presented_amount": "10.00", "presented_date": "2026-01-01"},
    ).json()

    assert client.get(f"/api/v1/paid-items/{created['id']}", headers=headers_b).status_code == 404
    assert created["id"] not in [p["id"] for p in client.get("/api/v1/paid-items", headers=headers_b).json()]


def test_ach_authorizations_and_transactions_not_visible_across_tenants(client, tenant_factory):
    (tenant_a, account_a, users_a), (_tenant_b, _account_b, users_b) = _two_tenants(tenant_factory)
    headers_a = login_headers(client, tenant_a.slug, users_a["preparer"].email)
    headers_b = login_headers(client, "xt-b", users_b["preparer"].email)

    auth = client.post(
        "/api/v1/ach/authorizations",
        headers=headers_a,
        json={
            "account_id": str(account_a.id),
            "originator_id": "ORIG",
            "originator_name": "X",
            "effective_date": "2026-01-01",
        },
    ).json()
    assert auth["id"] not in [a["id"] for a in client.get("/api/v1/ach/authorizations", headers=headers_b).json()]
    assert client.patch(f"/api/v1/ach/authorizations/{auth['id']}/revoke", headers=headers_b).status_code == 404

    txn = client.post(
        "/api/v1/ach/transactions",
        headers=headers_a,
        json={
            "account_id": str(account_a.id),
            "originator_id": "ORIG",
            "originator_name": "X",
            "amount": "10.00",
            "transaction_type": "credit",
            "sec_code": "PPD",
            "trace_number": "T1",
            "effective_date": "2026-01-01",
        },
    ).json()
    assert client.get(f"/api/v1/ach/transactions/{txn['id']}", headers=headers_b).status_code == 404


def test_exceptions_and_decisions_not_visible_or_decidable_across_tenants(client, tenant_factory):
    (tenant_a, account_a, users_a), (_tenant_b, _account_b, users_b) = _two_tenants(tenant_factory)
    headers_a = login_headers(client, tenant_a.slug, users_a["preparer"].email)
    approver_a = login_headers(client, tenant_a.slug, users_a["approver"].email)
    headers_b = login_headers(client, "xt-b", users_b["preparer"].email)
    approver_b = login_headers(client, "xt-b", users_b["approver"].email)

    client.post(
        "/api/v1/paid-items",
        headers=headers_a,
        json={"account_id": str(account_a.id), "check_number": "1", "presented_amount": "10.00", "presented_date": "2026-01-01"},
    )
    exception_id = client.get("/api/v1/exceptions", headers=headers_a).json()[0]["id"]

    # Tenant B sees an empty queue and can't reach tenant A's exception directly.
    assert client.get("/api/v1/exceptions", headers=headers_b).json() == []
    assert client.get(f"/api/v1/exceptions/{exception_id}", headers=headers_b).status_code == 404

    # Nor can tenant B's approver decide an exception belonging to tenant A.
    assert (
        client.post(
            f"/api/v1/exceptions/{exception_id}/decide",
            headers=approver_b,
            json={"outcome": "pay", "reason_code": "x"},
        ).status_code
        == 404
    )

    # Tenant A's own approver can, and tenant B still can't read the resulting decision.
    decide = client.post(
        f"/api/v1/exceptions/{exception_id}/decide", headers=approver_a, json={"outcome": "pay", "reason_code": "x"}
    )
    assert decide.status_code == 200
    assert client.get(f"/api/v1/exceptions/{exception_id}/decision", headers=headers_b).status_code == 404


def test_jwt_tenant_id_cannot_be_overridden_by_request_body(client, tenant_factory):
    """tenant_id must only ever come from the JWT — confirms no endpoint accepts a
    tenant_id field from the request body/path that could let a caller spoof another
    tenant (issued-item creation doesn't take a tenant_id field at all; this asserts a
    resource created by tenant A is truly owned by A regardless of any such attempt)."""
    (tenant_a, account_a, users_a), (_tenant_b, _account_b, users_b) = _two_tenants(tenant_factory)
    headers_a = login_headers(client, tenant_a.slug, users_a["preparer"].email)
    headers_b = login_headers(client, "xt-b", users_b["preparer"].email)

    resp = client.post(
        "/api/v1/issued-items",
        headers=headers_a,
        json={
            "account_id": str(account_a.id),
            "check_number": "spoof-1",
            "amount": "10.00",
            "payee_name": "X",
            "issue_date": "2026-01-01",
            "tenant_id": "11111111-1111-1111-1111-111111111111",  # ignored: not a real field
        },
    )
    assert resp.status_code == 201
    created_id = resp.json()["id"]

    assert client.get(f"/api/v1/issued-items/{created_id}", headers=headers_a).status_code == 200
    assert client.get(f"/api/v1/issued-items/{created_id}", headers=headers_b).status_code == 404
