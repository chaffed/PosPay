from pospay.domain.ach_transaction import AchTransaction
from pospay.repositories.base import TenantScopedRepository


class AchTransactionRepository(TenantScopedRepository[AchTransaction]):
    model = AchTransaction
