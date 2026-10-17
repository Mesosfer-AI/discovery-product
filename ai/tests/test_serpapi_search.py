import asyncio
import sys
from collections import Counter
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.settings import settings
from app.schemas.product import UserSearchQuery
from app.services import discovery, search
from app.services.discovery import DiscoveryWorkerPool, shopping_to_products

SHOPPING = {"shopping_results": [
    {"title": "Sony WH-1000XM5 Wireless Headphones", "price": "Rp 4.999.000", "extracted_price": 4999000,
     "source": "Tokopedia", "link": "https://www.tokopedia.com/shop/sony-wh-1000xm5",
     "thumbnail": "https://img/x.jpg", "rating": 4.8, "reviews": 120},
    {"title": "Sony WH-1000XM5 Case", "source": "Shop", "link": "https://shop.example/p/case"},  # no price
]}
WEB = {"organic_results": [{"link": "https://www.tokopedia.com/a/b"}, {"link": "/relative"}, {}]}


def test_shopping_mapping_and_gate() -> None:
    drops: Counter = Counter()
    products = shopping_to_products(SHOPPING, "sony wh-1000xm5", drops)
    assert len(products) == 1 and drops == {"no_price": 1}
    p = products[0]
    assert (p.price, p.currency, p.store_name, p.rating, p.review_count) == (4999000, "IDR", "Tokopedia", 4.8, 120)
    assert p.url.startswith("https://www.tokopedia.com/") and p.source == "google_shopping"


def test_web_urls() -> None:
    assert search.organic_urls(WEB) == ["https://www.tokopedia.com/a/b"]


def _pool(monkeypatch) -> tuple[DiscoveryWorkerPool, list]:
    pool = DiscoveryWorkerPool(concurrency=2)
    marketplace_calls: list[str] = []

    async def fake_marketplace(q: str, max_links: int = 25) -> list[str]:
        marketplace_calls.append(q)
        return []

    monkeypatch.setattr(pool, "search_candidate_urls", fake_marketplace)
    return pool, marketplace_calls


def test_serpapi_used_when_enabled(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_get(engine: str, q: str, gl: str, hl: str) -> dict:
        calls.append(engine)
        return SHOPPING if engine == "google_shopping" else {"organic_results": []}

    monkeypatch.setattr(settings, "search_provider", "serpapi")
    monkeypatch.setattr(settings, "serpapi_api_key", "k")
    monkeypatch.setattr(discovery, "serpapi_get", fake_get)
    pool, marketplace_calls = _pool(monkeypatch)
    out = asyncio.run(pool.discover(UserSearchQuery(query="sony wh-1000xm5", limit=3)))
    assert len(out) == 1 and not marketplace_calls and calls.count("google_shopping") == 1


def test_error_falls_back_to_marketplace(monkeypatch) -> None:
    async def boom(engine: str, q: str, gl: str, hl: str) -> dict:
        raise search.SerpApiError("google_shopping 429: quota")

    monkeypatch.setattr(settings, "search_provider", "serpapi")
    monkeypatch.setattr(settings, "serpapi_api_key", "k")
    monkeypatch.setattr(discovery, "serpapi_get", boom)
    pool, marketplace_calls = _pool(monkeypatch)
    asyncio.run(pool.discover(UserSearchQuery(query="sony wh-1000xm5", limit=3)))
    assert set(marketplace_calls) == {
        f"sony wh-1000xm5 site:{site}"
        for site in ["shopee.co.id", "tokopedia.com", "alibaba.com", "amazon.com"]
    }


def test_organic_error_preserves_shopping_products(monkeypatch) -> None:
    async def fake_get(engine: str, q: str, gl: str, hl: str) -> dict:
        if engine == "google_shopping":
            return SHOPPING
        raise search.SerpApiError("google 429: quota")

    monkeypatch.setattr(settings, "search_provider", "serpapi")
    monkeypatch.setattr(settings, "serpapi_api_key", "k")
    monkeypatch.setattr(discovery, "serpapi_get", fake_get)
    pool, marketplace_calls = _pool(monkeypatch)
    out = asyncio.run(pool.discover(UserSearchQuery(query="sony wh-1000xm5", limit=3)))
    assert [p.url for p in out] == ["https://www.tokopedia.com/shop/sony-wh-1000xm5"]
    assert not marketplace_calls


def test_shopping_error_preserves_successful_organic_source(monkeypatch) -> None:
    async def fake_get(engine: str, q: str, gl: str, hl: str) -> dict:
        if engine == "google_shopping" or "site:shopee.co.id" in q:
            raise search.SerpApiError(f"{engine} 429: quota")
        return WEB if "site:tokopedia.com" in q else {"organic_results": []}

    async def fake_extract(url: str, *args):
        assert url == "https://www.tokopedia.com/a/b"
        return shopping_to_products(SHOPPING, "sony wh-1000xm5")[0].model_copy(update={"url": url})

    monkeypatch.setattr(settings, "search_provider", "serpapi")
    monkeypatch.setattr(settings, "serpapi_api_key", "k")
    monkeypatch.setattr(discovery, "serpapi_get", fake_get)
    pool, marketplace_calls = _pool(monkeypatch)
    monkeypatch.setattr(pool, "extract_product_data", fake_extract)
    out = asyncio.run(pool.discover(UserSearchQuery(query="sony wh-1000xm5", limit=3)))
    assert [p.url for p in out] == ["https://www.tokopedia.com/a/b"]
    assert not marketplace_calls


def test_missing_key_uses_marketplace(monkeypatch) -> None:
    monkeypatch.setattr(settings, "search_provider", "serpapi")
    monkeypatch.setattr(settings, "serpapi_api_key", "")
    pool, marketplace_calls = _pool(monkeypatch)
    asyncio.run(pool.discover(UserSearchQuery(query="sony wh-1000xm5", limit=3)))
    assert marketplace_calls


def test_shopping_keeps_resolvable_google_links_and_rejects_other_merchants(monkeypatch) -> None:
    google_url = "https://www.google.com/search?ibp=oshop&prds=productid:1"
    items = [
        {"title": "Sony WH-1000XM5", "price": "$100", "product_link": google_url,
         "immersive_product_page_token": "token"},
        {"title": "Sony WH-1000XM5", "price": "$100", "link": "https://other.example/product/1"},
        {"title": "Sony WH-1000XM5", "price": "$100", "product_link": google_url + "2"},
    ]

    async def fake_get(engine: str, q: str, gl: str, hl: str) -> dict:
        return {"shopping_results": items} if engine == "google_shopping" else {"organic_results": []}

    monkeypatch.setattr(settings, "search_provider", "serpapi")
    monkeypatch.setattr(settings, "serpapi_api_key", "k")
    monkeypatch.setattr(discovery, "serpapi_get", fake_get)
    pool, _ = _pool(monkeypatch)
    out = asyncio.run(pool.discover(UserSearchQuery(query="sony wh-1000xm5", limit=3)))
    assert [p.url for p in out] == [google_url]


def test_marketplace_provider_skips_serpapi_even_with_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "search_provider", "marketplace")
    monkeypatch.setattr(settings, "serpapi_api_key", "configured-key")

    async def unexpected(*args, **kwargs):
        raise AssertionError("Direct marketplace search must not call SerpAPI")

    monkeypatch.setattr(discovery, "serpapi_get", unexpected)
    pool, marketplace_calls = _pool(monkeypatch)
    asyncio.run(pool.discover(UserSearchQuery(query="GPU RTX 3060", limit=3)))
    assert marketplace_calls


def _mock_http(monkeypatch, handler) -> None:
    real = httpx.AsyncClient
    monkeypatch.setattr(search.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(settings, "serpapi_api_key", "secret-key")


def test_serpapi_get_error_json_hides_key(monkeypatch) -> None:
    _mock_http(monkeypatch, lambda r: httpx.Response(200, json={"error": "Your account has run out of searches."}))
    try:
        asyncio.run(search.serpapi_get("google", "x", "us", "en"))
        raise AssertionError("expected SerpApiError")
    except search.SerpApiError as exc:
        assert str(exc) == "Search provider quota exhausted." and "secret-key" not in str(exc)


def test_serpapi_get_retries_once_on_5xx(monkeypatch) -> None:
    n = {"c": 0}

    def handler(r: httpx.Request) -> httpx.Response:
        n["c"] += 1
        return httpx.Response(503) if n["c"] == 1 else httpx.Response(200, json=WEB)

    _mock_http(monkeypatch, handler)
    assert asyncio.run(search.serpapi_get("google", "x", "us", "en")) == WEB and n["c"] == 2


@pytest.mark.parametrize("status", [200, 429])
def test_exhausted_quota_stops_before_browser_fallback(monkeypatch, status) -> None:
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": "Your account has run out of searches."})

    _mock_http(monkeypatch, handler)
    monkeypatch.setattr(settings, "search_provider", "serpapi")
    pool, marketplace_calls = _pool(monkeypatch)
    with pytest.raises(search.SerpApiError, match="Search provider quota exhausted"):
        asyncio.run(pool.discover(UserSearchQuery(query="macbook", country="id")))
    assert not marketplace_calls
    assert len(calls) == 1


def test_temporary_rate_limit_is_not_quota_exhaustion(monkeypatch) -> None:
    _mock_http(monkeypatch, lambda r: httpx.Response(429, json={"error": "Too many requests. Try again later."}))
    with pytest.raises(search.SerpApiError) as caught:
        asyncio.run(search.serpapi_get("google", "macbook", "id", "id"))
    assert type(caught.value) is search.SerpApiError


def test_quota_endpoint_returns_sanitized_402(monkeypatch) -> None:
    from unittest.mock import AsyncMock
    from app.main import app
    from app.services.pipeline import pipeline

    with monkeypatch.context() as upstream_patch:
        _mock_http(upstream_patch, lambda r: httpx.Response(429, json={"error": "Your account has run out of searches. secret-key"}))
        with pytest.raises(search.SerpApiError) as caught:
            asyncio.run(search.serpapi_get("google", "macbook", "id", "id"))

    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.post("/api/v1/discover", json={"query": "macbook"})

    monkeypatch.setattr(pipeline, "execute", AsyncMock(side_effect=caught.value))
    response = asyncio.run(request())
    assert response.status_code == 402
    assert response.json() == {"detail": "Search provider quota exhausted."}


def test_quota_cancels_inflight_sources_and_skips_queued_sources(monkeypatch) -> None:
    async def check():
        started, cancelled = [], []
        siblings_started = asyncio.Event()

        async def fake_get(engine, q, gl, hl):
            started.append(q)
            if engine == "google_shopping":
                await siblings_started.wait()
                raise search.SerpApiQuotaExhaustedError("Search provider quota exhausted.")
            if len(started) == 3:
                siblings_started.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.append(q)

        monkeypatch.setattr(settings, "search_provider", "serpapi")
        monkeypatch.setattr(settings, "serpapi_api_key", "configured-key")
        monkeypatch.setattr(settings, "discovery_search_concurrency", 3)
        monkeypatch.setattr(discovery, "serpapi_get", fake_get)
        pool, marketplace_calls = _pool(monkeypatch)
        with pytest.raises(search.SerpApiQuotaExhaustedError):
            await asyncio.wait_for(pool.discover(UserSearchQuery(query="macbook")), timeout=1)
        assert len(started) == 3
        assert len(cancelled) == 2
        assert not marketplace_calls

    asyncio.run(check())


def test_offer_resolution_propagates_quota(monkeypatch) -> None:
    async def exhausted(*args, **kwargs):
        raise search.SerpApiQuotaExhaustedError("Search provider quota exhausted.")

    monkeypatch.setattr(settings, "search_provider", "serpapi")
    monkeypatch.setattr(settings, "serpapi_api_key", "configured-key")
    monkeypatch.setattr(discovery, "serpapi_get", exhausted)
    products = shopping_to_products({"shopping_results": [{
        "title": "Macbook", "price": "$1000", "product_link": "https://www.google.com/search?product=1",
        "immersive_product_page_token": "token",
    }]}, "macbook")
    with pytest.raises(search.SerpApiQuotaExhaustedError):
        asyncio.run(discovery.resolve_store_links(products, "us", "en"))
