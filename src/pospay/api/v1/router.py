# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from fastapi import APIRouter

from pospay.api.v1.ach_authorizations import router as ach_authorizations_router
from pospay.api.v1.ach_transactions import router as ach_transactions_router
from pospay.api.v1.admin import router as admin_router
from pospay.api.v1.auth import router as auth_router
from pospay.api.v1.check_images import router as check_images_router
from pospay.api.v1.decisions import router as decisions_router
from pospay.api.v1.dropbox_import import router as dropbox_import_router
from pospay.api.v1.exceptions import router as exceptions_router
from pospay.api.v1.issued_items import router as issued_items_router
from pospay.api.v1.paid_items import router as paid_items_router
from pospay.api.v1.stop_payments import router as stop_payments_router
from pospay.api.v1.users import router as users_router
from pospay.api.v1.webauthn import router as webauthn_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(webauthn_router)
api_router.include_router(issued_items_router)
api_router.include_router(stop_payments_router)
api_router.include_router(paid_items_router)
api_router.include_router(check_images_router)
api_router.include_router(ach_authorizations_router)
api_router.include_router(ach_transactions_router)
api_router.include_router(exceptions_router)
api_router.include_router(decisions_router)
api_router.include_router(admin_router)
api_router.include_router(users_router)
api_router.include_router(dropbox_import_router)
