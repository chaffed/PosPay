import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy.orm import Session

from pospay.config import get_settings
from pospay.domain.audit_log_entry import AuditChannel, AuditLogEntry
from pospay.repositories.audit_log_repo import AuditLogRepository

_FIELD_SEPARATOR = "\x1f"  # ASCII unit separator — won't appear in any normal field value,
# so no combination of field values can be crafted to collide with a different field split.


def _normalize_datetime(dt: datetime) -> str:
    """SQLite drops tzinfo on reload (a freshly-created, still-in-session datetime comes
    back tz-aware; the same row read back in a later request comes back naive) — without
    normalizing, verify_chain would recompute a different hash for an untouched entry
    just because of *when* it re-read it, a false positive. Every datetime here is always
    UTC by construction, so a naive one is treated as already-UTC rather than guessed."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat()


def _canonical_fields(
    *,
    occurred_at: datetime,
    actor_user_id: uuid.UUID | None,
    channel: str,
    action: str,
    summary: str,
    resource_type: str,
    resource_id: uuid.UUID | None,
    metadata: dict[str, Any] | None,
    prev_entry_hash: str | None,
) -> bytes:
    """A stable, unambiguous serialization of everything that makes an entry what it is —
    used both when an entry is first signed and whenever it's re-verified later, so the
    two must always agree bit-for-bit on a legitimate, unmodified entry."""
    parts = [
        _normalize_datetime(occurred_at),
        str(actor_user_id) if actor_user_id else "",
        channel,
        action,
        summary,
        resource_type,
        str(resource_id) if resource_id else "",
        json.dumps(metadata, sort_keys=True) if metadata else "",
        prev_entry_hash or "",
    ]
    return _FIELD_SEPARATOR.join(parts).encode("utf-8")


def _sign(fields_bytes: bytes) -> str:
    secret = get_settings().audit_log_signing_secret.encode("utf-8")
    return hmac.new(secret, fields_bytes, hashlib.sha256).hexdigest()


@dataclass(frozen=True, slots=True)
class ChainVerificationResult:
    valid: bool
    checked_count: int
    broken_at_entry_id: uuid.UUID | None


def record_action(
    session: Session,
    tenant_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None,
    channel: Literal["web", "api"],
    action: str,
    summary: str,
    resource_type: str,
    resource_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLogEntry:
    """Called from route handlers (both web and API — see the sweep across
    web/routers/*.py and api/v1/*.py) right after the mutating service call succeeds and
    before the request's db.commit(), so the audit entry and the business change commit
    together atomically. `action` is a short dotted code chosen at the call site (e.g.
    "issued_item.void"), not derived from a table name, so the log reads as a narrative
    rather than a raw row diff."""
    repo = AuditLogRepository(session, tenant_id)
    prev = repo.latest()
    prev_hash = prev.entry_hash if prev else None
    occurred_at = datetime.now(timezone.utc)

    fields_bytes = _canonical_fields(
        occurred_at=occurred_at,
        actor_user_id=actor_user_id,
        channel=channel,
        action=action,
        summary=summary,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=metadata,
        prev_entry_hash=prev_hash,
    )

    entry = AuditLogEntry(
        tenant_id=tenant_id,
        occurred_at=occurred_at,
        actor_user_id=actor_user_id,
        channel=AuditChannel(channel),
        action=action,
        summary=summary,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata_json=metadata,
        prev_entry_hash=prev_hash,
        entry_hash=_sign(fields_bytes),
    )
    repo.add(entry)
    session.flush()
    return entry


def list_entries(session: Session, tenant_id: uuid.UUID) -> list[AuditLogEntry]:
    return AuditLogRepository(session, tenant_id).list()


def verify_chain(session: Session, tenant_id: uuid.UUID) -> ChainVerificationResult:
    """Walks every entry for this tenant in the order the chain was built and recomputes
    each hash from scratch — proof nothing has been edited, deleted, or reordered since
    it was written, not just that the stored values are internally consistent."""
    entries = AuditLogRepository(session, tenant_id).list_in_chain_order()
    prev_hash: str | None = None
    for index, entry in enumerate(entries):
        if entry.prev_entry_hash != prev_hash:
            return ChainVerificationResult(valid=False, checked_count=index, broken_at_entry_id=entry.id)

        fields_bytes = _canonical_fields(
            occurred_at=entry.occurred_at,
            actor_user_id=entry.actor_user_id,
            channel=entry.channel.value,
            action=entry.action,
            summary=entry.summary,
            resource_type=entry.resource_type,
            resource_id=entry.resource_id,
            metadata=entry.metadata_json,
            prev_entry_hash=entry.prev_entry_hash,
        )
        if _sign(fields_bytes) != entry.entry_hash:
            return ChainVerificationResult(valid=False, checked_count=index, broken_at_entry_id=entry.id)

        prev_hash = entry.entry_hash

    return ChainVerificationResult(valid=True, checked_count=len(entries), broken_at_entry_id=None)
