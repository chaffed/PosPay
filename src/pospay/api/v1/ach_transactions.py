import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from pospay.auth.deps import require_permission
from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.networks.ach.ingestion import AchTransactionSubmission, ingest_ach_transaction, ingest_ach_transactions_bulk
from pospay.repositories.ach_transaction_repo import AchTransactionRepository
from pospay.schemas.ach import AchTransactionCreate, AchTransactionRead
from pospay.schemas.common import BulkRowResultOut, BulkSubmitResponse

router = APIRouter(prefix="/ach/transactions", tags=["ach-transactions"])


def _to_submission(payload: AchTransactionCreate) -> AchTransactionSubmission:
    return AchTransactionSubmission(**payload.model_dump())


@router.post("", response_model=AchTransactionRead, status_code=status.HTTP_201_CREATED)
def create_ach_transaction(
    payload: AchTransactionCreate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("ach_transaction:write")),
) -> AchTransactionRead:
    txn = ingest_ach_transaction(db, ctx.tenant_id, _to_submission(payload))
    db.commit()
    return AchTransactionRead.model_validate(txn)


@router.post("/bulk", response_model=BulkSubmitResponse)
def create_ach_transactions_bulk(
    payload: list[AchTransactionCreate],
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("ach_transaction:write")),
) -> BulkSubmitResponse:
    submissions = [_to_submission(row) for row in payload]
    results = ingest_ach_transactions_bulk(db, ctx.tenant_id, submissions)
    out = [
        BulkRowResultOut(
            index=r.index,
            success=r.success,
            id=str(r.ach_transaction_id) if r.ach_transaction_id else None,
            status=r.match_status,
            error=r.error,
        )
        for r in results
    ]
    return BulkSubmitResponse(
        total=len(out), succeeded=sum(r.success for r in out), failed=sum(not r.success for r in out), results=out
    )


@router.get("", response_model=list[AchTransactionRead])
def list_ach_transactions(
    account_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("issued_item:read")),
) -> list[AchTransactionRead]:
    txns = AchTransactionRepository(db, ctx.tenant_id).list(account_id=account_id)
    return [AchTransactionRead.model_validate(t) for t in txns]


@router.get("/{transaction_id}", response_model=AchTransactionRead)
def get_ach_transaction(
    transaction_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("issued_item:read")),
) -> AchTransactionRead:
    txn = AchTransactionRepository(db, ctx.tenant_id).get(transaction_id)
    if txn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ACH transaction not found")
    return AchTransactionRead.model_validate(txn)
