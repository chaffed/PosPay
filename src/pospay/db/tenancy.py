# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Identity of the authenticated caller, resolved once from the JWT by auth/deps.py
    and threaded explicitly through services/repositories. Never build this from a
    request body or path parameter — tenant_id must only ever come from the token.

    `permissions` is resolved fresh from the caller's SecurityGroup on every request (not
    baked into the JWT) — see auth/deps.py::decode_and_build_context — so permission
    changes and membership deactivation take effect on the very next request. The
    `tenant_*`/`has_*` branding fields are resolved the same way, from the same Tenant
    lookup that already happens there (see services/tenant_service.py::TenantBranding) —
    every template gets branding for free via `ctx`, no per-route plumbing needed.

    `customer_id` is None for a tenant-wide membership (bank-wide staff, the only kind
    that existed before customers did) and set for a customer-scoped one (bank staff
    assigned to just that client, or the client's own employee) — see
    domain/tenant_membership.py. When set, decode_and_build_context has already masked
    every tenant-admin-only permission out of `permissions` regardless of what the
    security group nominally contains; repositories/services still must be passed
    `customer_id` explicitly wherever they accept it (see CustomerScopedRepository) —
    this field alone doesn't filter anything by itself."""

    tenant_id: uuid.UUID
    user_id: uuid.UUID
    security_group_id: uuid.UUID
    permissions: frozenset[str]
    tenant_slug: str
    tenant_name: str
    accent_color: str | None
    has_logo: bool
    has_favicon: bool
    customer_id: uuid.UUID | None
    customer_name: str | None

    # Per-tenant session-length override (services/tenant_service.py::set_session_timeouts)
    # — None means "use config.Settings.jwt_access/refresh_token_expire_minutes", the same
    # value most tests that construct a TenantContext directly want, hence the default
    # (unlike every field above, which has none, deliberately, and must be passed
    # explicitly). Resolved the same way branding is, from the same Tenant lookup
    # decode_and_build_context already does — see auth/security.py::create_token's
    # access_token_expire_minutes/refresh_token_expire_minutes params.
    access_token_expire_minutes: int | None = None
    refresh_token_expire_minutes: int | None = None

    # Contact info for templates/base.html's footer (services/tenant_service.py::
    # TenantBranding carries the identical set pre-login) — defaulted to None for the
    # same reason as the two fields above: most tests that construct a TenantContext
    # directly don't care about these and shouldn't have to pass them.
    support_email: str | None = None
    support_phone: str | None = None
    website: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
