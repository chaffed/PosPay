from fastapi import APIRouter

from pospay.web.routers.accounts import router as accounts_router
from pospay.web.routers.ach_authorizations import router as ach_authorizations_router
from pospay.web.routers.ach_transactions import router as ach_transactions_router
from pospay.web.routers.admin import router as admin_router
from pospay.web.routers.auth import router as auth_router
from pospay.web.routers.check_images import router as check_images_router
from pospay.web.routers.dashboard import router as dashboard_router
from pospay.web.routers.exceptions import router as exceptions_router
from pospay.web.routers.issued_items import router as issued_items_router
from pospay.web.routers.paid_items import router as paid_items_router
from pospay.web.routers.security_settings import router as security_settings_router
from pospay.web.routers.stop_payments import router as stop_payments_router

web_router = APIRouter()
web_router.include_router(auth_router)
web_router.include_router(dashboard_router)
web_router.include_router(security_settings_router)
web_router.include_router(accounts_router)
web_router.include_router(issued_items_router)
web_router.include_router(stop_payments_router)
web_router.include_router(paid_items_router)
web_router.include_router(check_images_router)
web_router.include_router(ach_authorizations_router)
web_router.include_router(ach_transactions_router)
web_router.include_router(exceptions_router)
web_router.include_router(admin_router)
