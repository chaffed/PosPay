# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from pospay.domain.stop_payment import StopPayment
from pospay.repositories.base import CustomerScopedRepository


class StopPaymentRepository(CustomerScopedRepository[StopPayment]):
    model = StopPayment
