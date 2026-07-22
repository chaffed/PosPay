import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from pospay.bulk_import.nacha import NachaParseError, parse_nacha_file
from pospay.bulk_import.tabular import TabularParseError, parse_tabular_file
from pospay.db.tenancy import TenantContext
from pospay.db.session import get_db
from pospay.domain.ach_transaction import AchTransactionType
from pospay.networks.ach.bulk_import import ingest_ach_rows, ingest_nacha_entries
from pospay.networks.ach.ingestion import AchTransactionSubmission, ingest_ach_transaction
from pospay.repositories.ach_transaction_repo import AchTransactionRepository
from pospay.services import account_service
from pospay.web.deps import WebNotFound, get_web_context, render_template, require_web_permission
from pospay.web.security import verify_csrf

router = APIRouter(prefix="/ui/ach/transactions", tags=["web-ach-transactions"])


@router.get("")
def list_transactions(
    request: Request, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_web_context)
) -> HTMLResponse:
    txns = AchTransactionRepository(db, ctx.tenant_id).list()
    return render_template(request, "ach/transactions_list.html", ctx=ctx, txns=txns)


@router.get("/new")
def new_transaction_form(
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("ach_transaction:write")),
) -> HTMLResponse:
    accounts = account_service.list_accounts(db, ctx.tenant_id)
    return render_template(request, "ach/transaction_form.html", ctx=ctx, accounts=accounts)


@router.post("")
def create_transaction(
    request: Request,
    account_id: uuid.UUID = Form(...),
    originator_id: str = Form(...),
    originator_name: str = Form(...),
    receiver_id: str = Form(""),
    amount: str = Form(...),
    transaction_type: AchTransactionType = Form(...),
    sec_code: str = Form(...),
    trace_number: str = Form(...),
    effective_date: str = Form(...),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("ach_transaction:write")),
    _csrf: None = Depends(verify_csrf),
) -> HTMLResponse:
    try:
        parsed_amount = Decimal(amount)
        parsed_date = date.fromisoformat(effective_date)
    except (InvalidOperation, ValueError):
        accounts = account_service.list_accounts(db, ctx.tenant_id)
        return render_template(
            request, "ach/transaction_form.html", ctx=ctx, accounts=accounts, error="Invalid amount or date.", status_code=422
        )

    txn = ingest_ach_transaction(
        db,
        ctx.tenant_id,
        AchTransactionSubmission(
            account_id=account_id,
            originator_id=originator_id,
            originator_name=originator_name,
            receiver_id=receiver_id or None,
            amount=parsed_amount,
            transaction_type=transaction_type,
            sec_code=sec_code.upper(),
            trace_number=trace_number,
            effective_date=parsed_date,
        ),
    )
    db.commit()

    flash = "Transaction matched." if txn.match_status.value == "matched" else "Transaction created an exception — see the Exceptions queue."
    return RedirectResponse(f"/ui/ach/transactions/{txn.id}?flash={quote(flash)}", status_code=303)


# NOTE: /bulk must be registered before /{transaction_id} below — FastAPI matches path
# patterns in registration order, and "bulk" would otherwise be captured as
# transaction_id and rejected as an invalid UUID before this route is ever tried.


@router.get("/bulk")
def bulk_upload_form(
    request: Request, ctx: TenantContext = Depends(require_web_permission("ach_transaction:write"))
) -> HTMLResponse:
    return render_template(request, "ach/transaction_bulk_upload.html", ctx=ctx)


@router.post("/bulk")
async def bulk_upload_transactions(
    request: Request,
    upload_file: UploadFile,
    format: Literal["tabular", "nacha"] = Form(...),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("ach_transaction:write")),
    _csrf: None = Depends(verify_csrf),
) -> HTMLResponse:
    content = await upload_file.read()

    if format == "nacha":
        try:
            entries = parse_nacha_file(content)
        except NachaParseError as exc:
            return render_template(
                request, "ach/transaction_bulk_upload.html", ctx=ctx, nacha_error=str(exc), status_code=422
            )
        results = ingest_nacha_entries(db, ctx.tenant_id, entries)
    else:
        try:
            rows = parse_tabular_file(upload_file.filename or "upload.csv", content)
        except TabularParseError as exc:
            return render_template(
                request, "ach/transaction_bulk_upload.html", ctx=ctx, tabular_error=str(exc), status_code=422
            )
        if not rows:
            return render_template(
                request,
                "ach/transaction_bulk_upload.html",
                ctx=ctx,
                tabular_error="That file has no data rows.",
                status_code=422,
            )
        results = ingest_ach_rows(db, ctx.tenant_id, rows)

    return render_template(
        request,
        "bulk_result.html",
        ctx=ctx,
        results=results,
        back_url="/ui/ach/transactions",
        back_label="Back to ACH transactions",
    )


@router.get("/{transaction_id}")
def transaction_detail(
    request: Request,
    transaction_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_web_context),
) -> HTMLResponse:
    txn = AchTransactionRepository(db, ctx.tenant_id).get(transaction_id)
    if txn is None:
        raise WebNotFound()
    return render_template(request, "ach/transaction_detail.html", ctx=ctx, txn=txn)
