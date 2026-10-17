import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.settings import settings
from app.schemas.product import RawProduct, UserSearchQuery
from app.services import discovery
from app.services.pipeline import DiscoveryPipeline


def test_discovery_searches_only_requested_marketplaces_and_filters_other_hosts(monkeypatch):
    monkeypatch.setattr(settings, "search_provider", "marketplace")
    # Explicit marketplace searches must still run despite historical scraper blocks.
    monkeypatch.setattr(discovery, "load_blocked_hosts", AsyncMock(return_value={"shopee.co.id", "tokopedia.com", "amazon.com"}))
    pool = discovery.DiscoveryWorkerPool()
    pool.search_candidate_urls = AsyncMock(return_value=[
        "https://www.amazon.com/dp/B123456789",
        "https://www.lazada.co.id/products/macbook.html",
        "https://amazon.com.evil.example/dp/B123456789",
        "https://www.alibaba.com/product-detail/macbook_123.html",
    ])

    async def extract(url, *args):
        return RawProduct(id=url, title="Macbook M5", price=1000, currency="USD", url=url, store_name="Store")

    pool.extract_product_data = AsyncMock(side_effect=extract)
    result = asyncio.run(pool.discover(UserSearchQuery(query="macbook m5", country="id")))
    queries = {call.args[0] for call in pool.search_candidate_urls.await_args_list}
    assert queries == {f"macbook m5 site:{site}" for site in ["shopee.co.id", "tokopedia.com", "alibaba.com", "amazon.com"]}
    assert {p.url for p in result} == {"https://www.amazon.com/dp/B123456789", "https://www.alibaba.com/product-detail/macbook_123.html"}
    assert pool.extract_product_data.await_count == 2


def test_pipeline_accepts_authorized_retailers_and_rejects_outside_stores(monkeypatch):
    monkeypatch.setattr(settings, "search_provider", "serpapi")
    monkeypatch.setattr(settings, "serpapi_api_key", "k")
    google_url = "https://www.google.com/search?ibp=oshop&prds=productid:1"

    async def serpapi(engine, q, gl, hl, **extra):
        if engine == "google_shopping":
            return {"shopping_results": [
                {"title": "Macbook M5", "price": "Rp 15.000.000", "link": "https://erafone.com/product/macbook"},
                {"title": "Macbook M5", "price": "Rp 15.000.000", "product_link": google_url,
                 "immersive_product_page_token": "token"},
                {"title": "Macbook M5", "price": "Rp 1.000.000", "link": "https://other.example/product/macbook"},
            ]}
        if engine == "google_immersive_product":
            return {"product_results": {"stores": [
                {"name": "Other", "link": "https://other.example/product/macbook", "price": "Rp 1.000.000"},
                {"name": "Digimap", "link": "https://digimap.co.id/products/macbook", "price": "Rp 16.000.000"},
            ]}}
        if "site:blibli.com" in q:
            return {"organic_results": [
                {"link": "https://www.blibli.com/p/macbook/1"},
                {"link": "https://blibli.com.evil.example/p/macbook/1"},
                {"link": "https://other.example/product/macbook"},
            ]}
        return {"organic_results": []}

    monkeypatch.setattr(discovery, "serpapi_get", serpapi)
    pool = discovery.DiscoveryWorkerPool()

    async def extract(url, *args):
        return RawProduct(id=url, title="Macbook M5", price=17000000, currency="IDR", url=url, store_name="Blibli")

    async def deduplicate(products, **kwargs):
        return products

    pool.extract_product_data = AsyncMock(side_effect=extract)
    pipeline = DiscoveryPipeline()
    pipeline.discovery_pool = pool
    pipeline.dedup_engine = SimpleNamespace(deduplicate=deduplicate)
    pipeline.trust_worker = SimpleNamespace(verify_batch=AsyncMock(return_value=[]))
    pipeline.recommender = SimpleNamespace(recommend=AsyncMock(return_value=[]))
    asyncio.run(pipeline.execute(UserSearchQuery(query="macbook m5", country="id", limit=3)))
    candidates = pipeline.trust_worker.verify_batch.await_args.args[0]
    assert {p.url for p in candidates} == {
        "https://erafone.com/product/macbook",
        "https://digimap.co.id/products/macbook",
        "https://www.blibli.com/p/macbook/1",
    }
