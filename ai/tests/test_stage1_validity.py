import asyncio
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.product import RawProduct, UserSearchQuery, VerifiedProduct
from app.services.discovery import rejection_reason, title_matches_query
from app.services.recommender import RecommendationEngine
from app.services.trust import TrustVerificationWorker


def make_product(**kw) -> RawProduct:
    base = dict(id="p1", title="Sony WH-1000XM5", price=300.0, url="https://shop.example/p/1", store_name="Shop")
    return RawProduct(**{**base, **kw})


class FakeProvider:
    def __init__(self, reply: str = "{}") -> None:
        self.calls = 0
        self.reply = reply

    async def chat(self, messages: list, model: str | None = None, **kwargs) -> str:
        self.calls += 1
        return self.reply


def test_title_matches_query() -> None:
    assert title_matches_query("Sony WH-1000XM5 Wireless Headphones", "https://x.com/p", "sony wh-1000xm5")
    assert title_matches_query("Apple iPhone 15 128GB", "https://x.com/p", "iphone 15 128gb")
    assert not title_matches_query("Sony Corporation", "https://www.sony.net/", "sony wh-1000xm5")
    assert not title_matches_query("iBox Official Store", "https://ibox.co.id/", "iphone 15 128gb")


def test_rejection_reason() -> None:
    q = "sony wh-1000xm5"
    ok_url = "https://shop.example/p/1"
    assert rejection_reason(ok_url, "Sony WH-1000XM5", 300.0, q) is None
    assert rejection_reason("https://www.sony.net/?l=en_US", "Sony WH-1000XM5", 300.0, q) == "bare_root_url"
    assert rejection_reason("https://apple.com", "Sony WH-1000XM5", 300.0, q) == "bare_root_url"
    assert rejection_reason(ok_url, "Sony WH-1000XM5", None, q) == "no_price"
    assert rejection_reason(ok_url, "Sony WH-1000XM5", 0.0, q) == "no_price"


def test_raw_product_rejects_non_positive_price() -> None:
    with pytest.raises(ValidationError):
        make_product(price=0.0)


def test_verify_batch_empty_when_none_trusted() -> None:
    # Provider returns garbage -> heuristic path, which must never mark a product trusted.
    worker = TrustVerificationWorker(provider=FakeProvider("not json"))
    assert asyncio.run(worker.verify_batch([make_product(rating=4.9)])) == []


def test_recommender_empty_input_skips_llm() -> None:
    provider = FakeProvider()
    engine = RecommendationEngine(provider=provider)
    assert asyncio.run(engine.recommend(UserSearchQuery(query="sony headphones"), [])) == []
    assert provider.calls == 0


def test_recommender_empty_llm_list_returns_empty() -> None:
    engine = RecommendationEngine(provider=FakeProvider('{"recommendations": []}'))
    vp = VerifiedProduct(product=make_product(), trust_score=90.0, is_trusted=True, trust_verdict="ok")
    assert asyncio.run(engine.recommend(UserSearchQuery(query="sony headphones"), [vp])) == []
