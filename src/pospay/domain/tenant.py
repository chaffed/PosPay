# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from pospay.db.base import Base, new_uuid


class Tenant(Base):
    __tablename__ = "tenant"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    require_dual_control: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # False only makes sense once at least one active bank-wide SsoConnection exists —
    # enforced in services/sso_service.py, not here, to keep this a plain column like
    # every other tenant-level toggle.
    password_login_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    stale_date_threshold_days: Mapped[int] = mapped_column(Integer, nullable=False, default=180)
    # Nullable = "use the app's global default" (config.Settings.jwt_access/refresh_
    # token_expire_minutes) — see auth/security.py::create_token and
    # services/tenant_service.py::set_session_timeouts. Doesn't affect the short-lived
    # mfa_pending token, which stays fixed regardless of tenant.
    access_token_expire_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    refresh_token_expire_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Same nullable-override pattern as the two above — None means "use
    # config.Settings.data_export_timeout_seconds" — see
    # services/data_export_service.py::run_export_job and
    # services/tenant_service.py::set_data_export_timeout.
    data_export_timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # At most one tenant ever has this set (enforced at the application level in
    # services/demo_tenant_service.py, not a DB constraint) — the persistent sales-demo
    # tenant. Gates the reactive reset-on-idle check in the login flow and the manual
    # "reset now" admin action; never affects any other tenant's behavior.
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Branding — local disk paths (see web/branding_storage.py), never the blob itself in
    # the row, same pattern as CheckImage.front_image_path. All nullable: unset means "use
    # the app's plain defaults" everywhere this is rendered.
    logo_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    logo_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    favicon_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    favicon_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    accent_color: Mapped[str | None] = mapped_column(String(7), nullable=True)

    # Contact info — shown in the page footer (templates/base.html), configured on
    # /ui/settings. All nullable/free-text, same shape (and same lack of format
    # validation) as Customer's own identical contact block — this is the bank's own
    # info, not a business client's. Unlike branding above, there's no "app default" to
    # fall back to: unset simply means the footer doesn't render at all (see
    # services/tenant_service.py::TenantBranding).
    support_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    support_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
