from pospay.domain.customer import Customer
from pospay.repositories.base import TenantScopedRepository


class CustomerRepository(TenantScopedRepository[Customer]):
    model = Customer
