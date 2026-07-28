from pospay.domain.stop_payment import StopPayment
from pospay.repositories.base import CustomerScopedRepository


class StopPaymentRepository(CustomerScopedRepository[StopPayment]):
    model = StopPayment
