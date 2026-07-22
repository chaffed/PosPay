from pospay.domain.stop_payment import StopPayment
from pospay.repositories.base import TenantScopedRepository


class StopPaymentRepository(TenantScopedRepository[StopPayment]):
    model = StopPayment
