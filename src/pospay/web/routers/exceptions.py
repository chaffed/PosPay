# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import uuid
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.domain.decision import DecisionOutcome
from pospay.domain.exception_item import ExceptionItem, ExceptionStatus
from pospay.networks.registry import get_adapter
from pospay.repositories.exception_repo import ExceptionRepository
from pospay.services import ach_return_reason_service, audit_log_service, decision_service, exception_service
from pospay.services.decision_service import DecisionError
from pospay.web.deps import WebNotFound, render_template, require_web_permission
from pospay.web.pagination import paginate
from pospay.web.security import verify_csrf

router = APIRouter(prefix="/ui/exceptions", tags=["web-exceptions"])

_DECISION_ERROR_MESSAGES = {
    DecisionError.NOT_FOUND: "Exception not found.",
    DecisionError.ALREADY_DECIDED: "This exception has already been decided.",
    DecisionError.RECOMMENDATION_REQUIRED: "A recommendation is required before this can be decided under dual control.",
    DecisionError.MAKER_CANNOT_APPROVE_OWN_RECOMMENDATION: "You recommended this decision — a different user must approve it.",
    DecisionError.WITHDRAWN: "This exception was withdrawn because its underlying item was backed out.",
    DecisionError.RETURN_REASON_REQUIRED: "Select a return reason from the list — freeform text isn't accepted for ACH returns.",
    DecisionError.INVALID_RETURN_REASON: "That return reason no longer exists or has been deactivated — pick another.",
}


def _parse_optional_uuid(raw: str) -> uuid.UUID | None:
    return uuid.UUID(raw) if raw else None


def _summarize_source_item(network_code: str, source_item: Any) -> dict[str, Any]:
    """The exceptions queue/detail is network-agnostic, but a reviewer still needs to see
    what the underlying check/ACH transaction actually was — this builds a small display
    dict from whichever concrete row networks.registry.get_adapter().load_source_item()
    returned, so the template never needs to branch on network-specific field names."""
    if network_code == "check":
        return {
            "label": f"Check #{source_item.check_number}",
            "amount": source_item.presented_amount,
            "date": str(source_item.presented_date),
        }
    if network_code == "ach":
        return {
            "label": f"{source_item.originator_name} ({source_item.originator_id})",
            "amount": source_item.amount,
            "date": str(source_item.effective_date),
        }
    return {"label": str(source_item.id), "amount": None, "date": ""}


@router.get("")
def list_exceptions(
    request: Request,
    network_code: str | None = None,
    status: ExceptionStatus | None = None,
    page: int = 1,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("exception:read")),
) -> HTMLResponse:
    page_obj = paginate(
        page=page,
        count_fn=lambda: ExceptionRepository(db, ctx.tenant_id, ctx.customer_id).count(
            network_code=network_code, status=status
        ),
        list_fn=lambda **kw: exception_service.list_exceptions(
            db, ctx.tenant_id, network_code=network_code, status=status, customer_id=ctx.customer_id,
            order_by=ExceptionItem.created_at.desc(), **kw,
        ),
    )
    # Per-row enrichment only ever runs over the current page's rows, not the whole
    # filtered result set — a nice side effect of paginating this network-agnostic
    # per-item load_source_item() call, which used to run once per row across every
    # matching exception regardless of how many were ever shown at once.
    rows = []
    for item in page_obj.items:
        adapter = get_adapter(item.network_code)
        source_item = adapter.load_source_item(db, item.source_item_id)
        rows.append(
            {
                "exception": item,
                "summary": _summarize_source_item(item.network_code, source_item) if source_item else {"label": "(missing)", "amount": None, "date": ""},
            }
        )
    return render_template(
        request, "exceptions/list.html", ctx=ctx, rows=rows, page_obj=page_obj, network_filter=network_code, status_filter=status
    )


@router.get("/{exception_id}")
def exception_detail(
    request: Request,
    exception_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("exception:read")),
) -> HTMLResponse:
    item = exception_service.get_exception(db, ctx.tenant_id, exception_id, customer_id=ctx.customer_id)
    if item is None:
        raise WebNotFound()

    adapter = get_adapter(item.network_code)
    source_item = adapter.load_source_item(db, item.source_item_id)
    summary = _summarize_source_item(item.network_code, source_item) if source_item else None
    decision = decision_service.get_decision_for_exception(db, ctx.tenant_id, exception_id, customer_id=ctx.customer_id)
    ach_return_reasons = (
        ach_return_reason_service.list_ach_return_reasons(db, ctx.tenant_id, active_only=True)
        if item.network_code == "ach"
        else []
    )

    return render_template(
        request,
        "exceptions/detail.html",
        ctx=ctx,
        item=item,
        exception_types=item.exception_types.split(",") if item.exception_types else [],
        summary=summary,
        decision=decision,
        ach_return_reasons=ach_return_reasons,
    )


@router.post("/{exception_id}/recommend")
def recommend(
    exception_id: uuid.UUID,
    outcome: DecisionOutcome = Form(...),
    reason_code: str = Form(""),
    notes: str = Form(""),
    ach_return_reason_id: str = Form(""),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("exception:recommend")),
    _csrf: None = Depends(verify_csrf),
) -> RedirectResponse:
    result = decision_service.submit_recommendation(
        db, ctx.tenant_id, exception_id, ctx, outcome=outcome, reason_code=reason_code, notes=notes or None,
        ach_return_reason_id=_parse_optional_uuid(ach_return_reason_id),
    )
    if result.error is None:
        audit_log_service.record_action(
            db,
            ctx.tenant_id,
            actor_user_id=ctx.user_id,
            channel="web",
            action="exception.recommend",
            summary=f"Recommended {outcome.value} on exception ({reason_code})",
            resource_type="exception_item",
            resource_id=exception_id,
        )
    db.commit()
    if result.error is not None:
        message = _DECISION_ERROR_MESSAGES[result.error]
        return RedirectResponse(f"/ui/exceptions/{exception_id}?error={quote(message)}", status_code=303)
    return RedirectResponse(f"/ui/exceptions/{exception_id}?flash=Recommendation+submitted.", status_code=303)


@router.post("/{exception_id}/decide")
def decide(
    exception_id: uuid.UUID,
    outcome: DecisionOutcome = Form(...),
    reason_code: str = Form(""),
    notes: str = Form(""),
    ach_return_reason_id: str = Form(""),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("exception:decide")),
    _csrf: None = Depends(verify_csrf),
) -> RedirectResponse:
    result = decision_service.decide(
        db, ctx.tenant_id, exception_id, ctx, outcome=outcome, reason_code=reason_code, notes=notes or None,
        ach_return_reason_id=_parse_optional_uuid(ach_return_reason_id),
    )
    if result.error is None:
        audit_log_service.record_action(
            db,
            ctx.tenant_id,
            actor_user_id=ctx.user_id,
            channel="web",
            action="exception.decide",
            summary=f"Decided {outcome.value} on exception ({reason_code})",
            resource_type="exception_item",
            resource_id=exception_id,
        )
    db.commit()
    if result.error is not None:
        message = _DECISION_ERROR_MESSAGES[result.error]
        return RedirectResponse(f"/ui/exceptions/{exception_id}?error={quote(message)}", status_code=303)
    return RedirectResponse(f"/ui/exceptions/{exception_id}?flash=Decision+recorded.", status_code=303)
