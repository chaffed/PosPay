import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Identity of the authenticated caller, resolved once from the JWT by auth/deps.py
    and threaded explicitly through services/repositories. Never build this from a
    request body or path parameter — tenant_id must only ever come from the token."""

    tenant_id: uuid.UUID
    user_id: uuid.UUID
    role: str
