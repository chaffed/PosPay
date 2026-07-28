# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from dataclasses import dataclass

from sqlalchemy.orm import Session

from pospay.domain.tenant import Tenant
from pospay.domain.tenant_membership import TenantMembership
from pospay.domain.user import User
from pospay.repositories.tenant_membership_repo import TenantMembershipRepository
from pospay.services import security_group_service, user_service


@dataclass(frozen=True, slots=True)
class ProvisionedIdentity:
    tenant: Tenant
    admin_user: User
    membership: TenantMembership


def create_tenant_with_admin(
    session: Session,
    *,
    tenant_name: str,
    tenant_slug: str,
    admin_email: str,
    admin_password: str,
) -> ProvisionedIdentity:
    """First-run bootstrap: creates a tenant, seeds its default security groups, and
    creates an initial admin user with a membership in the seeded "Admin" group. Used by
    scripts/launcher.py when the database is empty — kept here (not inline in the
    launcher) so it stays testable and reusable if a future admin API wants the same
    'create a new tenant' operation."""
    tenant = Tenant(name=tenant_name, slug=tenant_slug)
    session.add(tenant)
    session.flush()

    groups = security_group_service.seed_default_security_groups(session, tenant.id)

    admin_user = user_service.create_user_with_membership(
        session, tenant.id, email=admin_email, password=admin_password, security_group_id=groups["Admin"].id
    )
    membership = TenantMembershipRepository(session, tenant.id).list(user_id=admin_user.id)[0]

    return ProvisionedIdentity(tenant=tenant, admin_user=admin_user, membership=membership)
