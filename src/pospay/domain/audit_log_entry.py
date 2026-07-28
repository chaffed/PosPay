# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from pospay.db.base import Base, new_uuid


class AuditChannel(str, enum.Enum):
    WEB = "web"
    API = "api"


class AuditLogEntry(Base):
    """One entry per state-changing action, taken through either the web UI or the JSON
    API (`channel`) — see services/audit_log_service.py. Entries form a hash chain: each
    row's `entry_hash` is an HMAC-SHA256 (server-held `audit_log_signing_secret`, distinct
    from every other signing secret in this app) over its own fields plus the previous
    entry's hash. That's what makes the log tamper-*evident* — editing, deleting, or
    reordering any entry breaks the chain from that point forward, detectable by
    recomputing it (verify_chain), not by trusting a stored flag. `occurred_at` is set in
    Python at call time rather than a DB server_default, because the hash must be
    computable — and the row's own id/timestamp already fixed — before insert."""

    __tablename__ = "audit_log_entry"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    channel: Mapped[AuditChannel] = mapped_column(Enum(AuditChannel, name="audit_channel", native_enum=False, length=10), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    prev_entry_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)
