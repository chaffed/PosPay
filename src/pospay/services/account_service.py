import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from pospay.domain.account import Account, AchDebitBlockMode
from pospay.repositories.account_repo import AccountRepository


@dataclass(frozen=True, slots=True)
class AccountInput:
    account_number: str
    name: str


def create_account(session: Session, tenant_id: uuid.UUID, data: AccountInput) -> Account:
    repo = AccountRepository(session, tenant_id)
    account = Account(account_number=data.account_number, name=data.name)
    repo.add(account)
    session.flush()
    return account


def list_accounts(session: Session, tenant_id: uuid.UUID) -> list[Account]:
    return AccountRepository(session, tenant_id).list()


def set_ach_debit_block_mode(session: Session, tenant_id: uuid.UUID, account_id: uuid.UUID, mode: AchDebitBlockMode) -> Account | None:
    repo = AccountRepository(session, tenant_id)
    account = repo.get(account_id)
    if account is None:
        return None
    account.ach_debit_block_mode = mode
    session.flush()
    return account
