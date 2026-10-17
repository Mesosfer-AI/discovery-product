import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.settings import settings
from app.schemas.product import RawProduct
from app.services.trust import TrustVerificationWorker, parse_batch_verdicts


def _p(n: int) -> RawProduct:
    return RawProduct(id=f"id{n}", title=f"Sony WH-1000XM5 #{n}", price=300.0, url=f"https://shop.example/p/{n}",
                      store_name="Shop", rating=4.8)


class BatchProvider:
    """Answers each batch prompt with a verdict for every listed id except those in `skip`."""

    def __init__(self, skip: set[str] = frozenset(), raw: str | None = None) -> None:
        self.calls = 0
        self.skip, self.raw = skip, raw

    async def chat(self, messages: list, model: str | None = None, **kwargs) -> str:
        self.calls += 1
        if self.raw is not None:
            return self.raw
        prompt = messages[-1]["content"]
        items = json.loads(prompt.split("each has an \"id\"):\n", 1)[1].split("\n\nEvaluate:", 1)[0])
        verdicts = [{"id": it["id"], "trust_score": 80, "is_trusted": True, "trust_verdict": "ok", "fraud_flags": []}
                    for it in items if it["id"] not in self.skip]
        return "```json\n" + json.dumps({"verdicts": verdicts}) + "\n```"


def test_parse_batch_verdicts_shapes() -> None:
    assert set(parse_batch_verdicts('{"verdicts": [{"id": "p1", "trust_score": 70}, {"trust_score": 1}]}')) == {"p1"}
    assert set(parse_batch_verdicts('[{"id": "p2"}]')) == {"p2"}
    assert set(parse_batch_verdicts('{"p1": {"trust_score": 70}, "p3": {"trust_score": 20}}')) == {"p1", "p3"}
    assert parse_batch_verdicts("not json") == {}
    assert parse_batch_verdicts('{"verdicts": [{"id": "p1",') == {}


def test_batches_by_size(monkeypatch) -> None:
    monkeypatch.setattr(settings, "trust_batch_size", 4)
    provider = BatchProvider()
    out = asyncio.run(TrustVerificationWorker(provider=provider).verify_batch([_p(i) for i in range(10)]))
    assert provider.calls == 3 and len(out) == 10 and all(v.trust_score == 80 for v in out)
    assert [v.product.id for v in out] == [f"id{i}" for i in range(10)]


def test_missing_ids_get_untrusted_heuristic(monkeypatch) -> None:
    monkeypatch.setattr(settings, "trust_batch_size", 8)
    out = asyncio.run(TrustVerificationWorker(provider=BatchProvider(skip={"p2"})).verify_batch([_p(i) for i in range(3)]))
    # p2 (the second product) has no verdict -> heuristic, never trusted -> filtered out.
    assert [v.product.id for v in out] == ["id0", "id2"]


def test_malformed_reply_trusts_nothing() -> None:
    provider = BatchProvider(raw='{"verdicts": [ {"id": "p1", "trust_score": ')
    assert asyncio.run(TrustVerificationWorker(provider=provider).verify_batch([_p(1), _p(2)])) == []
    assert provider.calls == 1
