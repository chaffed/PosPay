import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pospay.db.base import Base, new_uuid


class AchDebitBlockMode(str, enum.Enum):
    # A genuine kill-switch: every ACH debit is rejected, even one that would otherwise
    # match an active authorization rule. Mirrors real "ACH debit block" products — an
    # account that expects zero ACH debits ever, full stop.
    BLOCK_ALL = "block_all"
    # The normal positive-pay posture ("ACH debit filter"): debits are evaluated against
    # authorization rules (originator whitelist, amount/frequency/SEC-code limits).
    FILTER_BY_AUTHORIZATION = "filter_by_authorization"


class Account(Base):
    __tablename__ = "account"
    __table_args__ = (UniqueConstraint("tenant_id", "account_number", name="uq_account_tenant_number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), nullable=False, index=True)
    account_number: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ach_debit_block_mode: Mapped[AchDebitBlockMode] = mapped_column(
        Enum(AchDebitBlockMode, name="ach_debit_block_mode", native_enum=False, length=32),
        nullable=False,
        default=AchDebitBlockMode.FILTER_BY_AUTHORIZATION,
    )
