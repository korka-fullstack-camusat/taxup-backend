from fastapi import APIRouter
from app.api.v1 import auth, transactions, receipts, audits, dashboard, fraud, notifications, admin, admin_settings

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(transactions.router)
api_router.include_router(receipts.router)
api_router.include_router(audits.router)
api_router.include_router(dashboard.router)
api_router.include_router(fraud.router)
api_router.include_router(notifications.router)
api_router.include_router(admin.router)
api_router.include_router(admin_settings.router)
