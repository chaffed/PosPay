import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from pospay.auth.deps import require_permission
from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.domain.exception_item import ExceptionStatus
from pospay.schemas.exception import ExceptionRead
from pospay.services import exception_service

router = APIRouter(prefix="/exceptions", tags=["exceptions"])


@router.get("", response_model=list[ExceptionRead])
def list_exceptions(
    network_code: str | None = None,
    status_filter: ExceptionStatus | None = None,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("exception:read")),
) -> list[ExceptionRead]:
    items = exception_service.list_exceptions(db, ctx.tenant_id, network_code=network_code, status=status_filter)
    return [ExceptionRead.from_orm_row(i) for i in items]


@router.get("/{exception_id}", response_model=ExceptionRead)
def get_exception(
    exception_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("exception:read")),
) -> ExceptionRead:
    item = exception_service.get_exception(db, ctx.tenant_id, exception_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exception not found")
    return ExceptionRead.from_orm_row(item)
