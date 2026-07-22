import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from pospay.auth.rbac import role_has_permission
from pospay.auth.security import decode_token
from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.domain.user import UserRole

_bearer_scheme = HTTPBearer(auto_error=True)


class WrongTokenType(Exception):
    """Raised by decode_and_build_context when a token of the wrong `type` claim is
    presented (e.g. an mfa_pending token where an access token is required)."""


def decode_and_build_context(token: str, db: Session, *, expected_type: str) -> TenantContext:
    """Shared by every auth channel that needs to turn a raw JWT string into a
    TenantContext: the JSON API's Authorization-header dependencies below, and
    web/deps.py's cookie-based equivalent. Keeping this in one place means the two
    channels can never drift on claim validation — only on WHERE the token comes from.

    Deliberately does NOT catch jwt's exceptions itself: jwt.ExpiredSignatureError vs
    jwt.InvalidTokenError vs WrongTokenType are meaningfully different outcomes to a
    caller (e.g. the web layer treats "expired" as refreshable but "invalid" as an
    immediate redirect-to-login), so translation is left to each call site."""
    payload = decode_token(token)  # may raise jwt.ExpiredSignatureError / jwt.InvalidTokenError

    if payload.get("type") != expected_type:
        raise WrongTokenType(f"Expected a {expected_type!r} token, got {payload.get('type')!r}")

    ctx = TenantContext(
        tenant_id=uuid.UUID(payload["tenant_id"]),
        user_id=uuid.UUID(payload["sub"]),
        role=payload["role"],
    )

    # Defense-in-depth for Postgres: mirrors the tenant_id into a session-local setting
    # that the RLS policies (see migrations — Postgres only, a no-op elsewhere) read.
    # FastAPI resolves `db` once per request and shares it across dependencies, so this
    # SET LOCAL applies to the same transaction every route handler's queries run in.
    # Primary tenant isolation is still the repository-layer filter (repositories/base.py)
    # — this is a second, independent layer, not a replacement for it.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SET LOCAL app.current_tenant_id = :tid"), {"tid": str(ctx.tenant_id)})

    return ctx


def _header_context(credentials: HTTPAuthorizationCredentials, db: Session, *, expected_type: str) -> TenantContext:
    try:
        return decode_and_build_context(credentials.credentials, db, expected_type=expected_type)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired") from None
    except (jwt.InvalidTokenError, WrongTokenType):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from None


def get_current_context(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> TenantContext:
    return _header_context(credentials, db, expected_type="access")


def get_mfa_pending_context(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> TenantContext:
    """For the two /auth/webauthn/login/* endpoints only: the client has passed the
    password check but not yet completed the second factor, so it holds a short-lived
    mfa_pending token (see api/v1/auth.py's login()) instead of a real access token.
    This must never be accepted anywhere a normal access token is (it grants no
    permissions — require_permission() is never used with it)."""
    return _header_context(credentials, db, expected_type="mfa_pending")


def require_permission(permission: str):
    def _check(ctx: TenantContext = Depends(get_current_context)) -> TenantContext:
        if not role_has_permission(UserRole(ctx.role), permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {permission}")
        return ctx

    return _check
