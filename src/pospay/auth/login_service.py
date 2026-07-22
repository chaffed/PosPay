from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from pospay.auth.security import verify_password
from pospay.auth.webauthn_service import user_has_webauthn_credentials
from pospay.domain.tenant import Tenant
from pospay.domain.user import User


@dataclass(frozen=True, slots=True)
class AuthenticatedIdentity:
    user: User
    tenant: Tenant
    mfa_required: bool


def authenticate_password(session: Session, tenant_slug: str, email: str, password: str) -> AuthenticatedIdentity | None:
    """Shared by the JSON API (api/v1/auth.py) and the web login form
    (web/routers/auth.py) so credential-checking logic exists in exactly one place.
    Returns None on ANY failure (unknown tenant, unknown/inactive user, wrong password)
    — deliberately collapsed into a single outcome so neither caller is tempted into a
    response that reveals which part of the credential was wrong."""
    tenant = session.execute(select(Tenant).where(Tenant.slug == tenant_slug)).scalar_one_or_none()
    if tenant is None or not tenant.is_active:
        return None

    user = session.execute(
        select(User).where(User.tenant_id == tenant.id, User.email == email)
    ).scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(password, user.hashed_password):
        return None

    mfa_required = user_has_webauthn_credentials(session, tenant.id, user.id)
    return AuthenticatedIdentity(user=user, tenant=tenant, mfa_required=mfa_required)
