import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.settings import settings
from app.prompt import TRUST_VERIFICATION_PROMPT
from app.schemas.product import RawProduct, UserSearchQuery
from app.services import discovery
from app.services.discovery import DiscoveryWorkerPool, drop_google_links, pick_offer, resolve_store_links
from app.services.search import SerpApiError

GOOGLE = "https://www.google.com/search?ibp=oshop&prds=productid:1"
STORES = {"product_results": {"stores": [
    {"name": "Cheap Shop", "link": "https://cheap.example/p/1", "price": "$300.00", "extracted_price": 300.0},
    {"name": "Best Buy", "link": "https://www.bestbuy.com/p/1", "price": "$349.99", "extracted_price": 349.99, "rating": 4.6},
]}}


def _product(store: str = "Best Buy", n: int = 1) -> RawProduct:
    return RawProduct(id=f"id{n}", title="iPhone 15 128GB", price=399.0, currency="USD", url=GOOGLE + str(n),
                      store_name=store, source="google_shopping", offers_token=f"tok{n}")


def _enable(monkeypatch, fake) -> None:
    monkeypatch.setattr(settings, "search_provider", "serpapi")
    monkeypatch.setattr(settings, "serpapi_api_key", "k")
    monkeypatch.setattr(discovery, "serpapi_get", fake)


def test_offer_maps_link_name_price(monkeypatch) -> None:
    async def fake(engine, q, gl, hl, **extra):
        assert engine == "google_immersive_product" and extra == {"page_token": "tok1"}
        return STORES

    _enable(monkeypatch, fake)
    p = asyncio.run(resolve_store_links([_product()], "us", "en", top_n=10))[0]
    # Well-known retailer (Best Buy) wins over the cheaper obscure offer.
    assert (p.url, p.store_name, p.price, p.currency, p.rating) == ("https://www.bestbuy.com/p/1", "Best Buy", 349.99, "USD", 4.6)


def test_pick_offer_preferences() -> None:
    obscure = {"name": "Cheap Shop", "link": "https://cheap.example/p/1", "extracted_price": 300.0}
    rated = {"name": "Rated Shop", "link": "https://rated.example/p/1", "extracted_price": "320.00", "reviews": 85}
    region = {"name": "Blibli", "link": "https://www.blibli.com/p/x", "price": "Rp 4.500.000"}
    major = {"name": "eBay - somedealer", "link": "https://www.ebay.com/itm/1", "extracted_price": 340.0}
    no_link = {"name": "Amazon", "link": "", "extracted_price": 1.0}
    assert pick_offer([obscure, rated, major, no_link], ["tokopedia.com"]) is major  # well-known beats cheaper
    assert pick_offer([obscure, rated, no_link]) is rated  # then rating/reviews (string price parsed)
    assert pick_offer([obscure, no_link]) is obscure  # then cheapest
    assert pick_offer([obscure, region], ["blibli.com"]) is region  # region marketplace counts as well-known
    assert pick_offer([no_link]) is None


def test_resolution_restricts_offers_to_requested_marketplaces(monkeypatch) -> None:
    async def fake(engine, q, gl, hl, **extra):
        return {"product_results": {"stores": [
            {"name": "Amazon", "link": "https://amazon.com.evil.example/dp/1", "price": "$1"},
            {"name": "Best Buy", "link": "https://www.bestbuy.com/p/1", "price": "$2"},
            {"name": "Tokopedia", "link": "https://www.tokopedia.com/shop/headphones", "price": "$100"},
        ]}}

    _enable(monkeypatch, fake)
    p = asyncio.run(resolve_store_links([_product()], "id", "id", sites=["tokopedia.com"]))[0]
    assert p.url == "https://www.tokopedia.com/shop/headphones"


def test_drop_google_links() -> None:
    kept = [RawProduct(id="w", title="t", price=1.0, url="https://shop.example/p/1", store_name="S")]
    out = drop_google_links([_product(n=1), _product(n=2)] + kept)
    assert out == kept


def test_backfill_respects_cap(monkeypatch) -> None:
    calls: list[str] = []

    async def fake(engine, q, gl, hl, **extra):
        calls.append(extra["page_token"])
        return STORES

    _enable(monkeypatch, fake)
    monkeypatch.setattr(settings, "serpapi_resolve_max", 5)
    products = [_product(n=i) for i in range(12)]
    asyncio.run(resolve_store_links(products, "us", "en", top_n=3, need=20))
    assert len(calls) == 5  # 3 top + 2 backfill, capped although 20 were needed
    assert sum(not p.url.startswith("https://www.google.") for p in products) == 5

    calls.clear()
    products = [_product(n=i) for i in range(12)]
    asyncio.run(resolve_store_links(products, "us", "en", top_n=3, need=4))
    assert len(calls) == 4  # backfill only the deficit


def test_error_keeps_item(monkeypatch) -> None:
    async def fake(engine, q, gl, hl, **extra):
        raise SerpApiError("boom")

    _enable(monkeypatch, fake)
    p = asyncio.run(resolve_store_links([_product()], "us", "en", top_n=10))[0]
    assert p.url == GOOGLE + "1" and p.price == 399.0


def test_top_n_zero_disables_and_limits(monkeypatch) -> None:
    calls: list[str] = []

    async def fake(engine, q, gl, hl, **extra):
        calls.append(extra["page_token"])
        return STORES

    _enable(monkeypatch, fake)
    products = [_product(n=i) for i in range(3)]
    asyncio.run(resolve_store_links(products, "us", "en", top_n=0))
    assert calls == []
    asyncio.run(resolve_store_links(products, "us", "en", top_n=2))
    assert sorted(calls) == ["tok0", "tok1"] and products[2].url == GOOGLE + "2"


def test_trust_prompt_has_source() -> None:
    out = TRUST_VERIFICATION_PROMPT.format(
        title="t", price=1, currency="USD", store_name="s", rating="N/A", review_count="N/A",
        url="u", source="google_shopping", description="d")
    assert "Source: google_shopping" in out and "do NOT treat it as a search page" in out


def test_shopping_share_cap_and_backfill(monkeypatch) -> None:
    items = [{"title": f"Sony WH-1000XM5 {i}", "extracted_price": 100 + i, "price": f"${100 + i}",
              "source": "Amazon", "product_link": f"https://www.amazon.com/dp/SHOPPING{i}"} for i in range(20)]
    web_links = [f"https://www.amazon.com/dp/WEB{i}" for i in range(10)]

    async def fake_get(engine, q, gl, hl, **extra):
        return {"shopping_results": items} if engine == "google_shopping" else {"organic_results": [{"link": u} for u in web_links]}

    monkeypatch.setattr(settings, "search_provider", "serpapi")
    monkeypatch.setattr(settings, "serpapi_api_key", "k")
    monkeypatch.setattr(settings, "discovery_max_candidates", 15)
    monkeypatch.setattr(settings, "discovery_shopping_share", 0.6)
    monkeypatch.setattr(discovery, "serpapi_get", fake_get)
    fetched: list[str] = []
    web_ok = {"n": 0}

    async def fake_extract(self, url, query, drops, cur="USD"):
        fetched.append(url)
        if len(fetched) > web_ok["n"]:
            return None
        return RawProduct(id=url, title="Sony WH-1000XM5", price=5.0, url=url, store_name="W")

    monkeypatch.setattr(DiscoveryWorkerPool, "extract_product_data", fake_extract)
    q = UserSearchQuery(query="sony wh-1000xm5", limit=3)

    web_ok["n"] = 99  # web fully yields: 9 shopping (60% of 15) + 6 web
    out = asyncio.run(DiscoveryWorkerPool(concurrency=2).discover(q))
    assert len(fetched) == 6 and sum(p.source == "google_shopping" for p in out) == 9 and len(out) == 15

    fetched.clear()
    web_ok["n"] = 2  # web yields only 2: backfill shopping up to the target
    out = asyncio.run(DiscoveryWorkerPool(concurrency=2).discover(q))
    assert len(out) == 15 and sum(p.source == "google_shopping" for p in out) == 13
