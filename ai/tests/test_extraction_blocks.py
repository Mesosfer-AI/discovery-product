import asyncio
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.discovery import DiscoveryWorkerPool, fetch_blocked, is_blocked_page, site_price

# Trimmed from pages fetched with the project's headless Chromium (Oct 2026).
AMAZON_BODY = "Click the button below to continue shopping Continue shopping Conditions of Use Privacy Policy"
WALMART_URL = "https://www.walmart.com/blocked?url=L2lwL0FwcGxl"
SHOPEE_URL = "https://shopee.co.id/verify/traffic/error?home_url=https%3A%2F%2Fshopee.co.id"
BLIBLI_URL = "https://www.blibli.com/challenge/landing/?redirect=%2Fp%2Fsony-wh-1000xm5"
LAZADA_SCRIPT = (
    '<script>var __moduleData__ = {"page":{"xParams":"_p_typ=pdp&_p_prod=7530242717"},'
    '\\"supplier_id\\":\\"\\",\\"pdt_price\\":\\"Rp4.799.000\\",\\"extraInfo\\":{}};</script>'
)
LAZADA_SCRIPT_PLAIN = '<script>{"supplier_id":"","pdt_price":"Rp4.799.000","extraInfo":{}}</script>'


def test_blocked_pages_detected() -> None:
    assert is_blocked_page(200, "https://www.amazon.com/dp/B0CMPMY9ZZ", "Amazon.com", AMAZON_BODY)
    assert is_blocked_page(403, "https://www.ebay.com/itm/187437992992", "Error Page | eBay", "SORRY Something went wrong")
    assert is_blocked_page(200, WALMART_URL, "Robot or human?", "Activate and hold the button")
    assert is_blocked_page(200, SHOPEE_URL, "Shopee Indonesia", "lompat ke konten utama")
    assert is_blocked_page(200, BLIBLI_URL, "Online Mall Blibli", "Ada aktivitas yang tidak biasa Coba lagi nanti")


def test_normal_product_page_not_blocked() -> None:
    body = "Home Sony Headphone WH1000XM5 - Black Rp 4.099.000 Rp 5.999.000 32% Continue shopping later"
    assert not is_blocked_page(200, "https://erafone.com/produk/sony-headphone-wh1000xm5-black", "Jual Sony", body)


def test_fetch_blocked_hosts() -> None:
    assert fetch_blocked("https://www.tokopedia.com/shop/sony-wh-1000xm5") == "fetch_blocked"
    assert fetch_blocked("https://www.amazon.com/Apple-iPhone-15/dp/B0CMPMY9ZZ") == "fetch_blocked"
    assert fetch_blocked("https://www.blibli.com/p/sony-wh-1000xm5/ps--SOA-60059-00242") == "fetch_blocked"
    assert fetch_blocked("https://www.lazada.co.id/products/x-i1.html") is None
    assert fetch_blocked("https://erafone.com/produk/x") is None


def test_lazada_site_price() -> None:
    assert site_price("lazada.co.id", LAZADA_SCRIPT) == (4799000.0, "IDR")
    assert site_price("h5.lazada.co.id", LAZADA_SCRIPT_PLAIN) == (4799000.0, "IDR")
    assert site_price("erafone.com", LAZADA_SCRIPT) == (None, None)  # rule is site-specific
    assert site_price("lazada.co.id", "<html>no price here</html>") == (None, None)


def _pool(info: dict, status: int = 200, final_url: str = "", html: str = "") -> DiscoveryWorkerPool:
    page = MagicMock()
    page.goto = AsyncMock(return_value=MagicMock(status=status))
    page.wait_for_function, page.close = AsyncMock(), AsyncMock()
    page.evaluate = AsyncMock(return_value=info)
    page.content = AsyncMock(return_value=html)
    page.url = final_url
    ctx = MagicMock()
    ctx.new_page, ctx.close = AsyncMock(return_value=page), AsyncMock()
    pool = DiscoveryWorkerPool(concurrency=1)
    pool.browser_manager = MagicMock()
    pool.browser_manager.create_context = AsyncMock(return_value=ctx)
    return pool


_INFO = {"title": "", "og_title": None, "og_image": None, "og_description": None,
         "meta_price": None, "meta_currency": None, "ld": [], "body": ""}


def test_extract_labels_blocked_instead_of_no_price() -> None:
    drops: Counter = Counter()
    url = "https://www.walmart.com/ip/Apple-iPhone-15/20809023575"
    pool = _pool({**_INFO, "title": "Robot or human?"}, final_url=WALMART_URL)
    assert asyncio.run(pool.extract_product_data(url, "iphone 15", drops)) is None
    assert drops == {"blocked": 1}


def test_extract_uses_lazada_site_price_as_structured() -> None:
    url = "https://www.lazada.co.id/products/sony-wh-1000xm5-i7530242717.html"
    title = "Sony WH-1000XM5 / WH1000XM5 Noise-Cancelling Headphones | Lazada Indonesia"
    pool = _pool({**_INFO, "title": title, "body": "Sony WH-1000XM5"}, final_url=url, html=LAZADA_SCRIPT)
    p = asyncio.run(pool.extract_product_data(url, "sony wh-1000xm5", Counter(), "IDR"))
    assert p is not None and (p.price, p.currency) == (4799000.0, "IDR")


def test_site_queries_skip_blocked_hosts() -> None:
    from app.services.discovery import _FETCH_BLOCKED_HOSTS, build_search_queries
    from app.services.regions import resolve_region

    for country, left in (("us", ["bestbuy.com"]), ("id", ["lazada.co.id"]), (None, ["aliexpress.com"])):
        qs = build_search_queries("tv", resolve_region(country).sites, None, _FETCH_BLOCKED_HOSTS)
        assert [s for s, _ in qs[:-1]] == left and qs[-1] == ("web", "tv")


def test_learned_host_is_persisted_then_skipped(monkeypatch) -> None:
    asyncio.run(_learned_host_flow(monkeypatch))


async def _learned_host_flow(monkeypatch) -> None:
    import app.services.discovery as d
    from app.services.redis_client import CacheManager

    cm = CacheManager("redis://127.0.0.1:1/0")  # unreachable -> in-memory fallback
    monkeypatch.setattr(d, "cache_manager", cm)
    assert "newshop.example" not in await d.load_blocked_hosts()
    await d.learn_blocked_host("www.NewShop.example")
    blocked = await d.load_blocked_hosts()
    assert "newshop.example" in blocked and "amazon.com" in blocked  # learned + seed, fallback works
    assert d.fetch_blocked("https://www.newshop.example/p/1", blocked) == "fetch_blocked"
    qs = d.build_search_queries("x", ["newshop.example", "ok.example"], None, blocked)
    assert [s for s, _ in qs[:-1]] == ["ok.example"]


def test_429_is_dropped_but_not_learned_while_403_is(monkeypatch) -> None:
    import app.services.discovery as d
    from app.services.redis_client import CacheManager

    monkeypatch.setattr(d, "cache_manager", CacheManager("redis://127.0.0.1:1/0"))
    url = "https://shop.example/p/1"
    for status in (429, 403):
        drops: Counter = Counter()
        pool = _pool(_INFO, status=status, final_url=url)
        assert asyncio.run(pool.extract_product_data(url, "x", drops)) is None and drops == {"blocked": 1}
        learned = asyncio.run(d.cache_manager.get_set(d.BLOCKED_HOSTS_KEY))
        assert ("shop.example" in learned) == (status == 403)
