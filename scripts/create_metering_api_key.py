#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""Mints a new cross-tenant, read-only API key for the usage-metering endpoint
(GET /api/v1/platform/usage — see services/usage_metrics_service.py). There's no
platform-level admin UI in this app (every admin surface is tenant-scoped by design),
so minting a key — a rare, ops-only action — is a management script instead.

The raw key is printed exactly once, here. Only its hash is ever stored; if it's lost,
revoke it (services/platform_api_key_service.py::revoke) and run this again for a
replacement.

Usage:
    python scripts/create_metering_api_key.py "Acme Billing Integration"
"""

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    os.chdir(PROJECT_ROOT)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("name", help="A human label identifying who/what this key is for (e.g. 'Acme Billing Integration')")
    args = parser.parse_args()

    os.environ.setdefault("POSPAY_ENVIRONMENT", "production")

    from pospay.db.session import get_session_factory
    from pospay.services import platform_api_key_service

    session = get_session_factory()()
    try:
        row, raw_key = platform_api_key_service.generate_and_create(session, args.name)
        session.commit()
    finally:
        session.close()

    print(f"Created platform API key {row.id} ({args.name!r}).\n")
    print("Raw key (shown once — store it now, it cannot be retrieved again):\n")
    print(f"  {raw_key}\n")
    print("Use it as the X-Api-Key header against GET /api/v1/platform/usage.")


if __name__ == "__main__":
    sys.exit(main())
