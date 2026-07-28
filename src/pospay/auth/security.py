# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

import bcrypt
import jwt

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
    settings: Settings | None = None,
) -> str:
    """The token only carries the security_group_id, not the permission set itself —
    auth/deps.py::decode_and_build_context resolves the actual permissions from the
    SecurityGroup row fresh on every request, so editing a group (or deactivating a
    membership) takes effect on the next request rather than waiting for this token to
    expire. `customer_id` is omitted (not just null) for a tenant-wide membership — the
    only kind that existed before customers did — so old tokens/callers are unaffected;
    a real value scopes the whole session to that one customer (domain/tenant_membership.py)."""
    settings = settings or get_settings()
    expire_minutes = {
        "access": settings.jwt_access_token_expire_minutes,
        "refresh": settings.jwt_refresh_token_expire_minutes,
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
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, *, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
