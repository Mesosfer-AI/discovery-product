import logging
from typing import Any

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

_SERPAPI_URL = "https://serpapi.com/search.json"


class SerpApiError(Exception):
    """SerpAPI call failed (HTTP error, quota, or an "error" field in the JSON). Never contains the key."""


class SearchUnavailableError(Exception):
    """Browser search failed before it could return usable results."""


class SearchBlockedError(SearchUnavailableError):
    """Search returned a rate limit or CAPTCHA; do not retry automatically."""


def serpapi_enabled() -> bool:
    if settings.search_provider.lower() != "serpapi":
        return False
    if not settings.serpapi_api_key:
        logger.warning("SEARCH_PROVIDER=serpapi but SERPAPI_API_KEY is empty; falling back to direct marketplace search")
        return False
    return True


async def serpapi_get(engine: str, q: str, gl: str, hl: str, **extra: str) -> dict[str, Any]:
    """One SerpAPI search over HTTPS; one retry on 5xx/timeout, no retry on 4xx (quota/auth)."""
    params = {"engine": engine, "api_key": settings.serpapi_api_key, "gl": gl, "hl": hl, **extra}
    if q:
        params["q"] = q
    last = ""
    for _ in range(2):  # ponytail: single retry; add backoff if SerpAPI 5xx becomes common.
        try:
            async with httpx.AsyncClient(timeout=settings.serpapi_timeout) as client:
                resp = await client.get(_SERPAPI_URL, params=params)
        except httpx.TimeoutException:
            last = "timeout"
            continue
        except httpx.HTTPError as exc:
            # Class name only: httpx messages can embed the request URL (which carries the key).
            raise SerpApiError(f"{engine} request failed: {type(exc).__name__}") from None
        if resp.status_code >= 500:
            last = f"HTTP {resp.status_code}"
            continue
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code >= 400 or data.get("error"):
            # SerpAPI also reports errors with HTTP 200 (e.g. "Google hasn't returned any results").
            raise SerpApiError(f"{engine} {resp.status_code}: {str(data.get('error', 'unknown error'))[:150]}")
        return data
    raise SerpApiError(f"{engine} failed after retry: {last}")


def organic_urls(data: dict[str, Any]) -> list[str]:
    return [r["link"] for r in data.get("organic_results", []) if str(r.get("link", "")).startswith("http")]
