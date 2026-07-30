# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from fastapi import APIRouter

from pospay.web.routers.accounts import router as accounts_router
from pospay.web.routers.ach_authorizations import router as ach_authorizations_router
from pospay.web.routers.ach_return_reasons import router as ach_return_reasons_router
from pospay.web.routers.ach_transactions import router as ach_transactions_router
from pospay.web.routers.admin import router as admin_router
from pospay.web.routers.audit_log import router as audit_log_router
from pospay.web.routers.auth import router as auth_router
from pospay.web.routers.branding import router as branding_router
from pospay.web.routers.bulk_uploads import router as bulk_uploads_router
from pospay.web.routers.check_images import router as check_images_router
from pospay.web.routers.customers import router as customers_router
from pospay.web.routers.dashboard import router as dashboard_router
from pospay.web.routers.data_export import router as data_export_router
from pospay.web.routers.exceptions import router as exceptions_router
from pospay.web.routers.issued_items import router as issued_items_router
from pospay.web.routers.paid_items import router as paid_items_router
from pospay.web.routers.security_groups import router as security_groups_router
from pospay.web.routers.security_settings import router as security_settings_router
from pospay.web.routers.sso_settings import router as sso_settings_router
from pospay.web.routers.stop_payments import router as stop_payments_router
from pospay.web.routers.tenant_settings import router as tenant_settings_router
from pospay.web.routers.tenant_switch import router as tenant_switch_router
from pospay.web.routers.users import router as users_router
from pospay.web.routers.wizard import router as wizard_router
from pospay.web.routers.wsud import router as wsud_router

web_router = APIRouter()
web_router.include_router(branding_router)
web_router.include_router(auth_router)
web_router.include_router(dashboard_router)
web_router.include_router(security_settings_router)
web_router.include_router(tenant_switch_router)
web_router.include_router(tenant_settings_router)
web_router.include_router(accounts_router)
web_router.include_router(customers_router)
web_router.include_router(issued_items_router)
web_router.include_router(stop_payments_router)
web_router.include_router(paid_items_router)
web_router.include_router(check_images_router)
web_router.include_router(ach_authorizations_router)
web_router.include_router(ach_transactions_router)
web_router.include_router(ach_return_reasons_router)
web_router.include_router(exceptions_router)
web_router.include_router(admin_router)
web_router.include_router(users_router)
web_router.include_router(security_groups_router)
web_router.include_router(bulk_uploads_router)
web_router.include_router(audit_log_router)
web_router.include_router(sso_settings_router)
web_router.include_router(data_export_router)
web_router.include_router(wizard_router)
web_router.include_router(wsud_router)
