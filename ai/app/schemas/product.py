import hashlib
from typing import Any
from pydantic import BaseModel, Field, field_validator


class UserSearchQuery(BaseModel):
    """Input payload representing user shopping intent and constraints."""

    query: str = Field(..., description="Target product search query", min_length=2)
    budget_max: float | None = Field(None, description="Maximum budget threshold")
    currency: str = Field("USD", description="Currency code (e.g. USD, IDR, EUR)")
    preferred_stores: list[str] = Field(default_factory=list, description="Optional store preferences")
    limit: int = Field(5, description="Number of top recommended products to return", ge=1, le=10)
    country: str | None = Field(
        None,
        description=(
            "ISO 3166-1 alpha-2 country code of the end user (e.g. us, id, gb), lowercased. The backend should fill "
            "it from the end user's location (IP geolocation or profile); omitted = global search."
        ),
    )

    @field_validator("country")
    @classmethod
    def _normalize_country(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().lower()
        if not (len(v) == 2 and v.isascii() and v.isalpha()):
            raise ValueError("country must be a 2-letter ISO 3166-1 alpha-2 code, e.g. 'us'")
        return v


class RawProduct(BaseModel):
    """Stage 1 output: raw candidate scraped or extracted from web/marketplaces."""

    id: str = Field(..., description="Unique product hash or identifier")
    title: str = Field(..., description="Product title/headline")
    price: float = Field(..., gt=0, description="Numeric product price")
    currency: str = Field("USD", description="Price currency")
    url: str = Field(..., description="Direct URL to product page")
    image_url: str | None = Field(None, description="Product image link")
    store_name: str = Field(..., description="Seller/store or marketplace name")
    rating: float | None = Field(None, description="Rating average (e.g. 4.8 out of 5.0)")
    review_count: int | None = Field(None, description="Total number of reviews/ratings")
    description: str | None = Field(None, description="Key specifications or product summary")
    source: str = Field("web", description="Origin source or marketplace")
    offers_token: str | None = Field(None, exclude=True, description="Google Shopping immersive-product token used to resolve merchant offers")

    @classmethod
    def generate_id(cls, url: str, title: str, store: str) -> str:
        """Deterministic hash generator for deduplication."""
        seed = f"{store.lower().strip()}:{title.lower().strip()}:{url.strip()}"
        return hashlib.sha256(seed.encode()).hexdigest()[:16]


class VerifiedProduct(BaseModel):
    """Stage 2 output: candidate after trust, authenticity, and reputation verification."""

    product: RawProduct
    trust_score: float = Field(..., description="Trust rating between 0 and 100", ge=0.0, le=100.0)
    is_trusted: bool = Field(..., description="True if trust_score meets minimum threshold (e.g. >= 60)")
    trust_verdict: str = Field(..., description="Short verdict summary on seller & product authenticity")
    fraud_flags: list[str] = Field(default_factory=list, description="Specific warning signals detected, if any")
    sentiment_summary: str | None = Field(None, description="Summary of real buyer experiences and complaints")


class RecommendedProduct(BaseModel):
    """Stage 3 output: final curated and ranked recommendation."""

    rank: int = Field(..., ge=1, le=10, description="Rank position (1 is best)")
    product: RawProduct
    trust_score: float = Field(..., description="Inherited trust rating")
    match_score: float = Field(..., description="Relevance and value-for-money score (0-100)", ge=0.0, le=100.0)
    why_recommended: str = Field(..., description="Persuasive explanation of why this product fits user needs")
    pros: list[str] = Field(default_factory=list, description="Top standout advantages")
    cons: list[str] = Field(default_factory=list, description="Noted trade-offs or caveats")


class DiscoveryResponse(BaseModel):
    """Final API response returned to caller or backend service."""

    query: str
    total_discovered: int
    total_deduplicated: int
    total_verified: int
    recommendations: list[RecommendedProduct]
    execution_time_seconds: float
    provider_used: str
