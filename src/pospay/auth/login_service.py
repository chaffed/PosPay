from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from pospay.auth.security import verify_password
from pospay.auth.webauthn_service import user_has_webauthn_credentials
from pospay.domain.tenant import Tenant
from pospay.domain.tenant_membership import TenantMembership
from pospay.domain.user import User


@dataclass(frozen=True, slots=True)
class AuthenticatedIdentity:
    user: User
    tenant: Tenant
    membership: TenantMembership
    mfa_required: bool


def authenticate_password(session: Session, tenant_slug: str, email: str, password: str) -> AuthenticatedIdentity | None:
    """Shared by the JSON API (api/v1/auth.py) and the web login form
    (web/routers/auth.py) so credential-checking logic exists in exactly one place.
    Returns None on ANY failure (unknown tenant, unknown/inactive user, wrong password,
    no active membership in this tenant) — deliberately collapsed into a single outcome
    so neither caller is tempted into a response that reveals which part was wrong.

    `email` resolves a User globally now (see domain/user.py) rather than within this one
    tenant — the same identity can hold a TenantMembership (and therefore log in) in more
    than one tenant, each with its own security group."""
    tenant = session.execute(select(Tenant).where(Tenant.slug == tenant_slug)).scalar_one_or_none()
    if tenant is None or not tenant.is_active:
        return None

    user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(password, user.hashed_password):
        return None

    membership = session.execute(
        select(TenantMembership).where(TenantMembership.user_id == user.id, TenantMembership.tenant_id == tenant.id)
    ).scalar_one_or_none()
    if membership is None or not membership.is_active:
        return None

    mfa_required = user_has_webauthn_credentials(session, tenant.id, user.id)
    return AuthenticatedIdentity(user=user, tenant=tenant, membership=membership, mfa_required=mfa_required)
