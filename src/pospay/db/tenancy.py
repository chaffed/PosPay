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
    every template gets branding for free via `ctx`, no per-route plumbing needed."""

    tenant_id: uuid.UUID
    user_id: uuid.UUID
    security_group_id: uuid.UUID
    permissions: frozenset[str]
    tenant_slug: str
    tenant_name: str
    accent_color: str | None
    has_logo: bool
    has_favicon: bool
