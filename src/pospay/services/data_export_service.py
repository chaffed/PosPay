# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import enum
import json
import uuid
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pospay.domain.customer import Customer
from pospay.domain.data_export_job import DataExportJob, DataExportJobStatus
from pospay.domain.tenant import Tenant
from pospay.repositories.ach_authorization_repo import AchAuthorizationRepository
from pospay.repositories.ach_transaction_repo import AchTransactionRepository
from pospay.repositories.account_repo import AccountRepository
from pospay.repositories.audit_log_repo import AuditLogRepository
from pospay.repositories.bulk_upload_file_repo import BulkUploadFileRepository
from pospay.repositories.check_image_repo import CheckImageRepository
from pospay.repositories.customer_repo import CustomerRepository
from pospay.repositories.decision_repo import DecisionRepository
from pospay.repositories.exception_repo import ExceptionRepository
from pospay.repositories.issued_item_repo import IssuedItemRepository
from pospay.repositories.paid_item_repo import PaidItemRepository
from pospay.repositories.sso_connection_repo import SsoConnectionRepository
from pospay.repositories.sso_group_mapping_repo import SsoGroupMappingRepository
from pospay.repositories.stop_payment_repo import StopPaymentRepository
from pospay.repositories.tenant_membership_repo import TenantMembershipRepository
from pospay.repositories.user_repo import UserRepository
from pospay.services import data_export_storage, security_group_service

# The only two genuinely secret columns in the schema — never included in an export,
# regardless of which entity they appear on. Everything else here is either already
# non-sensitive or (like a bcrypt hash) simply useless to a new platform anyway.
_SECRET_COLUMNS = {"hashed_password", "client_secret_encrypted"}


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Generic SQLAlchemy row -> JSON-safe dict, stripping _SECRET_COLUMNS. Shared by
    every exporter below that doesn't need custom field composition, so no exporter has
    to hand-map its own columns."""
    result: dict[str, Any] = {}
    for column in row.__table__.columns:
        if column.name in _SECRET_COLUMNS:
            continue
        value = getattr(row, column.name)
        if isinstance(value, uuid.UUID):
            value = str(value)
        elif isinstance(value, enum.Enum):
            value = value.value
        elif isinstance(value, Decimal):
            value = str(value)
        elif isinstance(value, (datetime, date)):
            value = value.isoformat()
        result[column.name] = value
    return result


def _check_image_rows(session: Session, tenant_id: uuid.UUID, customer_id: uuid.UUID | None) -> list:
    return CheckImageRepository(session, tenant_id, customer_id).list()


def _decision_rows(session: Session, tenant_id: uuid.UUID, customer_id: uuid.UUID | None) -> list:
    decisions = DecisionRepository(session, tenant_id).list()
    if customer_id is None:
        return decisions
    exception_ids = {e.id for e in ExceptionRepository(session, tenant_id, customer_id).list()}
    return [d for d in decisions if d.exception_item_id in exception_ids]


def _users_dicts(session: Session, tenant_id: uuid.UUID, customer_id: uuid.UUID | None) -> list[dict]:
    """Custom composition, not _row_to_dict: pulls in the user's email and the
    membership's resolved security group NAME (never the whole security_group table for
    a customer-scoped export — see the plan's scoping table) — and never the password
    hash, which isn't even a column on TenantMembership to begin with."""
    memberships = TenantMembershipRepository(session, tenant_id).list(customer_id=customer_id)
    user_repo = UserRepository(session)
    out = []
    for membership in memberships:
        user = user_repo.get(membership.user_id)
        group = security_group_service.get_security_group(session, tenant_id, membership.security_group_id)
        out.append(
            {
                "membership_id": str(membership.id),
                "email": user.email if user else None,
                "is_active": membership.is_active,
                "security_group_name": group.name if group else None,
                "customer_id": str(membership.customer_id) if membership.customer_id else None,
                "created_at": membership.created_at.isoformat(),
            }
        )
    return out


def _sso_group_mapping_dicts(session: Session, tenant_id: uuid.UUID, customer_id: uuid.UUID | None) -> list[dict]:
    connections = SsoConnectionRepository(session, tenant_id).list(customer_id=customer_id)
    connection_ids = {c.id for c in connections}
    mappings = SsoGroupMappingRepository(session, tenant_id).list()
    return [_row_to_dict(m) for m in mappings if m.connection_id in connection_ids]


# Included in both tenant-wide and customer-scoped exports.
_SCOPED_EXPORTERS: list[tuple[str, Any]] = [
    ("accounts", lambda s, t, c: [_row_to_dict(r) for r in AccountRepository(s, t, c).list()]),
    ("issued_items", lambda s, t, c: [_row_to_dict(r) for r in IssuedItemRepository(s, t, c).list()]),
    ("stop_payments", lambda s, t, c: [_row_to_dict(r) for r in StopPaymentRepository(s, t, c).list()]),
    ("paid_items", lambda s, t, c: [_row_to_dict(r) for r in PaidItemRepository(s, t, c).list()]),
    ("ach_authorizations", lambda s, t, c: [_row_to_dict(r) for r in AchAuthorizationRepository(s, t, c).list()]),
    ("ach_transactions", lambda s, t, c: [_row_to_dict(r) for r in AchTransactionRepository(s, t, c).list()]),
    ("exceptions", lambda s, t, c: [_row_to_dict(r) for r in ExceptionRepository(s, t, c).list()]),
    ("decisions", lambda s, t, c: [_row_to_dict(r) for r in _decision_rows(s, t, c)]),
    ("check_images", lambda s, t, c: [_row_to_dict(r) for r in _check_image_rows(s, t, c)]),
    ("users", _users_dicts),
    ("sso_connections", lambda s, t, c: [_row_to_dict(r) for r in SsoConnectionRepository(s, t).list(customer_id=c)]),
    ("sso_group_mappings", _sso_group_mapping_dicts),
]

# Tenant-wide exports only — see the plan's scoping table for why each is excluded from
# a customer-scoped export (not cleanly attributable to one customer, or would leak the
# tenant's own configuration/action history to a single customer's admin).
_TENANT_WIDE_ONLY_EXPORTERS: list[tuple[str, Any]] = [
    ("customers", lambda s, t, c: [_row_to_dict(r) for r in CustomerRepository(s, t).list()]),
    ("bulk_upload_files", lambda s, t, c: [_row_to_dict(r) for r in BulkUploadFileRepository(s, t).list()]),
    ("audit_log", lambda s, t, c: [_row_to_dict(r) for r in AuditLogRepository(s, t).list()]),
]


def request_export(
    session: Session, tenant_id: uuid.UUID, requested_by_user_id: uuid.UUID, customer_id: uuid.UUID | None = None
) -> DataExportJob:
    job = DataExportJob(
        tenant_id=tenant_id, customer_id=customer_id, requested_by_user_id=requested_by_user_id,
        status=DataExportJobStatus.PENDING,
    )
    session.add(job)
    session.flush()
    return job


def _apply_rls_tenant(session: Session, tenant_id: uuid.UUID) -> None:
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SET LOCAL app.current_tenant_id = :tid"), {"tid": str(tenant_id)})


def _add_file_if_exists(zf: zipfile.ZipFile, source_path: str | None, archive_name: str) -> None:
    if not source_path:
        return
    path = Path(source_path)
    if path.exists():
        zf.write(path, archive_name)


def _build_archive(session: Session, tenant_id: uuid.UUID, customer_id: uuid.UUID | None, destination: Path) -> None:
    exporters = list(_SCOPED_EXPORTERS)
    if customer_id is None:
        exporters += _TENANT_WIDE_ONLY_EXPORTERS

    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, fn in exporters:
            rows = fn(session, tenant_id, customer_id)
            zf.writestr(f"data/{name}.json", json.dumps(rows, indent=2))

        for check_image in _check_image_rows(session, tenant_id, customer_id):
            if check_image.front_image_path:
                _add_file_if_exists(zf, check_image.front_image_path, f"files/check_images/{Path(check_image.front_image_path).name}")
            if check_image.back_image_path:
                _add_file_if_exists(zf, check_image.back_image_path, f"files/check_images/{Path(check_image.back_image_path).name}")

        if customer_id is None:
            for upload in BulkUploadFileRepository(session, tenant_id).list():
                _add_file_if_exists(zf, upload.storage_path, f"files/bulk_uploads/{Path(upload.storage_path).name}")

            tenant = session.get(Tenant, tenant_id)
            zf.writestr("data/tenant.json", json.dumps(_row_to_dict(tenant), indent=2))
            if tenant.logo_path:
                _add_file_if_exists(zf, tenant.logo_path, f"files/branding/{Path(tenant.logo_path).name}")
            if tenant.favicon_path:
                _add_file_if_exists(zf, tenant.favicon_path, f"files/branding/{Path(tenant.favicon_path).name}")
        else:
            customer = session.get(Customer, customer_id)
            zf.writestr("data/customer.json", json.dumps(_row_to_dict(customer), indent=2))


def run_export_job(engine: Engine, job_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    """Runs from a FastAPI BackgroundTask (see web/routers/data_export.py) — opens its
    own Session bound to the request's engine, same pattern as
    networks/check/ocr_processing.py's own background-task entry point, since the
    request's own session is closed by the time this runs. Never lets an exception escape
    unhandled: any failure marks the job FAILED with a message, rather than silently
    leaving it stuck at RUNNING forever."""
    session = Session(bind=engine)
    try:
        _apply_rls_tenant(session, tenant_id)
        job = session.get(DataExportJob, job_id)
        if job is None:
            return
        job.status = DataExportJobStatus.RUNNING
        session.commit()
        _apply_rls_tenant(session, tenant_id)  # commit resets the transaction-local setting

        destination = data_export_storage.export_archive_path(tenant_id, job_id)
        try:
            _build_archive(session, tenant_id, job.customer_id, destination)
        except Exception as exc:  # noqa: BLE001 — must never crash the background task
            job.status = DataExportJobStatus.FAILED
            job.error_message = str(exc)[:1000]
            job.completed_at = datetime.now(timezone.utc)
            session.commit()
            return

        job.status = DataExportJobStatus.COMPLETED
        job.archive_path = str(destination)
        job.size_bytes = destination.stat().st_size
        job.completed_at = datetime.now(timezone.utc)
        session.commit()
    finally:
        session.close()
