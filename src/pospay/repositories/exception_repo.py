# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from pospay.domain.exception_item import ExceptionItem
from pospay.repositories.base import CustomerScopedRepository


class ExceptionRepository(CustomerScopedRepository[ExceptionItem]):
    model = ExceptionItem
