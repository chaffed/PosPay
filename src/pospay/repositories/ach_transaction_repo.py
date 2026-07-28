from pospay.domain.ach_transaction import AchTransaction
from pospay.repositories.base import CustomerScopedRepository


class AchTransactionRepository(CustomerScopedRepository[AchTransaction]):
    model = AchTransaction
