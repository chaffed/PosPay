# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from pospay.auth.login_service import PasswordLoginOutcome, authenticate_password
from pospay.auth.security import create_token, decode_token
from pospay.db.session import get_db
from pospay.domain.tenant import Tenant
from pospay.domain.tenant_membership import TenantMembership
from pospay.domain.user import User
from pospay.schemas.auth import LoginRequest, LoginResponse, RefreshRequest, TokenResponse
from pospay.services import demo_tenant_service, user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    # See web/routers/auth.py::login_submit's identical call for why this runs before
    # any identity for this request is resolved -- a no-op for every non-demo tenant.
    demo_tenant_service.maybe_reset_if_demo_idle_by_slug(db, payload.tenant_slug)
    db.commit()
    result = authenticate_password(db, payload.tenant_slug, payload.email, payload.password)
    # authenticate_password only flushes (see its docstring) — commit unconditionally,
    # even on a failed attempt, so the incremented failed_login_attempts/locked_until
    # actually persist rather than being discarded when this request's session closes.
    db.commit()
    if result.outcome == PasswordLoginOutcome.SSO_REQUIRED:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This organization requires single sign-on")
    if result.outcome == PasswordLoginOutcome.LOCKED:
        raise HTTPException(status.HTTP_423_LOCKED, "Too many failed attempts — account is temporarily locked")
    if result.outcome != PasswordLoginOutcome.SUCCESS or result.identity is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    identity = result.identity
    user, tenant, membership = identity.user, identity.tenant, identity.membership

    if identity.mfa_required:
        mfa_token = create_token(
            user_id=user.id,
            tenant_id=tenant.id,
            security_group_id=membership.security_group_id,
            customer_id=membership.customer_id,
            token_type="mfa_pending",
        )
        return LoginResponse(mfa_required=True, mfa_token=mfa_token)

    response = LoginResponse(
        mfa_required=False,
        access_token=create_token(
            user_id=user.id,
            tenant_id=tenant.id,
            security_group_id=membership.security_group_id,
            customer_id=membership.customer_id,
            token_type="access",
            access_token_expire_minutes=tenant.access_token_expire_minutes,
            refresh_token_expire_minutes=tenant.refresh_token_expire_minutes,
        ),
        refresh_token=create_token(
            user_id=user.id,
            tenant_id=tenant.id,
            security_group_id=membership.security_group_id,
            customer_id=membership.customer_id,
            token_type="refresh",
            access_token_expire_minutes=tenant.access_token_expire_minutes,
            refresh_token_expire_minutes=tenant.refresh_token_expire_minutes,
        ),
    )
    user_service.record_login(db, user.id)
    db.commit()
    return response


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        claims = decode_token(payload.refresh_token)
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token") from None

    if claims.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not a refresh token")

    user_id = uuid.UUID(claims["sub"])
    tenant_id = uuid.UUID(claims["tenant_id"])
    customer_id = uuid.UUID(claims["customer_id"]) if claims.get("customer_id") else None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer active")

    # Re-derived from the current membership (not the token's own security_group_id
    # claim) so a group reassignment since the refresh token was issued takes effect here
    # — the same "always reflects current state" property this already had for role
    # changes before security groups replaced roles. customer_id is part of the lookup
    # (not just user_id/tenant_id) because one user can hold several memberships in the
    # same tenant now — see domain/tenant_membership.py.
    membership = db.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.customer_id == customer_id,
        )
    ).scalar_one_or_none()
    if membership is None or not membership.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Membership no longer active")

    tenant = db.get(Tenant, tenant_id)
    return TokenResponse(
        access_token=create_token(
            user_id=user.id,
            tenant_id=tenant_id,
            security_group_id=membership.security_group_id,
            customer_id=customer_id,
            token_type="access",
            access_token_expire_minutes=tenant.access_token_expire_minutes,
            refresh_token_expire_minutes=tenant.refresh_token_expire_minutes,
        ),
        refresh_token=create_token(
            user_id=user.id,
            tenant_id=tenant_id,
            security_group_id=membership.security_group_id,
            customer_id=customer_id,
            token_type="refresh",
            access_token_expire_minutes=tenant.access_token_expire_minutes,
            refresh_token_expire_minutes=tenant.refresh_token_expire_minutes,
        ),
    )
