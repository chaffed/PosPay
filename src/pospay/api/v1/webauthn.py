import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from pospay.auth.deps import get_current_context, get_mfa_pending_context
from pospay.auth.security import create_token
from pospay.auth.webauthn_service import (
    WebauthnError,
    begin_authentication,
    begin_registration,
    complete_authentication,
    complete_registration,
    delete_credential,
    list_credentials,
)
from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.domain.user import User
from pospay.schemas.auth import TokenResponse
from pospay.schemas.webauthn import AuthenticationVerifyRequest, RegistrationVerifyRequest, WebauthnCredentialRead

router = APIRouter(prefix="/auth/webauthn", tags=["webauthn"])


def _get_user_or_500(db: Session, ctx: TenantContext) -> User:
    user = db.get(User, ctx.user_id)
    if user is None:
        # Shouldn't happen: a valid token was issued for this user_id, so a missing row
        # here means the user was deleted after the token was issued, not a client error.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    return user


@router.post("/register/options")
def register_options(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_current_context),
) -> Response:
    user = _get_user_or_500(db, ctx)
    options_json = begin_registration(db, user)
    db.commit()
    return Response(content=options_json, media_type="application/json")


@router.post("/register/verify", response_model=WebauthnCredentialRead, status_code=status.HTTP_201_CREATED)
def register_verify(
    payload: RegistrationVerifyRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_current_context),
) -> WebauthnCredentialRead:
    user = _get_user_or_500(db, ctx)
    try:
        credential = complete_registration(db, user, payload.credential, nickname=payload.nickname)
    except WebauthnError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    db.commit()
    return WebauthnCredentialRead.model_validate(credential)


@router.get("/credentials", response_model=list[WebauthnCredentialRead])
def get_credentials(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_current_context),
) -> list[WebauthnCredentialRead]:
    credentials = list_credentials(db, ctx.tenant_id, ctx.user_id)
    return [WebauthnCredentialRead.model_validate(c) for c in credentials]


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_credential(
    credential_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_current_context),
) -> None:
    deleted = delete_credential(db, ctx.tenant_id, ctx.user_id, credential_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Credential not found")
    db.commit()


@router.post("/login/options")
def login_options(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_mfa_pending_context),
) -> Response:
    user = _get_user_or_500(db, ctx)
    try:
        options_json = begin_authentication(db, user)
    except WebauthnError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    db.commit()
    return Response(content=options_json, media_type="application/json")


@router.post("/login/verify", response_model=TokenResponse)
def login_verify(
    payload: AuthenticationVerifyRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_mfa_pending_context),
) -> TokenResponse:
    user = _get_user_or_500(db, ctx)
    try:
        complete_authentication(db, user, payload.credential)
    except WebauthnError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None

    tokens = TokenResponse(
        access_token=create_token(user_id=user.id, tenant_id=user.tenant_id, role=user.role.value, token_type="access"),
        refresh_token=create_token(
            user_id=user.id, tenant_id=user.tenant_id, role=user.role.value, token_type="refresh"
        ),
    )
    db.commit()
    return tokens
