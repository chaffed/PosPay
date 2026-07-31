# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import pytest

from pospay.services.tenant_service import (
    InvalidTenantSettingsInput,
    get_tenant_branding_by_id,
    get_tenant_branding_by_slug,
    set_data_export_timeout,
    set_session_timeouts,
    update_tenant_branding,
    update_tenant_contact_info,
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


def test_update_tenant_branding_rejects_low_contrast_color(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="tenant-branding-low-contrast")

    # White -- every button renders white text on the accent color, so this would be
    # unreadable regardless of page theme.
    with pytest.raises(InvalidTenantSettingsInput, match="too light"):
        update_tenant_branding(db_session, tenant.id, name=tenant.name, accent_color="#ffffff")


def test_update_tenant_branding_accepts_sufficiently_dark_color(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="tenant-branding-good-contrast")

    updated = update_tenant_branding(db_session, tenant.id, name=tenant.name, accent_color="#000000")
    db_session.commit()

    assert updated.accent_color == "#000000"


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


def test_set_data_export_timeout_persists_override(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="tenant-export-timeout-set")

    updated = set_data_export_timeout(db_session, tenant.id, timeout_seconds=900)
    db_session.commit()

    assert updated.data_export_timeout_seconds == 900


def test_set_data_export_timeout_none_resets_to_global_default(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="tenant-export-timeout-reset")
    set_data_export_timeout(db_session, tenant.id, timeout_seconds=900)
    db_session.commit()

    updated = set_data_export_timeout(db_session, tenant.id, timeout_seconds=None)
    db_session.commit()

    assert updated.data_export_timeout_seconds is None


def test_set_data_export_timeout_rejects_non_positive_value(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="tenant-export-timeout-bad")

    with pytest.raises(InvalidTenantSettingsInput):
        set_data_export_timeout(db_session, tenant.id, timeout_seconds=0)


def test_update_tenant_contact_info_persists_all_fields(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="tenant-contact-set")

    updated = update_tenant_contact_info(
        db_session, tenant.id,
        support_email="help@example.com", support_phone="(555) 000-1111", website="https://example.com",
        address_line1="1 Main St", address_line2="Suite 2", city="Springfield", state="IL", postal_code="62701",
    )
    db_session.commit()

    assert updated.support_email == "help@example.com"
    assert updated.support_phone == "(555) 000-1111"
    assert updated.website == "https://example.com"
    assert updated.address_line1 == "1 Main St"
    assert updated.address_line2 == "Suite 2"
    assert updated.city == "Springfield"
    assert updated.state == "IL"
    assert updated.postal_code == "62701"


def test_update_tenant_contact_info_blank_strings_clear_fields(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="tenant-contact-clear")
    update_tenant_contact_info(
        db_session, tenant.id, support_email="help@example.com", support_phone="555", website=None,
        address_line1=None, address_line2=None, city=None, state=None, postal_code=None,
    )
    db_session.commit()

    cleared = update_tenant_contact_info(
        db_session, tenant.id, support_email="", support_phone="", website="",
        address_line1="", address_line2="", city="", state="", postal_code="",
    )
    db_session.commit()

    assert cleared.support_email is None
    assert cleared.support_phone is None


def test_update_tenant_contact_info_unknown_tenant_returns_none(db_session):
    import uuid

    assert (
        update_tenant_contact_info(
            db_session, uuid.uuid4(), support_email="x@example.com", support_phone=None, website=None,
            address_line1=None, address_line2=None, city=None, state=None, postal_code=None,
        )
        is None
    )


def test_branding_includes_contact_info(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="tenant-contact-branding")
    update_tenant_contact_info(
        db_session, tenant.id, support_email="help@example.com", support_phone=None, website=None,
        address_line1=None, address_line2=None, city=None, state=None, postal_code=None,
    )
    db_session.commit()

    branding = get_tenant_branding_by_id(db_session, tenant.id)
    assert branding.support_email == "help@example.com"

    by_slug = get_tenant_branding_by_slug(db_session, tenant.slug)
    assert by_slug.support_email == "help@example.com"
