from pospay.domain.issued_item import IssuedItem
from pospay.repositories.base import TenantScopedRepository


class IssuedItemRepository(TenantScopedRepository[IssuedItem]):
    model = IssuedItem
