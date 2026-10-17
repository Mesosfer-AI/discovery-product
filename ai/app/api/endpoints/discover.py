from fastapi import APIRouter, HTTPException
from app.schemas.product import DiscoveryResponse, UserSearchQuery
from app.services.pipeline import pipeline
from app.services.search import SearchBlockedError, SearchUnavailableError, SerpApiQuotaExhaustedError

router = APIRouter()


@router.post("/discover", response_model=DiscoveryResponse)
async def discover_products(query: UserSearchQuery) -> DiscoveryResponse:
    """
    Execute 3-Stage Autonomous Discovery:
    1. 20-Worker Global Browser Discovery
    2. Redis-backed Deduplication
    3. 5-Worker Trust & Fraud Verification
    4. 3-Worker Reasoning Recommendation
    """
    try:
        return await pipeline.execute(query)
    except SerpApiQuotaExhaustedError as exc:
        raise HTTPException(status_code=402, detail="Search provider quota exhausted.") from exc
    except SearchBlockedError as exc:
        raise HTTPException(status_code=429, detail="Search is temporarily blocked. Please try again later.") from exc
    except SearchUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Search is temporarily unavailable.") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline execution failed: {str(exc)}") from exc
