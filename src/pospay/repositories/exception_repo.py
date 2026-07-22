from pospay.domain.exception_item import ExceptionItem
from pospay.repositories.base import TenantScopedRepository


class ExceptionRepository(TenantScopedRepository[ExceptionItem]):
    model = ExceptionItem
