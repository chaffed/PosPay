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

    # A user can now hold several memberships in the same tenant (one per customer, or a
    # tenant-wide one plus per-customer overrides — domain/tenant_membership.py), so this
    # is no longer a single-row lookup. Login picks a default rather than asking the user
    # to disambiguate here: the tenant-wide membership if they have one (the only kind
    # that existed before customers did, so this keeps today's single-membership case
    # byte-for-byte unchanged), else the earliest-created customer membership. Reaching
    # any other one is what "Switch organization" is for post-login — a full login-time
    # disambiguation step across several customer scopes is deliberately out of scope.
    active_memberships = [
        m
        for m in session.execute(
            select(TenantMembership).where(TenantMembership.user_id == user.id, TenantMembership.tenant_id == tenant.id)
        )
        .scalars()
        .all()
        if m.is_active
    ]
    if not active_memberships:
        return None
    # created_at alone isn't a safe sort key: SQLite's CURRENT_TIMESTAMP only has
    # one-second resolution, so two memberships created in the same second (e.g. from a
    # single bulk CSV upload) would tie, and without a secondary key the "earliest" pick
    # would depend on incidental row-fetch order rather than being deterministic. id is an
    # arbitrary but stable tiebreaker — not truly "earliest" on a tie, but at least
    # reproducible for a given dataset.
    membership = next(
        (m for m in active_memberships if m.customer_id is None),
        sorted(active_memberships, key=lambda m: (m.created_at, m.id))[0],
    )

    mfa_required = user_has_webauthn_credentials(session, tenant.id, user.id)
    return AuthenticatedIdentity(user=user, tenant=tenant, membership=membership, mfa_required=mfa_required)
