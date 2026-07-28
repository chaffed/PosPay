# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from pospay.auth.permissions import PERMISSION_CATALOG
from pospay.services import security_group_service


def test_seed_default_security_groups_matches_old_role_behavior(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="sg-seed-defaults")
    groups = {g.name: g for g in security_group_service.list_security_groups(db_session, tenant.id)}

    assert set(groups) == {"Admin", "Preparer", "Approver", "Viewer"}
    assert set(groups["Admin"].permissions) == set(PERMISSION_CATALOG)
    assert "issued_item:write" in groups["Preparer"].permissions
    assert "exception:decide" not in groups["Preparer"].permissions
    assert "exception:decide" in groups["Approver"].permissions
    assert "issued_item:write" not in groups["Approver"].permissions
    assert all(key.endswith(":read") for key in groups["Viewer"].permissions)
    assert "issued_item:write" not in groups["Viewer"].permissions


def test_create_and_update_security_group(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="sg-create-update")

    group = security_group_service.create_security_group(
        db_session, tenant.id, security_group_service.SecurityGroupInput(name="AP Clerk", permissions=["issued_item:read"])
    )
    db_session.commit()
    assert group.permissions == ["issued_item:read"]

    updated = security_group_service.update_security_group(
        db_session,
        tenant.id,
        group.id,
        security_group_service.SecurityGroupInput(name="AP Clerk", permissions=["issued_item:read", "issued_item:write"]),
    )
    db_session.commit()
    assert set(updated.permissions) == {"issued_item:read", "issued_item:write"}


def test_create_security_group_drops_unknown_permissions(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="sg-unknown-perm")

    group = security_group_service.create_security_group(
        db_session,
        tenant.id,
        security_group_service.SecurityGroupInput(name="Weird", permissions=["issued_item:read", "not_a_real_permission"]),
    )
    db_session.commit()
    assert group.permissions == ["issued_item:read"]


def test_get_security_group_by_name(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="sg-get-by-name")
    found = security_group_service.get_security_group_by_name(db_session, tenant.id, "Admin")
    assert found is not None
    assert security_group_service.get_security_group_by_name(db_session, tenant.id, "Nonexistent") is None


def test_security_groups_are_tenant_scoped(db_session, tenant_factory):
    tenant_a, _account_a, _users_a = tenant_factory.make(slug="sg-scope-a")
    tenant_b, _account_b, _users_b = tenant_factory.make(slug="sg-scope-b")

    group_a = security_group_service.get_security_group_by_name(db_session, tenant_a.id, "Admin")
    assert security_group_service.get_security_group(db_session, tenant_b.id, group_a.id) is None
