# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

import bcrypt
import jwt

from pospay.auth.keys import load_private_key, load_public_key
from pospay.config import Settings, get_settings

TokenType = Literal["access", "refresh", "mfa_pending"]

# bcrypt's underlying algorithm silently truncates/ignores input past 72 bytes; cap it
# explicitly so behavior is consistent rather than relying on the library's own limit.
_MAX_PASSWORD_BYTES = 72


def hash_password(plain_password: str) -> str:
    password_bytes = plain_password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("ascii")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    return bcrypt.checkpw(password_bytes, hashed_password.encode("ascii"))


def create_token(
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    security_group_id: uuid.UUID,
    token_type: TokenType,
    customer_id: uuid.UUID | None = None,
    access_token_expire_minutes: int | None = None,
    refresh_token_expire_minutes: int | None = None,
    settings: Settings | None = None,
) -> str:
    """The token only carries the security_group_id, not the permission set itself —
    auth/deps.py::decode_and_build_context resolves the actual permissions from the
    SecurityGroup row fresh on every request, so editing a group (or deactivating a
    membership) takes effect on the next request rather than waiting for this token to
    expire. `customer_id` is omitted (not just null) for a tenant-wide membership — the
    only kind that existed before customers did — so old tokens/callers are unaffected;
    a real value scopes the whole session to that one customer (domain/tenant_membership.py).

    `access_token_expire_minutes`/`refresh_token_expire_minutes` are the caller's
    resolved per-tenant override (Tenant.access_token_expire_minutes/
    refresh_token_expire_minutes, see services/tenant_service.py::set_session_timeouts)
    — None (the default) falls back to the global setting below. Only consulted for
    their matching token_type; mfa_pending's expiry is always the fixed global setting,
    since a bank lengthening session lifetime shouldn't also lengthen how long a WebAuthn
    ceremony has to complete.

    Signed with an ECDSA key pair (auth/keys.py), not a shared secret — see
    config.py::assert_production_safe for why this matters."""
    settings = settings or get_settings()
    expire_minutes = {
        "access": access_token_expire_minutes if access_token_expire_minutes is not None else settings.jwt_access_token_expire_minutes,
        "refresh": refresh_token_expire_minutes if refresh_token_expire_minutes is not None else settings.jwt_refresh_token_expire_minutes,
        "mfa_pending": settings.mfa_pending_token_expire_minutes,
    }[token_type]
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "security_group_id": str(security_group_id),
        "type": token_type,
        "iat": now,
        "exp": now + timedelta(minutes=expire_minutes),
    }
    if customer_id is not None:
        payload["customer_id"] = str(customer_id)
    private_key = load_private_key(settings.jwt_private_key_path)
    return jwt.encode(payload, private_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, *, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    public_key = load_public_key(settings.jwt_public_key_path)
    return jwt.decode(token, public_key, algorithms=[settings.jwt_algorithm])


_SSO_STATE_EXPIRE_MINUTES = 10


def create_sso_state_token(
    *, connection_id: uuid.UUID, tenant_id: uuid.UUID, nonce: str, next_path: str, settings: Settings | None = None
) -> str:
    """Carries the SSO login-in-progress state across the redirect to the IdP and back —
    this app has no server-side session store, so (like mfa_pending) it round-trips
    through a short-lived, signed cookie instead. A dedicated `type="sso_state"` claim
    means this can never be accepted anywhere a real access/refresh/mfa_pending token is
    (auth/deps.py never checks for this type). Carrying `tenant_id` here (established
    once, at /start, when the login page's own tenant is already known) means the
    callback never needs an unscoped cross-tenant DB lookup to find it again — it can go
    straight to a normal tenant-scoped query, RLS included."""
    settings = settings or get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "connection_id": str(connection_id),
        "tenant_id": str(tenant_id),
        "nonce": nonce,
        "next_path": next_path,
        "type": "sso_state",
        "iat": now,
        "exp": now + timedelta(minutes=_SSO_STATE_EXPIRE_MINUTES),
    }
    private_key = load_private_key(settings.jwt_private_key_path)
    return jwt.encode(payload, private_key, algorithm=settings.jwt_algorithm)


def decode_sso_state_token(token: str, *, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    public_key = load_public_key(settings.jwt_public_key_path)
    payload = jwt.decode(token, public_key, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != "sso_state":
        raise jwt.InvalidTokenError("Not an sso_state token")
    return payload
