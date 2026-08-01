# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""Two independently permission-gated, static-content documentation tracks: End User
(day-to-day operational how-tos, gated by end_user_documentation:read) and Bank
Administrator (setup/configuration topics, gated by admin_documentation:read). See
auth/permissions.py for which default security groups get each permission."""

from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.web.deps import render_template, require_web_permission

router = APIRouter(prefix="/ui/docs", tags=["web-docs"])


@dataclass(frozen=True)
class DocPage:
    slug: str
    title: str
    summary: str


END_USER_DOC_PAGES: list[DocPage] = [
    DocPage("getting-started", "Getting Started", "Logging in, the tenant/customer/account model, and the dashboard."),
    DocPage("issued-items", "Issued Items", "Recording checks a company has written, single-entry or bulk."),
    DocPage("paid-items", "Paid Items", "Recording checks that cleared, so they can be matched against issued items."),
    DocPage("stop-payments", "Stop Payments", "Placing or cancelling a stop on a specific check."),
    DocPage("check-images", "Check Images", "Uploading front/back check images and reprocessing them."),
    DocPage("ach-transactions", "ACH Transactions", "Submitting incoming ACH debits and credits for screening."),
    DocPage("ach-authorizations", "ACH Authorizations & Allow Rules", "Maintaining the allow list ACH transactions are screened against."),
    DocPage("exceptions", "Exceptions & Decisioning", "Reviewing and deciding flagged checks and ACH items."),
    DocPage("wsud", "Unauthorized Debit Statements", "Signing a statement that a returned ACH debit was unauthorized."),
    DocPage("fraud-training", "Known-Fraud Training Data", "Labeling known-fraud items to improve the ML model."),
    DocPage("bulk-uploads", "Bulk File Uploads", "Uploading files in bulk, and undoing an upload if needed."),
]
END_USER_DOC_PAGES_BY_SLUG: dict[str, DocPage] = {p.slug: p for p in END_USER_DOC_PAGES}

ADMIN_DOC_PAGES: list[DocPage] = [
    DocPage("users-security-groups", "Users & Security Groups", "Managing users, permissions, and multi-customer access."),
    DocPage("customers-accounts", "Customers & Accounts", "Managing the customers and bank accounts under your organization."),
    DocPage("ml-admin", "ML Scoring & Default Disposition", "Configuring fraud scoring behavior and auto-decisions on expired exceptions."),
    DocPage("notifications-webauthn", "Notifications & Account Security", "Email/SMS preferences and passkey (WebAuthn) management."),
    DocPage("branding-settings", "Organization Settings & Branding", "Branding, dual control, session timeouts, and dark mode."),
    DocPage("audit-log", "Audit Log", "The immutable, tamper-evident record of every action taken."),
    DocPage("data-export", "Data Export", "Exporting all tenant or customer data for migration or offboarding."),
    DocPage("authentication", "Login, SSO & Account Lockout", "Configuring single sign-on and handling locked-out users."),
    DocPage("demo-tenant", "Demo Tenant", "Resetting the sales demo environment to a clean state."),
]
ADMIN_DOC_PAGES_BY_SLUG: dict[str, DocPage] = {p.slug: p for p in ADMIN_DOC_PAGES}


@router.get("/end-user")
def end_user_index(
    request: Request, db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("end_user_documentation:read")),
) -> HTMLResponse:
    return render_template(request, "docs/end_user/index.html", ctx=ctx, pages=END_USER_DOC_PAGES)


@router.get("/end-user/{slug}")
def end_user_page(
    slug: str, request: Request, db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("end_user_documentation:read")),
) -> HTMLResponse:
    page = END_USER_DOC_PAGES_BY_SLUG.get(slug)
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return render_template(
        request, f"docs/end_user/{slug}.html", ctx=ctx, page=page, pages=END_USER_DOC_PAGES, base_path="/ui/docs/end-user",
    )


@router.get("/admin")
def admin_index(
    request: Request, db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("admin_documentation:read")),
) -> HTMLResponse:
    return render_template(request, "docs/admin/index.html", ctx=ctx, pages=ADMIN_DOC_PAGES)


@router.get("/admin/{slug}")
def admin_page(
    slug: str, request: Request, db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("admin_documentation:read")),
) -> HTMLResponse:
    page = ADMIN_DOC_PAGES_BY_SLUG.get(slug)
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return render_template(
        request, f"docs/admin/{slug}.html", ctx=ctx, page=page, pages=ADMIN_DOC_PAGES, base_path="/ui/docs/admin",
    )
