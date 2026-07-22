from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.services import account_service
from pospay.web.deps import get_web_context, render_template, require_web_permission
from pospay.web.security import verify_csrf

router = APIRouter(prefix="/ui/accounts", tags=["web-accounts"])


@router.get("")
def list_accounts(
    request: Request, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_web_context)
) -> HTMLResponse:
    accounts = account_service.list_accounts(db, ctx.tenant_id)
    return render_template(request, "accounts/list.html", ctx=ctx, accounts=accounts)


@router.post("")
def create_account(
    request: Request,
    account_number: str = Form(...),
    name: str = Form(...),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("account:write")),
    _csrf: None = Depends(verify_csrf),
) -> RedirectResponse:
    account_service.create_account(db, ctx.tenant_id, account_service.AccountInput(account_number=account_number, name=name))
    db.commit()
    return RedirectResponse("/ui/accounts?flash=Account+created.", status_code=303)
