# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from pospay.domain.account import Account
from pospay.repositories.base import CustomerScopedRepository


class AccountRepository(CustomerScopedRepository[Account]):
    model = Account
