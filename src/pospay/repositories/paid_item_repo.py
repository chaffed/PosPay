from pospay.domain.paid_item import PaidItem
from pospay.repositories.base import TenantScopedRepository


class PaidItemRepository(TenantScopedRepository[PaidItem]):
    model = PaidItem
