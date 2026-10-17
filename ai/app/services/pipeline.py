import time
from app.config.settings import settings
from app.schemas.product import DiscoveryResponse, UserSearchQuery
from app.services.dedup import deduplication_engine
from app.services.discovery import discovery_pool, drop_google_links, resolve_store_links
from app.services.regions import DISCOVERY_SOURCES, resolve_region
from app.services.recommender import recommendation_engine
from app.services.trust import trust_worker


class DiscoveryPipeline:
    """Master Orchestrator executing the complete 3-Stage Discovery Pipeline."""

    def __init__(self) -> None:
        self.discovery_pool = discovery_pool
        self.dedup_engine = deduplication_engine
        self.trust_worker = trust_worker
        self.recommender = recommendation_engine

    async def execute(self, query: UserSearchQuery) -> DiscoveryResponse:
        start_time = time.time()

        # STAGE 1: Product Discovery (20 workers)
        raw_products = await self.discovery_pool.discover(query)

        # DEDUPLICATION: Merge identical products
        deduped_products = await self.dedup_engine.deduplicate(
            raw_products,
            session_id=query.query.strip().lower(),
        )

        # Resolve merchant store links for shopping items so trust sees real store URLs; items left on a
        # google.com link are dropped before trust (no LLM calls spent on them).
        region = resolve_region(query.country)
        # ponytail: ~3 candidates per requested result covers the trust filter rate seen live (~40-50% pass).
        candidates = await resolve_store_links(
            deduped_products, region.gl, region.hl, need=query.limit * 3, sites=DISCOVERY_SOURCES
        )
        candidates = drop_google_links(candidates)

        # STAGE 2: Trust & Verification (batched LLM calls)
        verified_products = await self.trust_worker.verify_batch(candidates)

        # STAGE 3: Recommendation (3 workers)
        top_recommendations = await self.recommender.recommend(query, verified_products)

        elapsed = round(time.time() - start_time, 2)

        return DiscoveryResponse(
            query=query.query,
            total_discovered=len(raw_products),
            total_deduplicated=len(deduped_products),
            total_verified=len(verified_products),
            recommendations=top_recommendations,
            execution_time_seconds=elapsed,
            provider_used=settings.llm_provider,
        )


pipeline = DiscoveryPipeline()
