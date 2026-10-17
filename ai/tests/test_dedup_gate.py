import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import AsyncMock, MagicMock

from app.schemas.product import RawProduct
from app.services.dedup import clean_url, deduplication_engine
from app.services.discovery import DiscoveryWorkerPool


def _p(title: str, url: str, store: str = "Shop") -> RawProduct:
    return RawProduct(id=url + title, title=title, price=10, url=url, store_name=store)


def _dedup(items: list[RawProduct]) -> list[RawProduct]:
    return asyncio.run(deduplication_engine.deduplicate(items, session_id="same-query"))


def test_google_product_links_do_not_collapse() -> None:
    items = [
        _p("iPhone 15 128GB Black", "https://www.google.com/search?q=iphone&prds=pid:1&udm=28", "A"),
        _p("iPhone 15 Pro 256GB", "https://www.google.com/search?q=iphone&prds=pid:2&udm=28", "B"),
        _p("iPhone 14 128GB", "https://www.google.com/shopping/product/333?gl=us", "C"),
    ]
    assert len(_dedup(items)) == 3


def test_same_store_same_title_collapses_different_store_does_not() -> None:
    a = _p("Sony WH-1000XM5", "https://a.com/x", "A")
    assert len(_dedup([a, _p("sony wh-1000xm5", "https://a.com/y", "A")])) == 1
    assert len(_dedup([a, _p("Sony WH-1000XM5", "https://b.com/x", "B")])) == 2


def test_tracking_params_stripped() -> None:
    base = "https://www.google.com/shopping/product/9?gl=us"
    assert clean_url(base + "&utm_source=x&gclid=1&fbclid=2&srsltid=3") == clean_url(base)
    assert clean_url("https://a.com/p?utm_source=x") == "a.com/p"


def test_second_identical_request_keeps_items() -> None:
    items = [_p("Thing One", "https://a.com/1"), _p("Thing Two", "https://a.com/2")]
    assert len(_dedup(items)) == 2
    assert len(_dedup(items)) == 2


def _pool_with_page(info: dict) -> DiscoveryWorkerPool:
    page = MagicMock()
    page.goto, page.wait_for_function, page.close = AsyncMock(), AsyncMock(), AsyncMock()
    page.evaluate = AsyncMock(return_value=info)
    ctx = MagicMock()
    ctx.new_page, ctx.close = AsyncMock(return_value=page), AsyncMock()
    pool = DiscoveryWorkerPool(concurrency=1)
    pool.browser_manager = MagicMock()
    pool.browser_manager.create_context = AsyncMock(return_value=ctx)
    return pool


_INFO = {"title": "Biodiversity", "og_title": None, "og_image": None, "og_description": None,
         "meta_price": None, "meta_currency": None, "ld": [], "body": "Biodiversity fund USD 100"}


def test_body_text_only_price_dropped() -> None:
    from collections import Counter
    drops: Counter = Counter()
    pool = _pool_with_page(_INFO)
    assert asyncio.run(pool.extract_product_data("https://x.org/bio/page", "biodiversity", drops)) is None
    assert drops["no_structured_price"] == 1


def test_json_ld_price_kept() -> None:
    ld = '{"@type":"Product","name":"Biodiversity Kit","offers":{"price":"25","priceCurrency":"USD"}}'
    pool = _pool_with_page({**_INFO, "ld": [ld]})
    p = asyncio.run(pool.extract_product_data("https://x.org/bio/page", "biodiversity"))
    assert p is not None and p.price == 25


def test_httpx_logger_quiet_after_app_import() -> None:
    import app.main  # noqa: F401
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
