from pospay.domain.issued_item import IssuedItem
from pospay.repositories.base import CustomerScopedRepository


class IssuedItemRepository(CustomerScopedRepository[IssuedItem]):
    model = IssuedItem
