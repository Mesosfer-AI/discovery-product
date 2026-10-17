import logging
import re
from urllib.parse import parse_qsl, urlencode, urlparse
from app.schemas.product import RawProduct

logger = logging.getLogger(__name__)

_TRACKING_PARAM = re.compile(r"^(utm_.*|gclid|fbclid|srsltid)$", re.I)


def normalize_title(title: str) -> str:
    """Normalize product title to a clean token signature."""
    cleaned = re.sub(r"[^\w\s]", "", title.lower())
    tokens = sorted(set(cleaned.split()))
    return " ".join(tokens)


def clean_url(url: str) -> str:
    """Canonical URL key: host+path; google.com URLs also keep their non-tracking query (it identifies the product)."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host == "amazon.com" or host.endswith(".amazon.com"):
        asin = re.search(r"^/(?:[^/]+/)?(?:dp|gp/product)/([A-Z0-9]{10})(?:/|$)", parsed.path, re.I)
        if asin:
            return f"amazon.com/dp/{asin.group(1).upper()}"
    key = f"{parsed.netloc}{parsed.path}".rstrip("/")
    if "google." in parsed.netloc.lower():
        # ponytail: google.com/shopping/product/<id>?... and /search?...&prds=... differ only by query.
        query = [(k, v) for k, v in parse_qsl(parsed.query) if not _TRACKING_PARAM.match(k)]
        if query:
            key += "?" + urlencode(sorted(query))
    return key


class DeduplicationEngine:
    """Merges identical products across multiple discovery workers and marketplaces."""

    async def deduplicate(
        self,
        products: list[RawProduct],
        session_id: str = "global",
    ) -> list[RawProduct]:
        """
        Filters duplicate products within one request by store+title signature and canonical URL.
        Different stores selling the same model stay distinct offers.
        """
        # ponytail: per-request only. A cross-request Redis set (no TTL) made repeat queries drop every
        # already-seen product; session_id is kept for API compatibility but unused.
        unique_products: list[RawProduct] = []
        seen: dict[str, str] = {}

        for product in products:
            url_sig = clean_url(product.url)
            compound_key = f"{product.store_name.lower()}:{normalize_title(product.title)}"
            hit = next((k for k in (compound_key, url_sig) if k in seen), None)
            if hit:
                logger.debug("Dedup dropped %r (%s) as dup of %r via %s", product.title[:50], url_sig, seen[hit], hit[:80])
                continue
            seen[compound_key] = seen[url_sig] = product.title[:50]
            unique_products.append(product)

        logger.debug("Dedup kept %d/%d: %s", len(unique_products), len(products), [clean_url(p.url)[:90] for p in unique_products])
        return unique_products


deduplication_engine = DeduplicationEngine()
