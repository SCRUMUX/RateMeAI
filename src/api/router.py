from fastapi import APIRouter

from src.config import settings
from src.api.v1.analyze import router as analyze_router
from src.api.v1.pre_analyze import router as pre_analyze_router
from src.api.v1.tasks import router as tasks_router
from src.api.v1.share import router as share_router
from src.api.v1.users import router as users_router
from src.api.v1.payments import router as payments_router
from src.api.v1.engagement import router as engagement_router
from src.api.v1.catalog import router as catalog_router
from src.api.v1.sse import router as sse_router
from src.api.v1.internal import router as internal_router
from src.api.v1.consents import router as consents_router
from src.api.v1.users_data import router as users_data_router

api_router = APIRouter()
api_router.include_router(analyze_router, prefix="/analyze", tags=["analyze"])
api_router.include_router(
    pre_analyze_router, prefix="/pre-analyze", tags=["pre-analyze"]
)
api_router.include_router(tasks_router, prefix="/tasks", tags=["tasks"])
api_router.include_router(share_router, prefix="/share", tags=["share"])
api_router.include_router(users_router, tags=["users"])
api_router.include_router(consents_router, tags=["consents"])
api_router.include_router(users_data_router, tags=["privacy"])
api_router.include_router(payments_router, prefix="/payments", tags=["payments"])
api_router.include_router(engagement_router, prefix="/engagement", tags=["engagement"])
api_router.include_router(catalog_router, prefix="/catalog", tags=["catalog"])
api_router.include_router(sse_router, prefix="/sse", tags=["sse"])

if not settings.uses_remote_ai:
    api_router.include_router(internal_router, prefix="/internal", tags=["internal"])
