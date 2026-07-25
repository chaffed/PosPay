import pytest

from pospay.services.tenant_service import (
    InvalidBrandingInput,
    get_tenant_branding_by_id,
    get_tenant_branding_by_slug,
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

    with pytest.raises(InvalidBrandingInput):
        update_tenant_branding(db_session, tenant.id, name=tenant.name, accent_color="not-a-color")


def test_update_tenant_branding_rejects_disallowed_image_type(db_session, tenant_factory):
    tenant, _account, _users = tenant_factory.make(slug="tenant-branding-bad-image")

    with pytest.raises(InvalidBrandingInput):
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
