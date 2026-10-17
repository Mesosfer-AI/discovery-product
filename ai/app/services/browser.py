import asyncio
import json
import logging
import re
from typing import Any
import httpx
from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from app.config.settings import settings

logger = logging.getLogger(__name__)


class BrowserManager:
    """Manages browser lifecycle with support for Obscura (CDP) and Headless Chromium."""

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._lock = asyncio.Lock()
        self.obscura_url = "http://127.0.0.1:9222"

    async def _is_obscura_running(self) -> bool:
        """Check if local Obscura daemon is reachable via HTTP."""
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                res = await client.get(f"{self.obscura_url}/json/version")
                return res.status_code == 200
        except Exception as exc:
            logger.debug("Obscura not reachable at %s: %r", self.obscura_url, exc)
            return False

    async def get_browser(self) -> Browser:
        """Get or initialize singleton browser instance (Obscura or Chromium)."""
        async with self._lock:
            if self._browser is None or not self._browser.is_connected():
                if self._playwright is None:
                    self._playwright = await async_playwright().start()

                # Check if Obscura daemon is active
                if await self._is_obscura_running():
                    try:
                        self._browser = await self._playwright.chromium.connect_over_cdp(self.obscura_url)
                        return self._browser
                    except Exception as exc:
                        logger.debug("Obscura CDP connect failed, falling back to Chromium: %r", exc)

                # Fallback to local headless Chromium
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
                )
            return self._browser

    async def create_context(self) -> BrowserContext:
        """Spawn an isolated context for a discovery worker."""
        browser = await self.get_browser()
        return await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )

    async def close(self) -> None:
        """Shutdown browser and Playwright process."""
        async with self._lock:
            if self._browser and self._browser.is_connected():
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None


browser_manager = BrowserManager()
