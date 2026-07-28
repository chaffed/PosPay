from pospay.domain.account import Account
from pospay.repositories.base import CustomerScopedRepository


class AccountRepository(CustomerScopedRepository[Account]):
    model = Account
