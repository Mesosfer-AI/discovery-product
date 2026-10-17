import asyncio
import json
import logging
import re
from typing import Any
from app.config.settings import settings
from app.prompt import RECOMMENDER_PROMPT
from app.provider import BaseLLMProvider, get_model, get_provider
from app.schemas.product import RecommendedProduct, UserSearchQuery, VerifiedProduct

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """Stage 3: 3-worker consensus and reasoning engine synthesizing final Top 5 recommendations."""

    def __init__(self, provider: BaseLLMProvider | None = None, concurrency: int = 3) -> None:
        self.provider = provider or get_provider()
        # Never wider than the process-wide LLM limit enforced in the provider.
        self.semaphore = asyncio.Semaphore(min(concurrency, settings.llm_max_concurrency))
        self.model = get_model("reasoning")  # Deep reasoning model of the active provider

    async def recommend(
        self,
        query: UserSearchQuery,
        verified_candidates: list[VerifiedProduct],
    ) -> list[RecommendedProduct]:
        """Rank and elaborate the best products tailored to the user query."""
        if not verified_candidates:
            return []

        async with self.semaphore:
            candidates_payload = [
                {
                    "id": vp.product.id,
                    "title": vp.product.title,
                    "price": vp.product.price,
                    "currency": vp.product.currency,
                    "store_name": vp.product.store_name,
                    "rating": vp.product.rating,
                    "trust_score": vp.trust_score,
                    "trust_verdict": vp.trust_verdict,
                    "description": vp.product.description,
                }
                for vp in verified_candidates
            ]

            prompt = RECOMMENDER_PROMPT.format(
                limit=query.limit,
                query=query.query,
                budget_max=query.budget_max or "No explicit budget limit",
                currency=query.currency,
                preferred_stores=", ".join(query.preferred_stores) or "Any trusted store",
                candidates_json=json.dumps(candidates_payload, indent=2),
            )

            id_map = {vp.product.id: vp for vp in verified_candidates}

            try:
                response = await self.provider.chat(
                    messages=[{"role": "user", "content": prompt}],
                    model=self.model,
                    response_format={"type": "json_object"},
                )
                cleaned = response.strip()
                match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
                if match:
                    cleaned = match.group(1)
                else:
                    cleaned = cleaned.replace("```json", "").replace("```", "").strip()
                data = json.loads(cleaned)
                raw_recs = data.get("recommendations", [])

                output: list[RecommendedProduct] = []
                for item in raw_recs:
                    pid = item.get("product_id")
                    vp = id_map.get(pid)
                    if vp:
                        output.append(
                            RecommendedProduct(
                                rank=int(item.get("rank", len(output) + 1)),
                                product=vp.product,
                                trust_score=vp.trust_score,
                                match_score=float(item.get("match_score", 85.0)),
                                why_recommended=str(item.get("why_recommended", "High value recommendation.")),
                                pros=list(item.get("pros", [])),
                                cons=list(item.get("cons", [])),
                            )
                        )

                output.sort(key=lambda r: r.rank)
                return output[: query.limit]
            except Exception as exc:
                logger.warning(
                    "Recommender LLM failed (provider=%s, model=%s); ranking by trust score: %r",
                    settings.llm_provider, self.model, exc,
                )
                # ponytail: Fallback to sorting by trust score and rating if LLM reasoning output fails.
                sorted_vps = sorted(
                    verified_candidates,
                    key=lambda v: (v.trust_score, v.product.rating or 0),
                    reverse=True,
                )[: query.limit]

                return [
                    RecommendedProduct(
                        rank=idx + 1,
                        product=vp.product,
                        trust_score=vp.trust_score,
                        match_score=vp.trust_score,
                        why_recommended=f"Ranked by trust score ({vp.trust_score:.0f}/100); listed at {vp.product.price} {vp.product.currency} on {vp.product.store_name}.",
                        pros=[],
                        cons=[],
                    )
                    for idx, vp in enumerate(sorted_vps)
                ]


recommendation_engine = RecommendationEngine()
