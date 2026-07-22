import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from pospay.auth.login_service import authenticate_password
from pospay.auth.security import create_token, decode_token
from pospay.db.session import get_db
from pospay.domain.user import User
from pospay.schemas.auth import LoginRequest, LoginResponse, RefreshRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    identity = authenticate_password(db, payload.tenant_slug, payload.email, payload.password)
    if identity is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    user, tenant = identity.user, identity.tenant

    if identity.mfa_required:
        mfa_token = create_token(user_id=user.id, tenant_id=tenant.id, role=user.role.value, token_type="mfa_pending")
        return LoginResponse(mfa_required=True, mfa_token=mfa_token)

    return LoginResponse(
        mfa_required=False,
        access_token=create_token(user_id=user.id, tenant_id=tenant.id, role=user.role.value, token_type="access"),
        refresh_token=create_token(user_id=user.id, tenant_id=tenant.id, role=user.role.value, token_type="refresh"),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        claims = decode_token(payload.refresh_token)
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token") from None

    if claims.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not a refresh token")

    user = db.get(User, uuid.UUID(claims["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer active")

    return TokenResponse(
        access_token=create_token(
            user_id=user.id, tenant_id=user.tenant_id, role=user.role.value, token_type="access"
        ),
        refresh_token=create_token(
            user_id=user.id, tenant_id=user.tenant_id, role=user.role.value, token_type="refresh"
        ),
    )
