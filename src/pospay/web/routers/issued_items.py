import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from pospay.bulk_import.tabular import TabularParseError, parse_tabular_file
from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.domain.issued_item import IssuedItemStatus
from pospay.repositories.issued_item_repo import IssuedItemRepository
from pospay.services import account_service, issued_item_service
from pospay.web.deps import WebNotFound, get_web_context, render_template, require_web_permission
from pospay.web.security import verify_csrf

router = APIRouter(prefix="/ui/issued-items", tags=["web-issued-items"])


@router.get("")
def list_issued_items(
    request: Request,
    status: IssuedItemStatus | None = None,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_web_context),
) -> HTMLResponse:
    items = issued_item_service.list_issued_items(db, ctx.tenant_id, status=status)
    return render_template(request, "issued_items/list.html", ctx=ctx, items=items, status_filter=status)


@router.get("/new")
def new_issued_item_form(
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("issued_item:write")),
) -> HTMLResponse:
    accounts = account_service.list_accounts(db, ctx.tenant_id)
    return render_template(request, "issued_items/form.html", ctx=ctx, accounts=accounts)


@router.post("")
def create_issued_item(
    request: Request,
    account_id: uuid.UUID = Form(...),
    check_number: str = Form(...),
    amount: str = Form(...),
    payee_name: str = Form(...),
    issue_date: str = Form(...),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("issued_item:write")),
    _csrf: None = Depends(verify_csrf),
) -> HTMLResponse:
    from datetime import date
    from decimal import Decimal, InvalidOperation

    try:
        parsed_amount = Decimal(amount)
        parsed_issue_date = date.fromisoformat(issue_date)
    except (InvalidOperation, ValueError):
        accounts = account_service.list_accounts(db, ctx.tenant_id)
        return render_template(
            request,
            "issued_items/form.html",
            ctx=ctx,
            accounts=accounts,
            error="Invalid amount or date.",
            status_code=422,
        )

    try:
        issued_item_service.create_issued_item(
            db,
            ctx.tenant_id,
            issued_item_service.IssuedItemInput(
                account_id=account_id,
                check_number=check_number,
                amount=parsed_amount,
                payee_name=payee_name,
                issue_date=parsed_issue_date,
            ),
            submitted_by_user_id=ctx.user_id,
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001 — surface a DB constraint violation (e.g. duplicate check number) to the form
        db.rollback()
        accounts = account_service.list_accounts(db, ctx.tenant_id)
        return render_template(
            request,
            "issued_items/form.html",
            ctx=ctx,
            accounts=accounts,
            error=f"Could not create issued item: {exc}",
            status_code=422,
        )

    return RedirectResponse("/ui/issued-items?flash=Issued+item+created.", status_code=303)


# NOTE: /bulk must be registered before /{item_id} below — FastAPI matches path patterns
# in registration order, and "bulk" would otherwise be captured as item_id and rejected
# as an invalid UUID before this route is ever tried.


@router.get("/bulk")
def bulk_upload_form(
    request: Request, ctx: TenantContext = Depends(require_web_permission("issued_item:write"))
) -> HTMLResponse:
    return render_template(request, "issued_items/bulk_upload.html", ctx=ctx)


@router.post("/bulk")
async def bulk_upload_issued_items(
    request: Request,
    upload_file: UploadFile,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("issued_item:write")),
    _csrf: None = Depends(verify_csrf),
) -> HTMLResponse:
    content = await upload_file.read()
    try:
        rows = parse_tabular_file(upload_file.filename or "upload.csv", content)
    except TabularParseError as exc:
        return render_template(
            request, "issued_items/bulk_upload.html", ctx=ctx, error=str(exc), status_code=422
        )

    if not rows:
        return render_template(
            request, "issued_items/bulk_upload.html", ctx=ctx, error="That file has no data rows.", status_code=422
        )

    results = issued_item_service.create_issued_items_from_rows(
        db, ctx.tenant_id, rows, submitted_by_user_id=ctx.user_id
    )
    return render_template(
        request,
        "bulk_result.html",
        ctx=ctx,
        results=results,
        back_url="/ui/issued-items",
        back_label="Back to issued items",
    )


@router.get("/{item_id}")
def issued_item_detail(
    request: Request,
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_web_context),
) -> HTMLResponse:
    item = IssuedItemRepository(db, ctx.tenant_id).get(item_id)
    if item is None:
        raise WebNotFound()
    return render_template(request, "issued_items/detail.html", ctx=ctx, item=item)


@router.post("/{item_id}/void")
def void_issued_item(
    item_id: uuid.UUID,
    reason: str = Form(...),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("issued_item:write")),
    _csrf: None = Depends(verify_csrf),
) -> RedirectResponse:
    item = issued_item_service.void_issued_item(db, ctx.tenant_id, item_id, reason)
    db.commit()
    if item is None:
        return RedirectResponse(f"/ui/issued-items?error={quote('Issued item not found.')}", status_code=303)
    return RedirectResponse(f"/ui/issued-items/{item_id}?flash=Issued+item+voided.", status_code=303)
