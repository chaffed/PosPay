# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from datetime import date
from decimal import Decimal

from pospay.domain.exception_item import ExceptionStatus
from pospay.networks.check.ingestion import PaidItemSubmission, ingest_paid_item
from pospay.services import issued_item_service, stop_payment_service
from tests.conftest import TenantFactory


def _login(client, tenant_slug, email, password=TenantFactory.PASSWORD):
    client.get("/ui/login")
    csrf = client.cookies.get("csrf_token")
    client.post(
        "/ui/login", data={"tenant_slug": tenant_slug, "email": email, "password": password, "csrf_token": csrf, "next": "/ui/"}
    )


def test_dashboard_shows_stat_cards_with_correct_counts(client, db_session, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="dashboard-stats")

    issued_item_service.create_issued_item(
        db_session, tenant.id,
        issued_item_service.IssuedItemInput(
            account_id=account.id, check_number="5001", amount=Decimal("100.00"), payee_name="Vendor",
            issue_date=date(2026, 1, 1),
        ),
        submitted_by_user_id=users["admin"].id,
    )
    stop_payment_service.create_stop_payment(
        db_session, tenant.id,
        stop_payment_service.StopPaymentInput(
            account_id=account.id, check_number="9001", amount=None, effective_date=date(2026, 1, 1),
            expiration_date=None, reason=None,
        ),
        created_by_user_id=users["admin"].id,
    )
    # A mismatched amount against the issued item above creates an open exception.
    ingest_paid_item(
        db_session, tenant.id,
        PaidItemSubmission(account_id=account.id, check_number="5001", presented_amount=Decimal("999.00"), presented_date=date(2026, 1, 2)),
    )
    db_session.commit()

    _login(client, tenant.slug, users["admin"].email)
    resp = client.get("/ui/")

    assert resp.status_code == 200
    assert "Open exceptions" in resp.text
    assert "Outstanding issued items" in resp.text
    assert "Active stop payments" in resp.text
    assert '/ui/exceptions?status=open' in resp.text
    assert '/ui/issued-items?status=outstanding' in resp.text
