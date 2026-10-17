import asyncio
import logging
import sys

# ponytail: Playwright requires WindowsProactorEventLoopPolicy on Windows for subprocess transport.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager
from typing import AsyncIterator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.config.settings import settings
from app.services.browser import browser_manager
from app.services.redis_client import cache_manager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup
    yield
    # Shutdown: Clean up background browser & redis connection
    await browser_manager.close()
    await cache_manager.close()


logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)
# Security: httpx logs full request URLs at INFO, and SerpAPI puts api_key in the query string.
for _noisy in ("httpx", "httpcore"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

app = FastAPI(
    title=settings.app_name,
    description="Autonomous Multi-Agent Global Product Discovery & Trust Recommendation Engine for AMD Hackathon.",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for frontend and external services
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "project": settings.app_name,
        "status": "online",
        "docs_url": "/docs",
    }
