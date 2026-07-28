from pospay.domain.paid_item import PaidItem
from pospay.repositories.base import CustomerScopedRepository


class PaidItemRepository(CustomerScopedRepository[PaidItem]):
    model = PaidItem
