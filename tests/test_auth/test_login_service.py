# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from pospay.auth.login_service import PasswordLoginOutcome, authenticate_password
from pospay.domain.webauthn_credential import WebauthnCredential
from pospay.repositories.tenant_membership_repo import TenantMembershipRepository
from pospay.repositories.webauthn_credential_repo import WebauthnCredentialRepository
from pospay.services import sso_service
from tests.conftest import TenantFactory
from tests.test_web.test_web_sso_login import _make_mapped_connection


def test_password_login_blocked_when_tenant_requires_sso(db_session, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="login-svc-sso-blocked")
    _make_mapped_connection(db_session, tenant)
    sso_service.set_tenant_password_login_enabled(db_session, tenant.id, enabled=False)
    db_session.commit()

    result = authenticate_password(db_session, tenant.slug, users["admin"].email, TenantFactory.PASSWORD)

    assert result.outcome == PasswordLoginOutcome.SSO_REQUIRED


def test_require_webauthn_membership_bypasses_sso_required(db_session, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="login-svc-sso-override")
    _make_mapped_connection(db_session, tenant)
    sso_service.set_tenant_password_login_enabled(db_session, tenant.id, enabled=False)
    membership = TenantMembershipRepository(db_session, tenant.id).list(user_id=users["admin"].id)[0]
    membership.require_webauthn = True
    db_session.commit()

    result = authenticate_password(db_session, tenant.slug, users["admin"].email, TenantFactory.PASSWORD)

    assert result.outcome == PasswordLoginOutcome.SUCCESS
    assert result.identity is not None
    assert result.identity.mfa_required is True
    assert result.identity.needs_webauthn_enrollment is True


def test_needs_webauthn_enrollment_false_once_key_registered(db_session, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="login-svc-sso-enrolled")
    _make_mapped_connection(db_session, tenant)
    sso_service.set_tenant_password_login_enabled(db_session, tenant.id, enabled=False)
    membership = TenantMembershipRepository(db_session, tenant.id).list(user_id=users["admin"].id)[0]
    membership.require_webauthn = True
    WebauthnCredentialRepository(db_session, tenant.id).add(
        WebauthnCredential(user_id=users["admin"].id, credential_id=b"fake-cred-id", public_key=b"fake-public-key")
    )
    db_session.commit()

    result = authenticate_password(db_session, tenant.slug, users["admin"].email, TenantFactory.PASSWORD)

    assert result.outcome == PasswordLoginOutcome.SUCCESS
    assert result.identity is not None
    assert result.identity.mfa_required is True
    assert result.identity.needs_webauthn_enrollment is False


def test_ordinary_membership_unaffected_by_require_webauthn_default(db_session, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="login-svc-ordinary")

    result = authenticate_password(db_session, tenant.slug, users["admin"].email, TenantFactory.PASSWORD)

    assert result.outcome == PasswordLoginOutcome.SUCCESS
    assert result.identity is not None
    assert result.identity.mfa_required is False
    assert result.identity.needs_webauthn_enrollment is False
