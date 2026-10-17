import asyncio
import json
import logging
import re
from typing import Any
from urllib.parse import urlparse
from app.config.settings import settings
from app.prompt import TRUST_BATCH_PROMPT, TRUST_VERIFICATION_PROMPT
from app.provider import BaseLLMProvider, get_model, get_provider
from app.schemas.product import RawProduct, VerifiedProduct

logger = logging.getLogger(__name__)


def _json_payload(text: str) -> Any:
    """Parse the outermost JSON object/array in an LLM reply (tolerates code fences and surrounding prose)."""
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    return json.loads(match.group(1) if match else text.replace("```json", "").replace("```", "").strip())


def parse_batch_verdicts(text: str) -> dict[str, dict[str, Any]]:
    """Map product id -> verdict dict from a batch reply; malformed JSON or entries are skipped (empty dict on failure)."""
    try:
        data = _json_payload(text)
    except (TypeError, ValueError):
        return {}
    if isinstance(data, dict):
        data = data.get("verdicts", data.get("results", data))
    if isinstance(data, dict):  # {"p1": {...}, "p2": {...}}
        data = [{**v, "id": k} for k, v in data.items() if isinstance(v, dict)]
    if not isinstance(data, list):
        return {}
    return {str(v["id"]): v for v in data if isinstance(v, dict) and v.get("id") is not None}


def _to_verified(product: RawProduct, data: dict[str, Any]) -> VerifiedProduct:
    trust_score = max(0.0, min(100.0, float(data.get("trust_score", 50.0))))
    return VerifiedProduct(
        product=product,
        trust_score=trust_score,
        is_trusted=bool(data.get("is_trusted", trust_score >= 60.0)),
        trust_verdict=str(data.get("trust_verdict", "Evaluated by AI trust engine.")),
        fraud_flags=[str(f) for f in data.get("fraud_flags") or []],
        sentiment_summary=data.get("sentiment_summary"),
    )


def _heuristic(product: RawProduct) -> VerifiedProduct:
    # ponytail: Fail-safe heuristic when LLM parsing errors out.
    # Score based on rating/review count signals if LLM output fails.
    # Never marks trusted: an unverified listing must not survive on heuristics alone.
    base_score = 55.0 if (product.rating and product.rating >= 4.0) else 40.0
    return VerifiedProduct(
        product=product,
        trust_score=base_score,
        is_trusted=False,
        trust_verdict="Automated heuristic assessment (LLM review fallback).",
        fraud_flags=[],
        sentiment_summary=None,
    )


class TrustVerificationWorker:
    """Stage 2: 5 parallel workers verifying product authenticity and seller trustworthiness."""

    def __init__(self, provider: BaseLLMProvider | None = None, concurrency: int = 5) -> None:
        self.provider = provider or get_provider()
        # Never wider than the process-wide LLM limit enforced in the provider.
        self.semaphore = asyncio.Semaphore(min(concurrency, settings.llm_max_concurrency))
        self.model = get_model("fast")  # High-speed, cost-effective model of the active provider

    @staticmethod
    def _log_item(res: VerifiedProduct, origin: str) -> None:
        p = res.product
        logger.debug(
            "Trust [%s] %s %r store=%r host=%s score=%.0f trusted=%s verdict=%r flags=%s",
            origin, p.id, p.title[:60], p.store_name, urlparse(p.url).netloc, res.trust_score,
            res.is_trusted, res.trust_verdict[:120], res.fraud_flags,
        )

    async def verify_single(self, product: RawProduct) -> VerifiedProduct:
        """Evaluate a single product candidate with the LLM trust prompt."""
        res, origin = await self._verify(product)
        self._log_item(res, origin)
        return res

    async def _verify(self, product: RawProduct) -> tuple[VerifiedProduct, str]:
        async with self.semaphore:
            prompt = TRUST_VERIFICATION_PROMPT.format(
                title=product.title,
                price=product.price,
                currency=product.currency,
                store_name=product.store_name,
                rating=product.rating or "N/A",
                review_count=product.review_count or "N/A",
                url=product.url,
                source=product.source,
                description=product.description or "No detailed description provided.",
            )

            try:
                response = await self.provider.chat(
                    messages=[{"role": "user", "content": prompt}],
                    model=self.model,
                    response_format={"type": "json_object"},
                )
                return _to_verified(product, _json_payload(response)), "llm"
            except Exception as exc:
                logger.warning(
                    "Trust LLM failed (provider=%s, model=%s) for product %s; using heuristic: %r",
                    settings.llm_provider, self.model, product.id, exc,
                )
                return _heuristic(product), "heuristic"

    async def _verify_chunk(self, products: list[RawProduct]) -> list[VerifiedProduct]:
        """One LLM call scoring several products; ids missing from the reply get the (never trusted) heuristic."""
        payload = [
            {
                "id": f"p{i}",
                "title": p.title,
                "price": p.price,
                "currency": p.currency,
                "store": p.store_name,
                "rating": p.rating,
                "review_count": p.review_count,
                "source": p.source,
                "url": p.url,
                "description": (p.description or "")[:300] or None,
            }
            for i, p in enumerate(products, 1)
        ]
        verdicts: dict[str, dict[str, Any]] = {}
        async with self.semaphore:
            try:
                response = await self.provider.chat(
                    messages=[{"role": "user", "content": TRUST_BATCH_PROMPT.format(products_json=json.dumps(payload, ensure_ascii=False))}],
                    model=self.model,
                    response_format={"type": "json_object"},
                )
                verdicts = parse_batch_verdicts(response)
            except Exception as exc:
                logger.warning(
                    "Trust batch LLM failed (provider=%s, model=%s) for %d products; using heuristic: %r",
                    settings.llm_provider, self.model, len(products), exc,
                )
        results = []
        for i, p in enumerate(products, 1):
            data, origin = verdicts.get(f"p{i}"), "llm"
            try:
                res = _to_verified(p, data) if data is not None else None
            except (TypeError, ValueError):
                res = None
            if res is None:
                res, origin = _heuristic(p), "heuristic"
            self._log_item(res, origin)
            results.append(res)
        missing = sum(1 for r in results if r.trust_verdict.startswith("Automated heuristic"))
        if verdicts and missing:
            logger.warning("Trust batch reply missing/invalid for %d of %d products; heuristic used", missing, len(products))
        return results

    async def verify_batch(self, products: list[RawProduct]) -> list[VerifiedProduct]:
        """Verify products in chunks of TRUST_BATCH_SIZE (one LLM call each), chunks run concurrently."""
        size = max(1, settings.trust_batch_size)
        chunks = [products[i:i + size] for i in range(0, len(products), size)]
        results = [r for chunk in await asyncio.gather(*(self._verify_chunk(c) for c in chunks)) for r in chunk]
        # Keep only trusted products; empty list when none qualify.
        trusted = [res for res in results if res.is_trusted]
        fallbacks = sum(1 for r in results if r.trust_verdict.startswith("Automated heuristic"))
        logger.info(
            "Trust: scored %d in %d LLM calls, trusted %d, filtered out %d, heuristic fallbacks %d",
            len(results), len(chunks), len(trusted), len(results) - len(trusted), fallbacks,
        )
        return trusted


trust_worker = TrustVerificationWorker()
