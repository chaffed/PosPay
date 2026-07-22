from dataclasses import dataclass

from sqlalchemy.orm import Session

from pospay.auth.security import hash_password
from pospay.domain.tenant import Tenant
from pospay.domain.user import User, UserRole


@dataclass(frozen=True, slots=True)
class ProvisionedIdentity:
    tenant: Tenant
    admin_user: User


def create_tenant_with_admin(
    session: Session,
    *,
    tenant_name: str,
    tenant_slug: str,
    admin_email: str,
    admin_password: str,
) -> ProvisionedIdentity:
    """First-run bootstrap: creates a tenant plus its initial admin user. Used by
    scripts/launcher.py when the database is empty — kept here (not inline in the
    launcher) so it stays testable and reusable if a future admin API wants the same
    'create a new tenant' operation."""
    tenant = Tenant(name=tenant_name, slug=tenant_slug)
    session.add(tenant)
    session.flush()

    admin_user = User(
        tenant_id=tenant.id,
        email=admin_email,
        hashed_password=hash_password(admin_password),
        role=UserRole.ADMIN,
    )
    session.add(admin_user)
    session.flush()

    return ProvisionedIdentity(tenant=tenant, admin_user=admin_user)
