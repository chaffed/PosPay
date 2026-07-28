# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from pospay.domain.tenant import Tenant
from pospay.web.branding_storage import save_tenant_asset

_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/svg+xml",
    "image/x-icon",
    "image/vnd.microsoft.icon",
}


class InvalidBrandingInput(ValueError):
    """Raised for a malformed accent color or a disallowed image content-type — callers
    turn this into a form error, never a 500."""


@dataclass(frozen=True, slots=True)
class TenantBranding:
    """What a template needs to render a tenant's branding — never the image bytes
    themselves (those are served separately, see web/routers/branding.py)."""

    slug: str
    name: str
    accent_color: str | None
    has_logo: bool
    has_favicon: bool


def _branding_from_tenant(tenant: Tenant) -> TenantBranding:
    return TenantBranding(
        slug=tenant.slug,
        name=tenant.name,
        accent_color=tenant.accent_color,
        has_logo=bool(tenant.logo_path),
        has_favicon=bool(tenant.favicon_path),
    )


def get_tenant_branding_by_id(session: Session, tenant_id: uuid.UUID) -> TenantBranding | None:
    """Used by auth/deps.py::decode_and_build_context to populate TenantContext for an
    already-authenticated request (tenant_id comes from the JWT)."""
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        return None
    return _branding_from_tenant(tenant)


def get_tenant_branding_by_slug(session: Session, slug: str) -> TenantBranding | None:
    """Used by web/routers/auth.py's login routes to brand the login page BEFORE
    authentication — resolved by the slug in the URL/form, not a token. Returns None for
    an unknown or inactive slug so the caller can fall back to the generic, unbranded
    login form rather than leaking which slugs exist via an error."""
    tenant = session.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one_or_none()
    if tenant is None or not tenant.is_active:
        return None
    return _branding_from_tenant(tenant)


def _validate_accent_color(accent_color: str | None) -> str | None:
    if not accent_color:
        return None
    if not _HEX_COLOR_RE.match(accent_color):
        raise InvalidBrandingInput(f"{accent_color!r} is not a valid hex color — expected e.g. #2563eb")
    return accent_color


def _validate_image(content_type: str) -> None:
    if content_type not in _ALLOWED_IMAGE_CONTENT_TYPES:
        raise InvalidBrandingInput(f"Unsupported image type {content_type!r} — use PNG, JPEG, SVG, or ICO")


def update_tenant_branding(
    session: Session,
    tenant_id: uuid.UUID,
    *,
    name: str,
    accent_color: str | None,
    logo: tuple[str, bytes] | None = None,
    favicon: tuple[str, bytes] | None = None,
) -> Tenant | None:
    """logo/favicon are (content_type, bytes) tuples, passed only when the admin actually
    picked a new file — omitting either leaves the existing one untouched, so re-saving
    the form just to change the color doesn't clobber an already-uploaded logo. Raises
    InvalidBrandingInput on a malformed color or a disallowed image type; the route turns
    that into a form error rather than a 500."""
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        return None

    tenant.name = name
    tenant.accent_color = _validate_accent_color(accent_color)

    if logo is not None:
        content_type, data = logo
        _validate_image(content_type)
        tenant.logo_path = save_tenant_asset(tenant_id, "logo", content_type, data)
        tenant.logo_content_type = content_type

    if favicon is not None:
        content_type, data = favicon
        _validate_image(content_type)
        tenant.favicon_path = save_tenant_asset(tenant_id, "favicon", content_type, data)
        tenant.favicon_content_type = content_type

    session.flush()
    return tenant
