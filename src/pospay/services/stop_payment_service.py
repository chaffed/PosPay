import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from pospay.domain.stop_payment import StopPayment, StopPaymentStatus
from pospay.repositories.stop_payment_repo import StopPaymentRepository


@dataclass(frozen=True, slots=True)
class StopPaymentInput:
    account_id: uuid.UUID
    check_number: str
    amount: Decimal | None
    effective_date: date
    expiration_date: date | None
    reason: str | None


def create_stop_payment(
    session: Session, tenant_id: uuid.UUID, data: StopPaymentInput, *, created_by_user_id: uuid.UUID | None
) -> StopPayment:
    repo = StopPaymentRepository(session, tenant_id)
    stop = StopPayment(
        account_id=data.account_id,
        check_number=data.check_number,
        amount=data.amount,
        effective_date=data.effective_date,
        expiration_date=data.expiration_date,
        reason=data.reason,
        created_by_user_id=created_by_user_id,
    )
    repo.add(stop)
    session.flush()
    return stop


def cancel_stop_payment(session: Session, tenant_id: uuid.UUID, stop_id: uuid.UUID) -> StopPayment | None:
    repo = StopPaymentRepository(session, tenant_id)
    stop = repo.get(stop_id)
    if stop is None:
        return None
    stop.status = StopPaymentStatus.CANCELLED
    session.flush()
    return stop


def list_stop_payments(
    session: Session, tenant_id: uuid.UUID, *, status: StopPaymentStatus | None = None
) -> list[StopPayment]:
    repo = StopPaymentRepository(session, tenant_id)
    return repo.list(status=status)
