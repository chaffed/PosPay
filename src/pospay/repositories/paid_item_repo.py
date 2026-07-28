# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from pospay.domain.paid_item import PaidItem
from pospay.repositories.base import CustomerScopedRepository


class PaidItemRepository(CustomerScopedRepository[PaidItem]):
    model = PaidItem
