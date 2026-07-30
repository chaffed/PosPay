#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""Regenerates the screenshots referenced by README.md.

Seeds a throwaway demo tenant with realistic-looking data in a scratch SQLite database
(never the real .pospay-run/ or project-root pospay.db), runs the actual app against it,
and drives a real headless browser (Playwright) through the key screens to capture PNGs
into docs/screenshots/. The screenshots are committed to the repo, so this is a manual,
occasional dev task, not something CI runs — rerun it after a UI change significant
enough to make the committed images visibly stale.

Usage:
    pip install -e ".[dev]"
    playwright install chromium
    python scripts/generate_screenshots.py
"""

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCREENSHOT_DIR = PROJECT_ROOT / "docs" / "screenshots"
HOST = "127.0.0.1"
PORT = 8799
BASE_URL = f"http://{HOST}:{PORT}"

TENANT_NAME = "Riverside Community Bank"
TENANT_SLUG = "riverside-bank"
ADMIN_EMAIL = "admin@riversidebank.example.com"
ADMIN_PASSWORD = "DemoPassword123!"
VIEWPORT = {"width": 1440, "height": 900}


def _configure_env(run_dir: Path) -> None:
    # Mirrors scripts/launcher.py::_configure_run_env's pattern — must run before any
    # `from pospay...` import, since config.Settings is @lru_cache'd. Points everything
    # at a throwaway temp dir so this never touches the real .pospay-run/ or a
    # project-root pospay.db.
    os.environ["POSPAY_ENVIRONMENT"] = "development"
    os.environ["POSPAY_DATABASE_URL"] = f"sqlite:///{run_dir / 'screenshots.db'}"
    os.environ["POSPAY_CHECK_IMAGE_STORAGE_DIR"] = str(run_dir / "check_images")
    os.environ["POSPAY_TENANT_ASSET_STORAGE_DIR"] = str(run_dir / "tenant_assets")
    os.environ["POSPAY_BULK_UPLOAD_STORAGE_DIR"] = str(run_dir / "bulk_uploads")
    os.environ["POSPAY_ML_ARTIFACT_DIR"] = str(run_dir / "ml_artifacts")


def _decision_ctx(tenant, user_id):
    from pospay.db.tenancy import TenantContext

    # decision_service.decide only reads ctx.tenant_id/user_id (not permissions or
    # branding), so placeholder values are fine here — this ctx never goes through a
    # require_permission() check or gets rendered in a template.
    return TenantContext(
        tenant_id=tenant.id,
        user_id=user_id,
        security_group_id=uuid.uuid4(),
        permissions=frozenset(),
        tenant_slug=tenant.slug,
        tenant_name=tenant.name,
        accent_color=None,
        has_logo=False,
        has_favicon=False,
        customer_id=None,
        customer_name=None,
    )


def _seed_demo_data() -> None:
    # Registers each network's adapter (register_adapter side effect) — normally done by
    # main.py::create_app(), but seeding here runs in this process, before the app
    # subprocess even starts.
    import pospay.networks.ach  # noqa: F401
    import pospay.networks.check  # noqa: F401
    import pospay.domain  # noqa: F401  (populates Base.metadata with every model)
    from sqlalchemy import select

    from pospay.db.base import Base
    from pospay.db.session import get_engine, get_session_factory
    from pospay.domain.ach_authorization_rule import AchAuthorizationStatus
    from pospay.domain.ach_transaction import AchTransactionType
    from pospay.domain.decision import DecisionOutcome
    from pospay.domain.payment_network import PaymentNetwork, SettlementTiming
    from pospay.domain.tenant import Tenant
    from pospay.networks.ach.ingestion import AchTransactionSubmission, ingest_ach_transaction
    from pospay.networks.check.ingestion import PaidItemSubmission, ingest_paid_item
    from pospay.repositories.exception_repo import ExceptionRepository
    from pospay.services import (
        account_service,
        ach_authorization_service,
        audit_log_service,
        customer_service,
        decision_service,
        issued_item_service,
        provisioning_service,
        security_group_service,
        stop_payment_service,
        tenant_service,
        user_service,
    )

    engine = get_engine()
    Base.metadata.create_all(engine)

    session = get_session_factory()()
    try:
        session.add_all(
            [
                PaymentNetwork(code="check", name="Check", settlement_timing=SettlementTiming.ASYNC_REVIEWABLE),
                PaymentNetwork(code="ach", name="ACH", settlement_timing=SettlementTiming.ASYNC_REVIEWABLE),
            ]
        )
        session.commit()

        print(f"Seeding tenant {TENANT_NAME!r}...")
        identity = provisioning_service.create_tenant_with_admin(
            session, tenant_name=TENANT_NAME, tenant_slug=TENANT_SLUG, admin_email=ADMIN_EMAIL, admin_password=ADMIN_PASSWORD
        )
        session.commit()
        tenant = identity.tenant

        groups = {g.name: g for g in security_group_service.list_security_groups(session, tenant.id)}
        extra_users = [
            ("Preparer", "sarah.preparer"),
            ("Approver", "james.approver"),
            ("Viewer", "linda.viewer"),
            ("Bookkeeper", "morgan.bookkeeper"),
        ]
        users = {"admin": identity.admin_user}
        for group_name, local_part in extra_users:
            group = groups.get(group_name)
            if group is None:
                continue
            users[group_name.lower()] = user_service.create_user_with_membership(
                session, tenant.id, email=f"{local_part}@riversidebank.example.com", password=ADMIN_PASSWORD,
                security_group_id=group.id,
            )
        session.commit()
        for name, user in users.items():
            if name == "admin":
                continue
            audit_log_service.record_action(
                session, tenant.id, actor_user_id=identity.admin_user.id, channel="web", action="user.create",
                summary=f"Added user {user.email}", resource_type="user", resource_id=user.id,
            )
        session.commit()

        print("Seeding accounts and a customer...")
        operating = account_service.create_account(
            session, tenant.id, account_service.AccountInput(account_number="1000234561", name="Operating Account")
        )
        payroll = account_service.create_account(
            session, tenant.id, account_service.AccountInput(account_number="1000234562", name="Payroll Account")
        )
        customer = customer_service.create_customer(
            session, tenant.id,
            customer_service.CustomerInput(
                customer_number="CUST-1001", name="Maple Street Dental", primary_contact_name="Dana Reyes",
                email="dana@maplestreetdental.example.com",
            ),
        )
        customer_account = account_service.create_account(
            session, tenant.id,
            account_service.AccountInput(account_number="1000234563", name="Maple Street Dental Operating", customer_id=customer.id),
        )
        session.commit()

        print("Seeding issued items and paid items (some clean, some exceptions)...")
        payees = [
            "Northgate Office Supply", "Summit Roofing LLC", "Dana Reyes", "Cascade Landscaping",
            "Harbor View Consulting", "Pinecrest Utilities", "Bright Path Marketing", "Ferris Logistics",
        ]
        issue_date = date(2026, 6, 1)
        decided = 0
        for i in range(26):
            check_number = f"{1001 + i}"
            issued_amount = Decimal("100.00") + Decimal(i * 37 % 900)
            issued_item_service.create_issued_item(
                session, tenant.id,
                issued_item_service.IssuedItemInput(
                    account_id=operating.id, check_number=check_number, amount=issued_amount,
                    payee_name=payees[i % len(payees)], issue_date=issue_date + timedelta(days=i % 10),
                ),
                submitted_by_user_id=users["preparer"].id,
            )
            session.commit()

            # Every 4th check clears clean (no exception); the rest are deliberately
            # off by a few dollars so they land in the exception queue.
            presented_amount = issued_amount if i % 4 == 0 else issued_amount + Decimal("25.00")
            paid_item = ingest_paid_item(
                session, tenant.id,
                PaidItemSubmission(
                    account_id=operating.id, check_number=check_number, presented_amount=presented_amount,
                    presented_date=issue_date + timedelta(days=i % 10 + 3),
                ),
            )
            session.commit()

            if presented_amount != issued_amount:
                exception = ExceptionRepository(session, tenant.id).list(source_item_id=paid_item.id)[0]
                # Leave the last few open/pending so the review queue has something to
                # show; decide the rest so there's enough labeled history to train on.
                if i < 22:
                    outcome = DecisionOutcome.RETURN if i % 3 == 0 else DecisionOutcome.PAY
                    decision_service.decide(
                        session, tenant.id, exception.id, _decision_ctx(tenant, users["approver"].id),
                        outcome=outcome, reason_code="amount_mismatch", notes="Reviewed against issued amount.",
                    )
                    session.commit()
                    decided += 1
        print(f"  {decided} check exceptions decided, {26 - decided} left pending for the review queue.")

        print("Seeding a stop payment and the resulting exception...")
        stop_payment_service.create_stop_payment(
            session, tenant.id,
            stop_payment_service.StopPaymentInput(
                account_id=operating.id, check_number="9001", amount=None, effective_date=issue_date,
                expiration_date=issue_date + timedelta(days=180), reason="Lost in the mail per payee request.",
            ),
            created_by_user_id=users["approver"].id,
        )
        session.commit()
        ingest_paid_item(
            session, tenant.id,
            PaidItemSubmission(
                account_id=operating.id, check_number="9001", presented_amount=Decimal("450.00"),
                presented_date=issue_date + timedelta(days=5),
            ),
        )
        session.commit()

        print("Seeding ACH authorizations and transactions...")
        ach_authorization_service.create_ach_authorization(
            session, tenant.id,
            ach_authorization_service.AchAuthorizationInput(
                account_id=payroll.id, originator_id="1234567890", originator_name="Gusto Payroll",
                receiver_id=None, max_amount=Decimal("5000.00"), frequency_limit=None,
                allowed_sec_codes=["PPD"], effective_date=issue_date, expiration_date=None,
            ),
            created_by_user_id=users["approver"].id,
        )
        session.commit()
        for i in range(6):
            over_limit = i == 4
            ingest_ach_transaction(
                session, tenant.id,
                AchTransactionSubmission(
                    account_id=payroll.id, originator_id="1234567890", originator_name="Gusto Payroll",
                    amount=Decimal("12000.00") if over_limit else Decimal("2450.00"),
                    transaction_type=AchTransactionType.DEBIT, sec_code="PPD",
                    trace_number=f"00012345670000{i:02d}", effective_date=issue_date + timedelta(days=i),
                ),
            )
            session.commit()

        print("Training and activating a global check-network ML model...")
        from pospay.ml.registry import activate_model
        from pospay.ml.train import train_model

        try:
            result = train_model(session, "check")
            activate_model(session, result.model_row.id, expected_customer_id=None)
            session.commit()
            print(f"  Trained model {result.model_row.id} ({decided} decisions).")
        except Exception as exc:  # noqa: BLE001 — best-effort; the admin page still renders with no model
            print(f"  Skipping ML training ({exc}) — admin page will just show no active model.")
            session.rollback()

        tenant_service.update_tenant_branding(session, tenant.id, name=TENANT_NAME, accent_color="#0f5b8a")
        session.commit()

        print("Demo data seeded.")
    finally:
        session.close()


def _wait_for_server(deadline_seconds: float = 30) -> None:
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"Server did not come up on {HOST}:{PORT} within {deadline_seconds}s")


@dataclass(frozen=True, slots=True)
class Page:
    name: str
    path: str
    wait_for_selector: str | None = None


PAGES: list[Page] = [
    Page("dashboard", "/ui/", "table, .card"),
    Page("issued_items", "/ui/issued-items"),
    Page("exceptions", "/ui/exceptions"),
    Page("check_images_bulk", "/ui/check-images/bulk"),
    Page("ach_transactions", "/ui/ach/transactions"),
    Page("stop_payments", "/ui/stop-payments"),
    Page("accounts", "/ui/accounts"),
    Page("customers", "/ui/customers"),
    Page("users", "/ui/users"),
    Page("security_groups", "/ui/security-groups"),
    Page("settings", "/ui/settings"),
    Page("admin_ml_models", "/ui/admin"),
    Page("audit_log", "/ui/audit-log"),
]


def _capture_screenshots() -> None:
    from playwright.sync_api import sync_playwright

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT, color_scheme="light")

        print("Capturing login page...")
        page.goto(f"{BASE_URL}/ui/login")
        page.wait_for_selector("form")
        page.screenshot(path=str(SCREENSHOT_DIR / "login.png"))

        page.fill('input[name="tenant_slug"]', TENANT_SLUG)
        page.fill('input[name="email"]', ADMIN_EMAIL)
        page.fill('input[name="password"]', ADMIN_PASSWORD)
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        for spec in PAGES:
            print(f"Capturing {spec.name}...")
            page.goto(f"{BASE_URL}{spec.path}")
            if spec.wait_for_selector:
                page.wait_for_selector(spec.wait_for_selector, timeout=10_000)
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(SCREENSHOT_DIR / f"{spec.name}.png"), full_page=True)

        # A single exception's detail/review page, not just the queue — needs a real id.
        # Picks a still-*open* row (not an already-decided one) so the screenshot shows
        # the actual pay/return review form, not just a read-only past decision.
        print("Capturing exception_detail...")
        page.goto(f"{BASE_URL}/ui/exceptions")
        page.wait_for_load_state("networkidle")
        open_row_link = page.query_selector(
            'table tr:has(td .badge:text-is("open")) a[href^="/ui/exceptions/"]'
        ) or page.query_selector('table a[href^="/ui/exceptions/"]')
        if open_row_link is not None:
            open_row_link.click()
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(SCREENSHOT_DIR / "exception_detail.png"), full_page=True)
        else:
            print("  No exceptions found to open — skipping exception_detail.png")

        browser.close()


def main() -> None:
    os.chdir(PROJECT_ROOT)  # pin cwd regardless of how this was invoked — dev_keys/ and
    # every other *_key_path config default is a relative path resolved against cwd, same
    # gotcha scripts/launcher.py::main() already documents for itself.

    try:
        import playwright  # noqa: F401
    except ImportError:
        print("Playwright isn't installed. Run:\n  pip install -e \".[dev]\"\n  playwright install chromium", file=sys.stderr)
        sys.exit(1)

    run_dir = Path(tempfile.mkdtemp(prefix="pospay-screenshots-"))
    _configure_env(run_dir)

    server: subprocess.Popen | None = None
    try:
        _seed_demo_data()

        print(f"Starting the app on {BASE_URL} ...")
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "pospay.main:app", "--host", HOST, "--port", str(PORT), "--log-level", "warning"],
            cwd=PROJECT_ROOT,
            env=os.environ.copy(),
        )
        _wait_for_server()

        _capture_screenshots()
        print(f"\nDone — screenshots written to {SCREENSHOT_DIR}")
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
        shutil.rmtree(run_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
