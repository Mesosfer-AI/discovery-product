import asyncio
import os
import sys
from pathlib import Path
import httpx
import uuid

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app
from app.config.settings import settings
from app.schemas.product import RawProduct, UserSearchQuery, VerifiedProduct
from app.services.dedup import deduplication_engine
from app.services.recommender import RecommendationEngine
from app.services.trust import TrustVerificationWorker


class MockLLMProvider:
    """Fast mock LLM provider for unit verification."""

    async def chat(self, messages: list, model: str | None = None, **kwargs) -> str:
        prompt = messages[-1]["content"] if messages else ""
        if "Fraud & Trust Investigator" in prompt:
            return '{"trust_score": 88.0, "is_trusted": true, "trust_verdict": "Verified official store.", "fraud_flags": [], "sentiment_summary": "Positive buyer reviews."}'
        if "Master Commercial Shopping Advisor" in prompt:
            return '{"recommendations": [{"rank": 1, "product_id": "test_id_1", "match_score": 96.0, "why_recommended": "Top value for mechanical keyboard enthusiasts.", "pros": ["Hot-swappable", "PBT keycaps"], "cons": ["Wired only"]}]}'
        return "{}"

    async def generate(self, prompt: str, **kwargs) -> str:
        return "{}"

    async def is_available(self) -> bool:
        return True


async def check_pipeline_logic() -> None:
    # 1. Test Deduplication
    p1 = RawProduct(
        id="test_id_1",
        title="Royal Kludge RK61 Mechanical Keyboard",
        price=45.0,
        currency="USD",
        url="https://example.com/p1?utm_source=ad",
        store_name="ExampleStore",
        rating=4.7,
        review_count=120,
    )
    p2 = RawProduct(
        id="test_id_2",
        title="royal kludge rk61 mechanical keyboard",  # duplicate title
        price=44.0,
        currency="USD",
        url="https://example.com/p1",  # duplicate url
        store_name="ExampleStore",
        rating=4.7,
        review_count=120,
    )
    p3 = RawProduct(
        id="test_id_3",
        title="Keychron K2 Wireless Keyboard",
        price=79.0,
        currency="USD",
        url="https://example.com/p2",
        store_name="KeychronDirect",
        rating=4.9,
        review_count=350,
    )

    deduped = await deduplication_engine.deduplicate(
        [p1, p2, p3],
        session_id=f"test_session_{uuid.uuid4().hex}",
    )
    assert len(deduped) == 2, f"Expected 2 unique products, got {len(deduped)}"
    assert {p.id for p in deduped} == {"test_id_1", "test_id_3"}

    # 2. Test Trust Verification Worker
    mock_provider = MockLLMProvider()
    trust_worker = TrustVerificationWorker(provider=mock_provider)
    verified = await trust_worker.verify_single(p1)
    assert verified.trust_score == 88.0
    assert verified.is_trusted is True
    assert "Verified" in verified.trust_verdict

    # 3. Test Recommender Engine
    recommender = RecommendationEngine(provider=mock_provider)
    query = UserSearchQuery(query="mechanical keyboard under $50", budget_max=50.0, limit=1)
    recs = await recommender.recommend(query, [verified])
    assert len(recs) == 1
    assert recs[0].rank == 1
    assert recs[0].match_score == 96.0
    assert "Top value" in recs[0].why_recommended

    # 4. Test FastAPI Endpoint
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        health_res = await ac.get("/api/v1/health")
        assert health_res.status_code == 200, f"Expected 200, got {health_res.status_code}"
        health_data = health_res.json()
        assert health_data["app_name"] == settings.app_name

    print("ALL PIPELINE & DEDUP & API CHECKS PASSED.")



def test_pipeline() -> None:
    asyncio.run(check_pipeline_logic())


if __name__ == "__main__":
    asyncio.run(check_pipeline_logic())
