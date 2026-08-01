# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from pospay.config import get_settings
from pospay.domain.issued_item import IssuedItem
from pospay.domain.ml_model import MlModel
from pospay.domain.tenant import Tenant
from pospay.domain.user import User
from pospay.services import account_service, demo_tenant_service, issued_item_service


def _configure_demo_password(monkeypatch, password: str = "DemoSmokeTest123!") -> None:
    monkeypatch.setattr(get_settings(), "demo_tenant_password", password)


def test_ensure_demo_tenant_creates_and_seeds(db_session, monkeypatch):
    _configure_demo_password(monkeypatch)

    tenant = demo_tenant_service.ensure_demo_tenant(db_session)

    assert tenant.is_demo is True
    assert tenant.slug == demo_tenant_service.DEMO_TENANT_SLUG
    users = db_session.query(User).filter(User.email.in_(demo_tenant_service.DEMO_USER_EMAILS)).all()
    assert len(users) == 5
    assert db_session.query(IssuedItem).filter(IssuedItem.tenant_id == tenant.id).count() > 0

    # Safety property: never trains/activates the bare global model (customer_id=None) --
    # only a per-customer one, since MlModel has no tenant_id column at all and the
    # global model is genuinely shared across every tenant in the database.
    global_models = db_session.query(MlModel).filter(MlModel.network_code == "check", MlModel.customer_id.is_(None)).count()
    per_customer_models = db_session.query(MlModel).filter(MlModel.network_code == "check", MlModel.customer_id.is_not(None)).count()
    assert global_models == 0
    assert per_customer_models >= 1


def test_ensure_demo_tenant_is_idempotent(db_session, monkeypatch):
    _configure_demo_password(monkeypatch)

    first = demo_tenant_service.ensure_demo_tenant(db_session)
    second = demo_tenant_service.ensure_demo_tenant(db_session)

    assert first.id == second.id
    assert db_session.query(Tenant).filter(Tenant.is_demo.is_(True)).count() == 1


def test_ensure_demo_tenant_requires_password_configured(db_session, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_tenant_password", None)

    with pytest.raises(demo_tenant_service.DemoTenantNotConfigured):
        demo_tenant_service.ensure_demo_tenant(db_session)


def test_reset_demo_tenant_raises_when_none_exists(db_session, monkeypatch):
    _configure_demo_password(monkeypatch)

    with pytest.raises(demo_tenant_service.DemoTenantNotConfigured):
        demo_tenant_service.reset_demo_tenant(db_session)


def test_reset_demo_tenant_restores_pristine_state(db_session, monkeypatch):
    _configure_demo_password(monkeypatch)
    tenant = demo_tenant_service.ensure_demo_tenant(db_session)
    original_count = db_session.query(IssuedItem).filter(IssuedItem.tenant_id == tenant.id).count()

    account = account_service.list_accounts(db_session, tenant.id)[0]
    issued_item_service.create_issued_item(
        db_session, tenant.id,
        issued_item_service.IssuedItemInput(
            account_id=account.id, check_number="SALESDEMO1", amount=Decimal("999.00"), payee_name="Test Vendor",
            issue_date=date(2026, 1, 1),
        ),
        submitted_by_user_id=None,
    )
    db_session.commit()
    assert db_session.query(IssuedItem).filter(IssuedItem.tenant_id == tenant.id, IssuedItem.check_number == "SALESDEMO1").count() == 1

    reset_tenant = demo_tenant_service.reset_demo_tenant(db_session)

    assert reset_tenant.id == tenant.id
    db_session.expire_all()
    assert db_session.query(IssuedItem).filter(IssuedItem.tenant_id == tenant.id, IssuedItem.check_number == "SALESDEMO1").count() == 0
    assert db_session.query(IssuedItem).filter(IssuedItem.tenant_id == tenant.id).count() == original_count


def test_reset_demo_tenant_never_touches_a_different_tenant(db_session, monkeypatch, tenant_factory):
    _configure_demo_password(monkeypatch)
    demo_tenant_service.ensure_demo_tenant(db_session)

    real_tenant, real_account, real_users = tenant_factory.make(slug="real-bank-untouched")
    issued_item_service.create_issued_item(
        db_session, real_tenant.id,
        issued_item_service.IssuedItemInput(
            account_id=real_account.id, check_number="REALCHECK1", amount=Decimal("500.00"), payee_name="Real Vendor",
            issue_date=date(2026, 1, 1),
        ),
        submitted_by_user_id=real_users["admin"].id,
    )
    db_session.commit()
    before = db_session.query(IssuedItem).filter(IssuedItem.tenant_id == real_tenant.id).count()

    demo_tenant_service.reset_demo_tenant(db_session)

    db_session.expire_all()
    after = db_session.query(IssuedItem).filter(IssuedItem.tenant_id == real_tenant.id).count()
    assert before == after == 1
    # And the real tenant's own admin user must still exist untouched too.
    assert db_session.get(User, real_users["admin"].id) is not None


def test_maybe_reset_if_demo_idle_by_slug_noop_for_non_demo_tenant(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="not-the-demo-tenant")
    # Must not raise or do anything even though this tenant obviously isn't the demo one.
    demo_tenant_service.maybe_reset_if_demo_idle_by_slug(db_session, tenant.slug)


def test_maybe_reset_if_demo_idle_by_slug_noop_when_never_logged_in(db_session, monkeypatch):
    _configure_demo_password(monkeypatch)
    tenant = demo_tenant_service.ensure_demo_tenant(db_session)
    original_count = db_session.query(IssuedItem).filter(IssuedItem.tenant_id == tenant.id).count()

    demo_tenant_service.maybe_reset_if_demo_idle_by_slug(db_session, tenant.slug)

    db_session.expire_all()
    assert db_session.query(IssuedItem).filter(IssuedItem.tenant_id == tenant.id).count() == original_count


def test_maybe_reset_if_demo_idle_by_slug_no_reset_within_window(db_session, monkeypatch):
    _configure_demo_password(monkeypatch)
    tenant = demo_tenant_service.ensure_demo_tenant(db_session)
    admin = db_session.query(User).filter(User.email == demo_tenant_service.DEMO_ADMIN_EMAIL).one()
    admin.last_login_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    original_count = db_session.query(IssuedItem).filter(IssuedItem.tenant_id == tenant.id).count()

    demo_tenant_service.maybe_reset_if_demo_idle_by_slug(db_session, tenant.slug)

    db_session.expire_all()
    assert db_session.query(IssuedItem).filter(IssuedItem.tenant_id == tenant.id).count() == original_count


def test_maybe_reset_if_demo_idle_by_slug_resets_after_idle_window(db_session, monkeypatch):
    _configure_demo_password(monkeypatch)
    tenant = demo_tenant_service.ensure_demo_tenant(db_session)

    account = account_service.list_accounts(db_session, tenant.id)[0]
    issued_item_service.create_issued_item(
        db_session, tenant.id,
        issued_item_service.IssuedItemInput(
            account_id=account.id, check_number="SALESDEMO2", amount=Decimal("111.00"), payee_name="Test Vendor",
            issue_date=date(2026, 1, 1),
        ),
        submitted_by_user_id=None,
    )
    db_session.commit()

    admin = db_session.query(User).filter(User.email == demo_tenant_service.DEMO_ADMIN_EMAIL).one()
    admin.last_login_at = datetime.now(timezone.utc) - timedelta(minutes=get_settings().demo_tenant_session_minutes + 5)
    db_session.commit()

    demo_tenant_service.maybe_reset_if_demo_idle_by_slug(db_session, tenant.slug)

    db_session.expire_all()
    assert db_session.query(IssuedItem).filter(IssuedItem.tenant_id == tenant.id, IssuedItem.check_number == "SALESDEMO2").count() == 0
