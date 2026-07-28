import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pospay.auth.security import hash_password
from pospay.bulk_import.fields import RowFieldError, optional_str, require_str
from pospay.bulk_import.results import UserBulkRowResult
from pospay.domain.tenant import Tenant
from pospay.domain.tenant_membership import TenantMembership
from pospay.domain.user import User
from pospay.repositories.tenant_membership_repo import TenantMembershipRepository
from pospay.repositories.user_repo import UserRepository
from pospay.services import customer_service, security_group_service


@dataclass(frozen=True, slots=True)
class TenantUserRow:
    membership: TenantMembership
    user: User
    security_group_name: str
    customer_name: str | None = None


@dataclass(frozen=True, slots=True)
class MembershipRow:
    membership: TenantMembership
    tenant: Tenant
    customer_name: str | None = None


@dataclass(frozen=True, slots=True)
class AddUserResult:
    outcome: Literal["created", "already_member", "needs_confirmation", "failed"]
    error: str | None = None
    # Set only when outcome == "created" -- lets a bulk caller
    # (services/bulk_upload_reversal_service.py) track the specific membership row this
    # call produced, for backing it out later.
    membership_id: uuid.UUID | None = None


def record_login(session: Session, user_id: uuid.UUID) -> None:
    """Called once per completed login (not token refresh, not "switch organization") —
    see the four call sites in web/routers/auth.py, api/v1/auth.py, and
    api/v1/webauthn.py. Powers the last_login_at column an access-review/recertification
    process (GET /api/v1/users) relies on to flag stale accounts."""
    user = UserRepository(session).get(user_id)
    if user is None:
        return
    user.last_login_at = datetime.now(timezone.utc)
    session.flush()


def list_tenant_users(session: Session, tenant_id: uuid.UUID) -> list[TenantUserRow]:
    memberships = TenantMembershipRepository(session, tenant_id).list()
    user_repo = UserRepository(session)
    rows: list[TenantUserRow] = []
    for membership in memberships:
        user = user_repo.get(membership.user_id)
        group = security_group_service.get_security_group(session, tenant_id, membership.security_group_id)
        if user is None or group is None:
            continue
        customer_name = None
        if membership.customer_id is not None:
            customer = customer_service.get_customer(session, tenant_id, membership.customer_id)
            customer_name = customer.name if customer else None
        rows.append(
            TenantUserRow(membership=membership, user=user, security_group_name=group.name, customer_name=customer_name)
        )
    return rows


def list_memberships_for_user(session: Session, user_id: uuid.UUID) -> list[MembershipRow]:
    """The one deliberately cross-tenant query in the app: which tenants (and, within
    each, which customer scope) does this identity belong to. Powers "switch
    organization" (web/routers/tenant_switch.py) — never goes through
    TenantScopedRepository, which always filters to a single tenant; documented the same
    way exception_item/decision document their own RLS exclusion."""
    memberships = (
        session.execute(select(TenantMembership).where(TenantMembership.user_id == user_id, TenantMembership.is_active))
        .scalars()
        .all()
    )
    rows: list[MembershipRow] = []
    for membership in memberships:
        tenant = session.get(Tenant, membership.tenant_id)
        if tenant is None or not tenant.is_active:
            continue
        customer_name = None
        if membership.customer_id is not None:
            customer = customer_service.get_customer(session, membership.tenant_id, membership.customer_id)
            customer_name = customer.name if customer else None
        rows.append(MembershipRow(membership=membership, tenant=tenant, customer_name=customer_name))
    return rows


def create_user_with_membership(
    session: Session,
    tenant_id: uuid.UUID,
    *,
    email: str,
    password: str,
    security_group_id: uuid.UUID,
    customer_id: uuid.UUID | None = None,
) -> User:
    user = User(email=email, hashed_password=hash_password(password))
    UserRepository(session).add(user)
    session.flush()
    membership = TenantMembership(
        user_id=user.id, tenant_id=tenant_id, customer_id=customer_id, security_group_id=security_group_id
    )
    TenantMembershipRepository(session, tenant_id).add(membership)
    session.flush()
    return user


def confirm_cross_tenant_membership(
    session: Session, tenant_id: uuid.UUID, *, email: str, security_group_id: uuid.UUID, customer_id: uuid.UUID | None = None
) -> TenantMembership | None:
    """Re-resolves the identity BY EMAIL again here, server-side, rather than trusting a
    client-supplied user id — this confirmation step exists precisely so an admin
    explicitly agrees to grant an *existing* identity access to this tenant, and that
    grant must never be inferable from anything a client request could tamper with.
    Returns None only if the identity no longer exists (a race, not the normal path);
    idempotent if a membership in this exact (tenant, customer) scope already exists."""
    user = UserRepository(session).get_by_email(email)
    if user is None:
        return None
    existing = [
        m for m in TenantMembershipRepository(session, tenant_id).list(user_id=user.id) if m.customer_id == customer_id
    ]
    if existing:
        return existing[0]
    membership = TenantMembership(
        user_id=user.id, tenant_id=tenant_id, customer_id=customer_id, security_group_id=security_group_id
    )
    TenantMembershipRepository(session, tenant_id).add(membership)
    session.flush()
    return membership


def add_user(
    session: Session,
    tenant_id: uuid.UUID,
    *,
    email: str,
    password: str,
    security_group_id: uuid.UUID,
    customer_id: uuid.UUID | None = None,
) -> AddUserResult:
    """Single-user add flow (web/routers/users.py). A brand-new email is created
    immediately with the given password. An email that already belongs to an identity
    with a membership *in this same tenant* (any customer scope) is granted the new
    scoped membership directly — no confirmation needed, since the admin doing this
    already administers this tenant and the identity is already known within it. An
    email that only exists in a *different* tenant is never attached silently — the
    caller must re-post to confirm_cross_tenant_membership to actually grant it, after
    showing the admin an explicit confirmation step."""
    existing = UserRepository(session).get_by_email(email)
    if existing is None:
        if not password:
            return AddUserResult(outcome="failed", error="A password is required for a new user.")
        new_user = create_user_with_membership(
            session, tenant_id, email=email, password=password, security_group_id=security_group_id, customer_id=customer_id
        )
        new_membership = TenantMembershipRepository(session, tenant_id).list(user_id=new_user.id, customer_id=customer_id)[0]
        return AddUserResult(outcome="created", membership_id=new_membership.id)

    memberships_in_tenant = TenantMembershipRepository(session, tenant_id).list(user_id=existing.id)
    if any(m.customer_id == customer_id for m in memberships_in_tenant):
        return AddUserResult(outcome="already_member")

    if memberships_in_tenant:
        membership = TenantMembership(
            user_id=existing.id, tenant_id=tenant_id, customer_id=customer_id, security_group_id=security_group_id
        )
        TenantMembershipRepository(session, tenant_id).add(membership)
        session.flush()
        return AddUserResult(outcome="created", membership_id=membership.id)

    return AddUserResult(outcome="needs_confirmation")


def deactivate_membership(session: Session, tenant_id: uuid.UUID, membership_id: uuid.UUID) -> TenantMembership | None:
    membership = TenantMembershipRepository(session, tenant_id).get(membership_id)
    if membership is None:
        return None
    membership.is_active = False
    session.flush()
    return membership


def reactivate_membership(session: Session, tenant_id: uuid.UUID, membership_id: uuid.UUID) -> TenantMembership | None:
    membership = TenantMembershipRepository(session, tenant_id).get(membership_id)
    if membership is None:
        return None
    membership.is_active = True
    session.flush()
    return membership


def create_users_from_rows(
    session: Session, tenant_id: uuid.UUID, rows: list[dict[str, Any]], *, scoped_customer_id: uuid.UUID | None = None
) -> list[UserBulkRowResult]:
    """Entry point for the CSV bulk-load (web/routers/users.py). Expected
    (case/whitespace-insensitive) columns: email, security_group (a name resolved within
    this tenant), password (required only for rows whose email is brand new), and an
    optional customer_number. When the upload itself is customer-scoped
    (scoped_customer_id set — the uploader is scoped to one customer), every row is
    granted access to that same customer regardless of whether customer_number is
    present, and a present value must name that same customer; otherwise each row's own
    customer_number (if any) determines its scope, same pattern as bulk account uploads.
    Rows whose email already belongs to an identity in another tenant come back as
    'needs_confirmation' rather than being created — see add_user."""
    results: list[UserBulkRowResult] = []
    for index, row in enumerate(rows):
        row_label = f"row {index + 2}"  # +2: 1-based, plus the header row itself
        try:
            email = require_str(row, "email")
            group_name = require_str(row, "security_group")
            password = optional_str(row, "password") or ""
            group = security_group_service.get_security_group_by_name(session, tenant_id, group_name)
            if group is None:
                raise RowFieldError(f"No security group found named {group_name!r}")

            customer_number = optional_str(row, "customer_number")
            if scoped_customer_id is not None:
                if customer_number:
                    customer = customer_service.get_customer_by_number(session, tenant_id, customer_number)
                    if customer is None or customer.id != scoped_customer_id:
                        raise RowFieldError(f"customer_number {customer_number!r} does not match your assigned customer")
                row_customer_id = scoped_customer_id
            elif customer_number:
                customer = customer_service.get_customer_by_number(session, tenant_id, customer_number)
                if customer is None:
                    raise RowFieldError(f"No customer found with customer number {customer_number!r}")
                row_customer_id = customer.id
            else:
                row_customer_id = None

            result = add_user(
                session, tenant_id, email=email, password=password, security_group_id=group.id, customer_id=row_customer_id
            )
        except RowFieldError as exc:
            session.rollback()
            results.append(UserBulkRowResult(row_label=row_label, outcome="failed", error=str(exc)))
            continue
        except Exception as exc:  # noqa: BLE001 — isolate row failures in a bulk file
            session.rollback()
            results.append(UserBulkRowResult(row_label=row_label, outcome="failed", error=str(exc)))
            continue

        if result.outcome == "created":
            session.commit()
        else:
            session.rollback()
        results.append(
            UserBulkRowResult(
                row_label=row_label,
                outcome=result.outcome,
                email=email,
                security_group_id=group.id,
                error=result.error,
                membership_id=result.membership_id,
            )
        )
    return results


def confirm_users_bulk(
    session: Session, tenant_id: uuid.UUID, confirmations: list[tuple[str, uuid.UUID, uuid.UUID | None]]
) -> list[UserBulkRowResult]:
    """Follow-up step for the 'needs_confirmation' rows a bulk CSV load produced — the
    admin reviewed and re-submitted these (email, security_group_id, customer_id) triples
    explicitly."""
    results: list[UserBulkRowResult] = []
    for email, security_group_id, customer_id in confirmations:
        membership = confirm_cross_tenant_membership(
            session, tenant_id, email=email, security_group_id=security_group_id, customer_id=customer_id
        )
        if membership is None:
            session.rollback()
            results.append(UserBulkRowResult(row_label=email, outcome="failed", email=email, error="User no longer exists."))
        else:
            session.commit()
            results.append(UserBulkRowResult(row_label=email, outcome="created", email=email, security_group_id=security_group_id))
    return results
