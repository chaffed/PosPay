from pospay.domain.account import Account
from pospay.repositories.base import TenantScopedRepository


class AccountRepository(TenantScopedRepository[Account]):
    model = Account
