import uuid

from sqlalchemy.orm import Session

from pospay.domain.exception_item import ExceptionItem, ExceptionStatus
from pospay.repositories.exception_repo import ExceptionRepository


def list_exceptions(
    session: Session,
    tenant_id: uuid.UUID,
    *,
    network_code: str | None = None,
    status: ExceptionStatus | None = None,
) -> list[ExceptionItem]:
    repo = ExceptionRepository(session, tenant_id)
    return repo.list(network_code=network_code, status=status)


def get_exception(session: Session, tenant_id: uuid.UUID, exception_id: uuid.UUID) -> ExceptionItem | None:
    repo = ExceptionRepository(session, tenant_id)
    return repo.get(exception_id)
