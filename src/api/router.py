from fastapi import APIRouter

from src.api.v1.analyze import router as analyze_router
from src.api.v1.tasks import router as tasks_router
from src.api.v1.share import router as share_router
from src.api.v1.users import router as users_router
from src.api.v1.payments import router as payments_router
from src.api.v1.engagement import router as engagement_router

api_router = APIRouter()
api_router.include_router(analyze_router, prefix="/analyze", tags=["analyze"])
api_router.include_router(tasks_router, prefix="/tasks", tags=["tasks"])
api_router.include_router(share_router, prefix="/share", tags=["share"])
api_router.include_router(users_router, tags=["users"])
api_router.include_router(payments_router, prefix="/payments", tags=["payments"])
api_router.include_router(engagement_router, prefix="/engagement", tags=["engagement"])
