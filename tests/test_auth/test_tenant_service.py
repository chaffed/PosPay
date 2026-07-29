# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import pytest

from pospay.services.tenant_service import (
    InvalidTenantSettingsInput,
    get_tenant_branding_by_id,
    get_tenant_branding_by_slug,
    set_session_timeouts,
    update_tenant_branding,
)


def test_update_tenant_branding_name_and_color(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="tenant-branding-basic")

    updated = update_tenant_branding(db_session, tenant.id, name="New Name", accent_color="#123abc")
    db_session.commit()

    assert updated.name == "New Name"
    assert updated.accent_color == "#123abc"
    assert updated.logo_path is None


def test_update_tenant_branding_uploads_logo_and_favicon(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="tenant-branding-upload")

    update_tenant_branding(
        db_session,
        tenant.id,
        name=tenant.name,
        accent_color=None,
        logo=("image/png", b"fake-png-bytes"),
        favicon=("image/x-icon", b"fake-ico-bytes"),
    )
    db_session.commit()

    branding = get_tenant_branding_by_id(db_session, tenant.id)
    assert branding.has_logo is True
    assert branding.has_favicon is True


def test_update_tenant_branding_without_new_files_keeps_existing(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="tenant-branding-keep")
    update_tenant_branding(db_session, tenant.id, name=tenant.name, accent_color=None, logo=("image/png", b"original"))
    db_session.commit()

    # re-save just the color, no new logo file supplied
    update_tenant_branding(db_session, tenant.id, name=tenant.name, accent_color="#2563eb", logo=None)
    db_session.commit()

    branding = get_tenant_branding_by_id(db_session, tenant.id)
    assert branding.has_logo is True
    assert branding.accent_color == "#2563eb"


def test_update_tenant_branding_rejects_malformed_color(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="tenant-branding-bad-color")

    with pytest.raises(InvalidTenantSettingsInput):
        update_tenant_branding(db_session, tenant.id, name=tenant.name, accent_color="not-a-color")


def test_update_tenant_branding_rejects_disallowed_image_type(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="tenant-branding-bad-image")

    with pytest.raises(InvalidTenantSettingsInput):
        update_tenant_branding(
            db_session, tenant.id, name=tenant.name, accent_color=None, logo=("application/pdf", b"not-an-image")
        )


def test_get_tenant_branding_by_slug_unknown_or_inactive_returns_none(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="tenant-branding-inactive")

    assert get_tenant_branding_by_slug(db_session, "does-not-exist") is None

    tenant.is_active = False
    db_session.commit()
    assert get_tenant_branding_by_slug(db_session, tenant.slug) is None


def test_get_tenant_branding_by_slug_matches_active_tenant(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="tenant-branding-slug-match")
    update_tenant_branding(db_session, tenant.id, name="Acme Renamed", accent_color="#654321")
    db_session.commit()

    branding = get_tenant_branding_by_slug(db_session, tenant.slug)
    assert branding.name == "Acme Renamed"
    assert branding.accent_color == "#654321"


def test_set_session_timeouts_persists_override(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="tenant-session-timeout-set")

    updated = set_session_timeouts(db_session, tenant.id, access_token_expire_minutes=15, refresh_token_expire_minutes=120)
    db_session.commit()

    assert updated.access_token_expire_minutes == 15
    assert updated.refresh_token_expire_minutes == 120
    branding = get_tenant_branding_by_id(db_session, tenant.id)
    assert branding.access_token_expire_minutes == 15
    assert branding.refresh_token_expire_minutes == 120


def test_set_session_timeouts_none_resets_to_global_default(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="tenant-session-timeout-reset")
    set_session_timeouts(db_session, tenant.id, access_token_expire_minutes=15, refresh_token_expire_minutes=120)
    db_session.commit()

    updated = set_session_timeouts(db_session, tenant.id, access_token_expire_minutes=None, refresh_token_expire_minutes=None)
    db_session.commit()

    assert updated.access_token_expire_minutes is None
    assert updated.refresh_token_expire_minutes is None


def test_set_session_timeouts_rejects_non_positive_value(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="tenant-session-timeout-bad")

    with pytest.raises(InvalidTenantSettingsInput):
        set_session_timeouts(db_session, tenant.id, access_token_expire_minutes=0, refresh_token_expire_minutes=None)
