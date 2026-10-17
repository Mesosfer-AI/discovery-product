from fastapi import APIRouter
from app.api.endpoints import discover, health

router = APIRouter(prefix="/api/v1", tags=["Discovery"])

router.include_router(health.router)
router.include_router(discover.router)
