import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from pospay.auth.deps import require_permission
from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.domain.ach_authorization_rule import AchAuthorizationStatus
from pospay.schemas.ach import AchAuthorizationCreate, AchAuthorizationRead
from pospay.services import ach_authorization_service

router = APIRouter(prefix="/ach/authorizations", tags=["ach-authorizations"])


@router.post("", response_model=AchAuthorizationRead, status_code=status.HTTP_201_CREATED)
def create_ach_authorization(
    payload: AchAuthorizationCreate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("ach_authorization:write")),
) -> AchAuthorizationRead:
    rule = ach_authorization_service.create_ach_authorization(
        db,
        ctx.tenant_id,
        ach_authorization_service.AchAuthorizationInput(**payload.model_dump()),
        created_by_user_id=ctx.user_id,
    )
    db.commit()
    return AchAuthorizationRead.model_validate(rule)


@router.get("", response_model=list[AchAuthorizationRead])
def list_ach_authorizations(
    status_filter: AchAuthorizationStatus | None = None,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("issued_item:read")),
) -> list[AchAuthorizationRead]:
    rules = ach_authorization_service.list_ach_authorizations(db, ctx.tenant_id, status=status_filter)
    return [AchAuthorizationRead.model_validate(r) for r in rules]


@router.patch("/{rule_id}/revoke", response_model=AchAuthorizationRead)
def revoke_ach_authorization(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("ach_authorization:write")),
) -> AchAuthorizationRead:
    rule = ach_authorization_service.revoke_ach_authorization(db, ctx.tenant_id, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ACH authorization not found")
    db.commit()
    return AchAuthorizationRead.model_validate(rule)
