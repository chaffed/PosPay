# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from pospay.networks.ach.adapter import AchAdapter
from pospay.networks.registry import register_adapter

register_adapter(AchAdapter())
