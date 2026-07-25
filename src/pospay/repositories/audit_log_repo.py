from pospay.domain.audit_log_entry import AuditLogEntry
from pospay.repositories.base import TenantScopedRepository


class AuditLogRepository(TenantScopedRepository[AuditLogEntry]):
    model = AuditLogEntry

    def list_in_chain_order(self) -> list[AuditLogEntry]:
        """Oldest first — the order the hash chain was built in, needed to walk and
        re-verify it. list()/the UI's newest-first view is a display concern, not this."""
        stmt = self.query().order_by(AuditLogEntry.occurred_at.asc())
        return list(self.session.execute(stmt).scalars().all())

    def latest(self) -> AuditLogEntry | None:
        stmt = self.query().order_by(AuditLogEntry.occurred_at.desc()).limit(1)
        return self.session.execute(stmt).scalar_one_or_none()
