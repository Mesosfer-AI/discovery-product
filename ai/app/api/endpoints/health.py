import time
from typing import Any
from fastapi import APIRouter
from app.config.settings import settings
from app.provider import BaseLLMProvider, get_provider
from app.services.redis_client import cache_manager

router = APIRouter()

_AVAILABILITY_TTL = 60.0
_provider: BaseLLMProvider | None = None
_availability: tuple[float, bool] | None = None  # (checked_at monotonic, reachable)


async def _provider_available() -> bool:
    """Provider reachability, cached so frequent healthchecks don't burn the shared RPM budget."""
    global _provider, _availability
    now = time.monotonic()
    if _availability is None or now - _availability[0] >= _AVAILABILITY_TTL:
        _provider = _provider or get_provider()
        _availability = (now, await _provider.is_available())
    return _availability[1]


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Health status check for Mesosfer Agentic Discovery services."""
    provider_ok = await _provider_available()
    redis_client = await cache_manager.get_client()

    return {
        "status": "healthy" if provider_ok else "degraded",
        "app_name": settings.app_name,
        "active_provider": settings.llm_provider,
        "provider_reachable": provider_ok,
        "redis_connected": bool(redis_client is not None),
    }
