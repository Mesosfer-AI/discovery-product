import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlparse

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import discovery
from app.services.search import SearchBlockedError


@pytest.mark.parametrize("site,path,param,product", [
    ("shopee.co.id", "/search", "keyword", "https://shopee.co.id/Skates-i.123.456"),
    ("tokopedia.com", "/search", "q", "https://www.tokopedia.com/shop/sepatu-roda"),
    ("alibaba.com", "/trade/search", "SearchText", "https://www.alibaba.com/product-detail/skates_123.html"),
    ("amazon.com", "/s", "k", "https://www.amazon.com/Skates/dp/B123456789"),
])
def test_search_opens_marketplace_and_returns_only_its_product_links(monkeypatch, site, path, param, product):
    monkeypatch.setattr(discovery.cache_manager, "get_json", AsyncMock(return_value=None))
    monkeypatch.setattr(discovery.cache_manager, "set_json", AsyncMock())
    page = AsyncMock()
    page.set_default_timeout = lambda value: None
    page.goto.return_value = MagicMock(status=200)
    page.url = f"https://{site}{path}"
    page.title.return_value = "Search results"
    page.locator = MagicMock(return_value=MagicMock(inner_text=AsyncMock(return_value="Products")))
    page.eval_on_selector_all.return_value = [product, product, f"https://{site}/", "https://other.example/product/1", f"https://{site}.evil.example/dp/123",
                                             "https://ads.amazon.com/x/c/tracking/https://www.amazon.com/dp/B123456789"]
    context = AsyncMock()
    context.new_page.return_value = page
    pool = discovery.DiscoveryWorkerPool()
    pool.browser_manager = AsyncMock()
    pool.browser_manager.create_context.return_value = context

    expected = "https://www." + discovery.clean_url(product) if site == "amazon.com" else product
    assert asyncio.run(pool.search_candidate_urls(f"sepatu roda site:{site}")) == [expected]
    target = urlparse(page.goto.call_args.args[0])
    assert target.hostname.removeprefix("www.") == site
    assert target.path == path
    assert parse_qs(target.query)[param] == ["sepatu roda"]
    context.close.assert_awaited_once()


def test_blocked_marketplace_does_not_skip_other_marketplaces(monkeypatch):
    from app.config.settings import settings
    from app.schemas.product import RawProduct, UserSearchQuery
    monkeypatch.setattr(settings, "search_provider", "marketplace")
    product = "https://www.amazon.com/dp/B123456789"
    pool = discovery.DiscoveryWorkerPool()
    pool.search_candidate_urls = AsyncMock(side_effect=[SearchBlockedError(), SearchBlockedError(), SearchBlockedError(), [product]])
    pool.extract_product_data = AsyncMock(return_value=RawProduct(id="p", title="Sepatu roda", price=40, currency="USD", url=product, store_name="Amazon"))
    result = asyncio.run(pool.discover(UserSearchQuery(query="sepatu roda", country="id")))
    assert [p.url for p in result] == [product]
    assert pool.search_candidate_urls.await_count == 4


def test_marketplace_cache_skips_browser(monkeypatch):
    from app.services import discovery
    monkeypatch.setattr(discovery.cache_manager, "get_json", AsyncMock(return_value={"created_at": time.time(), "urls": ["https://www.amazon.com/dp/123"]}))
    pool = discovery.DiscoveryWorkerPool()
    pool.browser_manager = AsyncMock()
    assert asyncio.run(pool.search_candidate_urls("sepatu roda site:amazon.com")) == ["https://www.amazon.com/dp/123"]
    pool.browser_manager.create_context.assert_not_awaited()


def test_marketplace_waits_between_uncached_searches(monkeypatch):
    from app.services import discovery
    monkeypatch.setattr(discovery.cache_manager, "get_json", AsyncMock(return_value=None))
    monkeypatch.setattr(discovery.cache_manager, "set_json", AsyncMock())
    sleep = AsyncMock()
    monkeypatch.setattr(discovery.asyncio, "sleep", sleep)
    page = AsyncMock()
    page.set_default_timeout = lambda value: None
    page.goto.return_value = MagicMock(status=200)
    page.url = "https://www.amazon.com/s"
    page.title.return_value = "Results"
    page.locator = MagicMock(return_value=MagicMock(inner_text=AsyncMock(return_value="Products")))
    page.eval_on_selector_all.return_value = ["https://www.amazon.com/dp/123"]
    context = AsyncMock()
    context.new_page.return_value = page
    pool = discovery.DiscoveryWorkerPool()
    pool.browser_manager = AsyncMock()
    pool.browser_manager.create_context.return_value = context

    async def run():
        await pool.search_candidate_urls("roller skates site:amazon.com")
        await pool.search_candidate_urls("sepatu roda site:amazon.com")

    asyncio.run(run())
    sleep.assert_awaited_once()
    assert 2 < sleep.call_args.args[0] <= 3


def test_all_marketplaces_blocked_returns_an_error(monkeypatch):
    from app.config.settings import settings
    from app.schemas.product import UserSearchQuery
    monkeypatch.setattr(settings, "search_provider", "marketplace")
    pool = discovery.DiscoveryWorkerPool()
    pool.search_candidate_urls = AsyncMock(side_effect=SearchBlockedError("Blocked"))
    with pytest.raises(SearchBlockedError):
        asyncio.run(pool.discover(UserSearchQuery(query="sepatu roda", country="id")))
    assert pool.search_candidate_urls.await_count == 4


def test_blocked_search_endpoint_returns_429(monkeypatch):
    import httpx
    from app.main import app
    from app.services.pipeline import pipeline
    monkeypatch.setattr(pipeline, "execute", AsyncMock(side_effect=SearchBlockedError("private internal details")))

    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.post("/api/v1/discover", json={"query": "sepatu roda"})

    response = asyncio.run(request())
    assert response.status_code == 429
    assert "private internal details" not in response.text
