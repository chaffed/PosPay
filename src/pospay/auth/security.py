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
    role: str,
    token_type: TokenType,
    settings: Settings | None = None,
) -> str:
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
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + timedelta(minutes=expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, *, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
