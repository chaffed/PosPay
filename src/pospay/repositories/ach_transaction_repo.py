# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from pospay.domain.ach_transaction import AchTransaction
from pospay.repositories.base import CustomerScopedRepository


class AchTransactionRepository(CustomerScopedRepository[AchTransaction]):
    model = AchTransaction
