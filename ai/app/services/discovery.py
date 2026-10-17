import asyncio
import json
import logging
import re
import time
from collections import Counter
from itertools import zip_longest
from typing import Any, Iterable
from urllib.parse import quote_plus, urlparse

from app.config.settings import settings
from app.schemas.product import RawProduct, UserSearchQuery
from app.services.browser import browser_manager
from app.services.dedup import clean_url
from app.services.redis_client import cache_manager
from app.services.regions import DISCOVERY_MARKETPLACES, DISCOVERY_SOURCES, MAJOR_RETAILERS, resolve_region
from app.services.search import SearchBlockedError, SearchUnavailableError, SerpApiError, organic_urls, serpapi_enabled, serpapi_get

logger = logging.getLogger(__name__)

# ponytail: tiny stop list; extend if generic words start letting junk pages through.
_STOP_TOKENS = {"the", "and", "for", "with", "buy", "new", "online", "store", "shop", "official"}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def title_matches_query(title: str, url: str, query: str) -> bool:
    """Lenient relevance check: model-number tokens (with digits) must appear in title/url, else any word overlaps."""
    q = {t for t in _tokens(query) if t not in _STOP_TOKENS}
    digits = {t for t in q if any(c.isdigit() for c in t)}
    if digits:
        return bool(digits & (_tokens(title) | _tokens(url)))
    words = {t for t in q if len(t) >= 3}
    # ponytail: any single shared word passes; tighten to a ratio if loose matches slip through.
    return not words or bool(words & _tokens(title))


def rejection_reason(url: str, title: str | None, price: float | None, query: str) -> str | None:
    """Return why a candidate is not a valid product listing, or None if it passes."""
    if not title or len(title) < 3:
        return "no_title"
    if price is None or price <= 0:
        return "no_price"
    if urlparse(url).path in ("", "/"):
        return "bare_root_url"
    if not title_matches_query(title, url, query):
        return "title_mismatch"
    return None


# ---------------------------------------------------------------------------
# Pure helpers: price/currency parsing, URL pre-filter, JSON-LD, search queries
# ---------------------------------------------------------------------------


def parse_price(raw: Any) -> float | None:
    """Locale-aware price parse: 'Rp 1.299.000' -> 1299000, '1.299,99 €' -> 1299.99, '$1,299.99' -> 1299.99."""
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw) if raw > 0 else None
    if not raw:
        return None
    m = re.search(r"\d[\d.,]*", str(raw))
    if not m:
        return None
    num = m.group(0).rstrip(".,")
    if "." in num and "," in num:
        # The separator that appears last is the decimal one.
        dec, thou = (",", ".") if num.rfind(",") > num.rfind(".") else (".", ",")
        num = num.replace(thou, "").replace(dec, ".")
    else:
        sep = "." if "." in num else "," if "," in num else None
        if sep:
            parts = num.split(sep)
            # ponytail: one separator + exactly 3 trailing digits is read as thousands ("1.299" -> 1299).
            if len(parts) > 2 or len(parts[-1]) == 3:
                num = num.replace(sep, "")
            else:
                num = num.replace(sep, ".")
    try:
        value = float(num)
    except ValueError:
        return None
    return value if value > 0 else None


_CURRENCY_MARKERS = [
    (re.compile(r"\bRp|\bIDR(?=\b|[0-9])", re.I), "IDR"),
    (re.compile(r"€|\bEUR\b"), "EUR"),
    (re.compile(r"£|\bGBP\b"), "GBP"),
    (re.compile(r"\bCNY\b|\bRMB\b"), "CNY"),
    (re.compile(r"\bJPY\b"), "JPY"),
    (re.compile(r"\$|\bUSD\b"), "USD"),
]
_TLD_CURRENCY = {"id": "IDR", "jp": "JPY", "cn": "CNY", "uk": "GBP", "de": "EUR", "fr": "EUR", "it": "EUR", "es": "EUR", "nl": "EUR", "sg": "SGD", "my": "MYR"}


def infer_currency(text: str | None, domain: str = "", default: str = "USD") -> str:
    """Currency from symbol/code in text, else from the domain TLD (.co.id -> IDR), else `default` (region currency)."""
    tld = domain.lower().rstrip(".").rsplit(".", 1)[-1]
    if text:
        if "¥" in text:
            return "CNY" if tld == "cn" else "JPY"
        for pattern, code in _CURRENCY_MARKERS:
            if pattern.search(text):
                return code
    return _TLD_CURRENCY.get(tld, default)


_TEXT_PRICE = re.compile(
    r"(?:Rp\.?|IDR|US\$|USD|EUR|GBP|[$€£¥])\s?\d[\d.,]*|\d[\d.,]*\s?(?:€|EUR)",
    re.I,
)


def price_from_text(body: str, title: str | None, domain: str = "") -> tuple[float | None, str | None]:
    """Body-text fallback: first currency-tagged price after the title occurrence (else from the top)."""
    start = 0
    if title:
        idx = body.find(title[:40])
        start = idx if idx >= 0 else 0
    # ponytail: "near the title" = first match after it; installment/strikethrough prices can still win.
    for chunk in (body[start:start + 4000], body[:4000]):
        m = _TEXT_PRICE.search(chunk)
        if m:
            price = parse_price(m.group(0))
            if price:
                return price, infer_currency(m.group(0), domain)
    return None, None


_BLOCKED_HOSTS = (
    "wikipedia.org", "youtube.com", "youtu.be", "facebook.com", "instagram.com", "twitter.com", "x.com",
    "tiktok.com", "reddit.com", "pinterest.com", "linkedin.com", "quora.com", "kaskus.co.id",
)
# Known marketplaces: only product-detail path shapes pass.
_MARKETPLACE_PRODUCT_PATHS = {
    "amazon.com": re.compile(r"^/(?:[^/]+/)?(?:dp|gp/product)/[A-Z0-9]+(?:/|$)", re.I),
    "alibaba.com": re.compile(r"^/product-detail/[^/]+\.html$", re.I),
    "tokopedia.com": re.compile(
        r"^/(?!(?:p|search|find|discovery|promo|help|blog|top-up|official-store|hot|categories|kategori)/)"
        r"[^/]+/(?!(?:product|etalase|review|info|note)$)[^/]+$"
    ),
    "shopee.co.id": re.compile(r"-i\.\d+\.\d+$|^/product/\d+/\d+$"),
    "blibli.com": re.compile(r"^/p/[^/]+"),
    "lazada.co.id": re.compile(r"^/products/[^/]+"),
    "bukalapak.com": re.compile(r"^/p/[^/]+"),
}
# ponytail: segment keyword list; extend as new listing/content shapes leak through.
_NON_PRODUCT_PATH = re.compile(
    r"/(?:blog|news|berita|artikel|articles?|search|find|list|category|categories|kategori|collections|pages|"
    r"tags?|compare|wiki|forum|reviews?)(?:/|$)|/daftar-",
    re.I,
)


def _host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def prefilter_reason(url: str) -> str | None:
    """Cheap URL-shape check before fetching; returns a skip reason or None for a product-looking URL."""
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":")[0]
    path = parsed.path.rstrip("/")
    if not path:
        return "bare_root"
    if any(_host_matches(host, h) for h in _BLOCKED_HOSTS):
        return "non_shop_site"
    for domain, pattern in _MARKETPLACE_PRODUCT_PATHS.items():
        if _host_matches(host, domain):
            return None if pattern.search(path) else "marketplace_non_product"
    if _NON_PRODUCT_PATH.search(path):
        return "listing_or_content_path"
    return None


# Hosts that block headless Chromium on every product page (checked Oct 2026: amazon.com "continue shopping"
# interstitial, ebay.com HTTP 403, walmart.com /blocked "Robot or human?", tokopedia.com ERR_HTTP2_PROTOCOL_ERROR,
# shopee.co.id /verify/traffic redirect, blibli.com /challenge/landing "unusual activity", sony.co.id HTTP 403
# "Access Denied"). Their pages are not fetched; Google Shopping still covers these stores.
_FETCH_BLOCKED_HOSTS = ("amazon.com", "ebay.com", "walmart.com", "tokopedia.com", "shopee.co.id", "blibli.com", "sony.co.id")
BLOCKED_HOSTS_KEY = "discovery:blocked_hosts"  # persistent Redis set (no TTL) of hosts that block headless fetches


async def load_blocked_hosts() -> frozenset[str]:
    """Seed list plus hosts learned in Redis; one read per request. Never raises."""
    try:
        learned = await cache_manager.get_set(BLOCKED_HOSTS_KEY)
    except Exception:
        learned = set()
    return frozenset(_FETCH_BLOCKED_HOSTS) | learned


async def learn_blocked_host(host: str) -> None:
    """Persist a host that served a bot-block page so later requests skip it; INFO-logged once per new host."""
    host = host.lower().split(":")[0].removeprefix("www.")
    try:
        if host and await cache_manager.is_member_or_add(BLOCKED_HOSTS_KEY, host):
            logger.info("Learned blocked host %s: added to %s", host, BLOCKED_HOSTS_KEY)
    except Exception as exc:
        logger.warning("Could not persist blocked host %s: %s", host, _short_error(exc))


def fetch_blocked(url: str, blocked: Iterable[str] = _FETCH_BLOCKED_HOSTS) -> str | None:
    """'fetch_blocked' for hosts on the blocklist (seed + learned), else None."""
    host = urlparse(url).netloc.lower().split(":")[0]
    return "fetch_blocked" if any(_host_matches(host, h) for h in blocked) else None


_BLOCK_PATH = re.compile(r"/(?:blocked|captcha|verify/traffic|punish|challenge)", re.I)
_BLOCK_TEXT = re.compile(
    r"robot or human|are you a robot|verify you are human|unusual traffic|captcha interception|click the button below to continue shopping",
    re.I,
)


def is_blocked_page(status: int | None, final_url: str, title: str, body: str) -> bool:
    """Bot-block / CAPTCHA interstitial instead of the product page (HTTP status, redirect path, or page text)."""
    if status in (403, 429):
        return True
    if _BLOCK_PATH.search(urlparse(final_url).path):
        return True
    # ponytail: phrase list from pages seen live; extend when a new interstitial shows up as no_price.
    return bool(_BLOCK_TEXT.search(f"{title} {body[:500]}"))


# Site-specific price evidence, verified on live pages: lazada.co.id ships a JSON-LD Product without a price and
# renders no price for headless Chromium, but embeds "pdt_price":"Rp4.799.000" (product tracking data) in a script.
_SITE_PRICE = {"lazada.co.id": re.compile(r'pdt_price\\?"\s*:\s*\\?"([^"\\]+)')}


def site_price(domain: str, html: str) -> tuple[float | None, str | None]:
    """Price/currency from a site-specific embedded field; (None, None) when the site has no rule or no match."""
    for site, pattern in _SITE_PRICE.items():
        if _host_matches(domain, site):
            m = pattern.search(html)
            price = parse_price(m.group(1)) if m else None
            if price:
                return price, infer_currency(m.group(1), domain)
    return None, None


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _ld_nodes(data: Any):
    """Yield every dict node, descending into lists, @graph and ProductGroup variants."""
    for item in _as_list(data):
        if isinstance(item, dict):
            yield item
            for key in ("@graph", "hasVariant"):
                if key in item:
                    yield from _ld_nodes(item[key])


def _image(value: Any) -> str | None:
    value = _as_list(value)[0] if _as_list(value) else None
    if isinstance(value, dict):
        value = value.get("url") or value.get("contentUrl")
    return value if isinstance(value, str) else None


def _offer_price(offers: Any) -> tuple[float | None, str | None]:
    for offer in _as_list(offers):
        if not isinstance(offer, dict):
            continue
        spec = next((s for s in _as_list(offer.get("priceSpecification")) if isinstance(s, dict)), {})
        price = parse_price(offer.get("price") or offer.get("lowPrice") or spec.get("price"))
        if price:
            return price, offer.get("priceCurrency") or spec.get("priceCurrency")
        if offer.get("offers"):  # AggregateOffer with nested offers
            price, cur = _offer_price(offer["offers"])
            if price:
                return price, cur or offer.get("priceCurrency")
    return None, None


def parse_json_ld(scripts: list[str]) -> dict[str, Any]:
    """Merge schema.org Product/ProductGroup fields from ld+json script bodies (first non-empty value wins)."""
    out: dict[str, Any] = {}

    def put(key: str, value: Any) -> None:
        if value not in (None, "") and out.get(key) is None:
            out[key] = value

    for raw in scripts:
        try:
            data = json.loads(raw, strict=False)
        except (TypeError, ValueError) as exc:
            logger.debug("JSON-LD parse error: %r", exc)
            continue
        for node in _ld_nodes(data):
            types = {str(t) for t in _as_list(node.get("@type"))}
            if not types & {"Product", "ProductGroup"}:
                continue
            put("title", node.get("name") if isinstance(node.get("name"), str) else None)
            put("image_url", _image(node.get("image")))
            put("description", node.get("description") if isinstance(node.get("description"), str) else None)
            price, currency = _offer_price(node.get("offers"))
            if price and out.get("price") is None:
                out["price"], out["currency"] = price, currency
            agg = node.get("aggregateRating")
            if isinstance(agg, dict):
                try:
                    put("rating", float(agg["ratingValue"]) if agg.get("ratingValue") else None)
                    cnt = agg.get("reviewCount") or agg.get("ratingCount")
                    put("review_count", int(float(str(cnt).replace(",", ""))) if cnt else None)
                except (TypeError, ValueError):
                    pass
    return out


def shopping_to_products(
    data: dict[str, Any], query: str, drops: Counter | None = None, default_currency: str = "USD"
) -> list[RawProduct]:
    """Map google_shopping results to candidates, run through the same validity gate as extracted pages."""
    out: list[RawProduct] = []
    for item in data.get("shopping_results", []):
        # ponytail: if SerpAPI gives no merchant `link`, we keep the google.com product_link (not a store page).
        url = item.get("link") or item.get("product_link") or ""
        title = item.get("title")
        price = parse_price(item.get("extracted_price")) or parse_price(item.get("price"))
        reason = rejection_reason(url, title, price, query) if url else "no_url"
        if reason:
            logger.info("Dropped shopping item %r: %s", title, reason)
            if drops is not None:
                drops[reason] += 1
            continue
        store = item.get("source") or urlparse(url).netloc.replace("www.", "")
        reviews = item.get("reviews")
        out.append(RawProduct(
            id=RawProduct.generate_id(url, title, store),
            title=title[:180],
            price=price,
            currency=infer_currency(item.get("price"), urlparse(url).netloc, default_currency),
            url=url,
            image_url=item.get("thumbnail"),
            store_name=store,
            rating=item.get("rating"),
            review_count=int(reviews) if isinstance(reviews, (int, float)) else None,
            description=(item.get("snippet") or "")[:300],
            source="google_shopping",
            offers_token=item.get("immersive_product_page_token"),
        ))
    return out


def pick_offer(stores: list[dict[str, Any]], sites: list[str] | tuple[str, ...] = ()) -> dict[str, Any] | None:
    """Best merchant offer: well-known retailer/marketplace first, then one with rating/reviews, then the cheapest.

    `sites` are the region's marketplace domains; offers without an http link are never picked.
    """
    known = {s.split(".")[0] for s in sites} | MAJOR_RETAILERS
    # ponytail: label match on host / squashed store name; a curated domain list per region if this misfires.

    def tier(s: dict[str, Any]) -> int:
        host_labels = set(urlparse(s["link"]).netloc.lower().split("."))
        name = re.sub(r"[^a-z0-9]", "", str(s.get("name", "")).lower())
        if host_labels & known or any(name.startswith(k) for k in known):
            return 0
        return 1 if s.get("rating") or s.get("reviews") else 2

    def price(s: dict[str, Any]) -> float:
        return parse_price(s.get("extracted_price")) or parse_price(s.get("price")) or float("inf")

    offers = [s for s in stores if str(s.get("link", "")).startswith("http")]
    return min(offers, key=lambda s: (tier(s), price(s)), default=None)


def is_google_link(url: str) -> bool:
    host = urlparse(url).netloc.lower().split(":")[0]
    return bool(re.search(r"(?:^|\.)google\.[a-z.]+$", host))


def drop_google_links(products: list[RawProduct]) -> list[RawProduct]:
    """Remove candidates still pointing at a google.com shopping/search page (no merchant link resolved)."""
    kept = [p for p in products if not is_google_link(p.url)]
    logger.info("Dropped %d candidates with unresolved google.com links; %d left", len(products) - len(kept), len(kept))
    return kept


async def resolve_store_links(
    products: list[RawProduct], gl: str, hl: str, top_n: int | None = None, need: int = 0,
    sites: list[str] | tuple[str, ...] = (),
) -> list[RawProduct]:
    """Replace google.com links of shopping candidates with merchant offer links (in place, order kept).

    Resolves the first `top_n`; if fewer than `need` candidates then have a non-google link, resolves more,
    never exceeding SERPAPI_RESOLVE_MAX SerpAPI calls in total.
    """
    top_n = settings.serpapi_resolve_top_n if top_n is None else top_n
    cap = max(settings.serpapi_resolve_max, top_n)
    pending = [p for p in products if p.source == "google_shopping" and p.offers_token and is_google_link(p.url)]
    if top_n <= 0 or not pending or not serpapi_enabled():
        return products
    sem = asyncio.Semaphore(settings.discovery_search_concurrency)

    async def resolve(p: RawProduct) -> bool:
        try:
            async with sem:
                data = await serpapi_get("google_immersive_product", "", gl, hl, page_token=p.offers_token)
        except SerpApiError as exc:
            logger.warning("Offer resolution failed for %r, keeping %s: %s", p.title[:60], urlparse(p.url).netloc, exc)
            return False
        stores = data.get("product_results", {}).get("stores", [])
        if sites:
            stores = [s for s in stores if any(_host_matches(urlparse(s.get("link", "")).hostname or "", site) for site in sites)]
        offer = pick_offer(stores, sites)
        if not offer:
            return False
        p.url = offer["link"]
        p.store_name = offer.get("name") or p.store_name
        price = parse_price(offer.get("extracted_price")) or parse_price(offer.get("price"))
        if price:
            p.price = price
            p.currency = infer_currency(offer.get("price"), urlparse(p.url).netloc, p.currency)
        if isinstance(offer.get("rating"), (int, float)):
            p.rating = offer["rating"]
        return True

    batch = pending[:top_n]
    ok = sum(await asyncio.gather(*(resolve(p) for p in batch)))
    used = len(batch)
    deficit = need - sum(not is_google_link(p.url) for p in products)
    backfill = pending[used:used + max(0, min(deficit, cap - used))]
    if backfill:
        ok += sum(await asyncio.gather(*(resolve(p) for p in backfill)))
        used += len(backfill)
    logger.info(
        "Resolved merchant links for %d/%d shopping candidates (SerpAPI calls %d: top %d + backfill %d, cap %d, need %d)",
        ok, used, used, len(batch), len(backfill), cap, need,
    )
    return products


def build_search_queries(
    query: str, sites: list[str], preferred_stores: list[str] | None = None, blocked: Iterable[str] = ()
) -> list[tuple[str, str]]:
    """(source, search query) pairs: one `site:` query per marketplace + the plain query.

    preferred_stores (names like "tokopedia" or domains) replace the default site list when they resolve.
    Sites on the `blocked` list get no `site:` query (their pages can't be fetched, so the search would be wasted).
    """
    preferred: list[str] = []
    for store in preferred_stores or []:
        s = store.strip().lower()
        if not s:
            continue
        if "." in s:
            domain = urlparse(s if "//" in s else "//" + s).netloc.removeprefix("www.")
        else:
            key = s.replace(" ", "")
            domain = next((site for site in sites if site.split(".")[0] == key), None)
        if domain and domain not in preferred:
            preferred.append(domain)
    targets = [t for t in (preferred or sites) if not any(_host_matches(t, b) for b in blocked)]
    return [(site, f"{query} site:{site}") for site in targets] + [("web", query)]


def merge_candidates(groups: list[list[str]], limit: int) -> list[str]:
    """Round-robin interleave per-source lists so every source gets a share; dedupe by host+path."""
    seen: set[str] = set()
    out: list[str] = []
    for row in zip_longest(*groups):
        for url in row:
            if url is None:
                continue
            p = urlparse(url)
            key = clean_url(url) if _host_matches(p.hostname or "", "amazon.com") else p.netloc.lower().removeprefix("www.") + p.path.rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            out.append(url)
            if len(out) >= limit:
                return out
    return out


# One round trip for everything optional on the page: missing tags yield null instead of waiting.
_PAGE_INFO_JS = """() => {
  const q = s => { const e = document.querySelector(s); return e ? (e.getAttribute('content') || e.textContent || '').trim() || null : null; };
  const price = s => q(s + ' .a-offscreen') || q(s + ' [aria-hidden="true"]');
  const amazon = (location.hostname === 'amazon.com' || location.hostname.endsWith('.amazon.com')) && document.querySelector('#productTitle');
  return {
    title: document.title || '',
    og_title: q('meta[property="og:title"]'),
    og_image: q('meta[property="og:image"]'),
    og_description: q('meta[property="og:description"]') || q('meta[name="description"]'),
    meta_price: q('meta[property="product:price:amount"]') || q('meta[property="og:price:amount"]') || q('[itemprop="price"]'),
    meta_currency: q('meta[property="product:price:currency"]') || q('meta[property="og:price:currency"]') || q('[itemprop="priceCurrency"]'),
    amazon_title: amazon ? q('#productTitle') : null,
    amazon_price: amazon ? (price('#corePriceDisplay_desktop_feature_div .priceToPay') || price('#corePrice_feature_div .priceToPay') || price('#apex_desktop .priceToPay') || price('#apex_price .apex-pricetopay-value') || q('#priceblock_ourprice') || q('#priceblock_dealprice')) : null,
    amazon_rating: amazon ? parseFloat(document.querySelector('#acrPopover')?.getAttribute('title') || '') || null : null,
    amazon_reviews: amazon ? Number((q('#acrCustomerReviewText') || '').replace(/[^0-9]/g, '')) || null : null,
    amazon_availability: amazon ? document.querySelector('#availability')?.innerText?.trim() || null : null,
    ld: [...document.querySelectorAll('script[type="application/ld+json"]')].map(e => e.textContent),
    body: document.body ? document.body.innerText.slice(0, 20000) : '',
  };
}"""
# Signals that the product price has rendered (JS-heavy pages inject these after domcontentloaded).
_PRODUCT_READY_JS = """() => !!document.querySelector('[itemprop="price"], meta[property="product:price:amount"], meta[property="og:price:amount"]')
  || [...document.querySelectorAll('#apex_price .apex-pricetopay-value, #corePriceDisplay_desktop_feature_div .priceToPay, #corePrice_feature_div .priceToPay, #apex_desktop .priceToPay, #priceblock_ourprice, #priceblock_dealprice')].some(e => /[0-9]/.test(e.textContent))
  || [...document.querySelectorAll('script[type="application/ld+json"]')].some(s => /"Product/.test(s.textContent) && /"(?:low)?[pP]rice"/.test(s.textContent))"""


def _strip_title_suffix(title: str) -> str:
    for sep in (" | ", " - "):
        if sep in title:
            return title.split(sep)[0].strip()
    return title.strip()


def _short_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc).splitlines()[0][:120] if str(exc) else ''}"


class DiscoveryWorkerPool:
    """Stage 1: concurrent workers searching marketplaces and extracting product candidates."""

    def __init__(self, concurrency: int = 20) -> None:
        self.semaphore = asyncio.Semaphore(concurrency)
        self.browser_manager = browser_manager
        self._search_lock = asyncio.Lock()
        self._last_search_at = 0.0

    async def search_candidate_urls(self, query: str, max_links: int = 25) -> list[str]:
        """Open the marketplace search page directly, with pacing and a ten-minute URL cache."""
        text, separator, site = query.rpartition(" site:")
        search_urls = {
            "shopee.co.id": "https://shopee.co.id/search?keyword=",
            "tokopedia.com": "https://www.tokopedia.com/search?st=product&q=",
            "alibaba.com": "https://www.alibaba.com/trade/search?SearchText=",
            "amazon.com": "https://www.amazon.com/s?k=",
        }
        if not separator or site not in search_urls:
            raise SearchUnavailableError("Unsupported marketplace search")
        async with self._search_lock:
            key = f"search:marketplace:v3:{query}"
            cached = await cache_manager.get_json(key)
            # The timestamp also expires entries in the cache manager's in-memory fallback.
            if isinstance(cached, dict) and time.time() - cached.get("created_at", 0) < 600:
                return cached["urls"][:max_links]
            delay = 3 - (time.monotonic() - self._last_search_at)
            if delay > 0:
                await asyncio.sleep(delay)
            context = await self.browser_manager.create_context()
            page = await context.new_page()
            page.set_default_timeout(settings.discovery_page_timeout_ms)
            urls: list[str] = []
            try:
                response = await page.goto(search_urls[site] + quote_plus(text),
                                           timeout=settings.discovery_page_timeout_ms, wait_until="domcontentloaded")
                if response.status in {403, 429}:
                    raise SearchBlockedError(f"{site} search is temporarily blocked")
                if response.status >= 400:
                    raise SearchUnavailableError(f"{site} search is unavailable")
                try:
                    await page.wait_for_selector('a[href*="/dp/"], a[href*="/gp/product/"], a[href*="/product-detail/"], a[href*="-i."], a[href*="/product/"], a[href*="tokopedia.com/"]',
                                                 timeout=settings.discovery_render_wait_ms)
                except Exception:
                    pass  # Extract available links after the capped render wait.
                title, body = await page.title(), await page.locator("body").inner_text()
                if is_blocked_page(response.status, str(page.url), title, body):
                    raise SearchBlockedError(f"{site} search is temporarily blocked")
                raw_links = await page.eval_on_selector_all("a[href]", "elements => elements.map(e => e.href)")
                for link in raw_links:
                    parsed = urlparse(link)
                    if parsed.scheme in {"http", "https"} and _host_matches(parsed.hostname or "", site):
                        if prefilter_reason(link) is None and link not in urls:
                            if site == "amazon.com":
                                canonical = clean_url(link)
                                if canonical.startswith("amazon.com/dp/"):
                                    link = "https://www." + canonical
                            if link in urls:
                                continue
                            urls.append(link)
                if urls:
                    await cache_manager.set_json(key, {"created_at": time.time(), "urls": urls}, ttl_seconds=600)
                elif not re.search(r"no results|no products|tidak (?:ada|ditemukan)|produk tidak ditemukan|0 results", body, re.I):
                    raise SearchUnavailableError(f"{site} search did not expose product links")
                logger.info("Direct search %r on %s: %d product links", text, site, len(urls))
                return urls[:max_links]
            except SearchUnavailableError:
                raise
            except Exception as exc:
                logger.warning("Direct search failed for %r on %s: %s", text, site, _short_error(exc))
                raise SearchUnavailableError(f"{site} search is unavailable") from exc
            finally:
                self._last_search_at = time.monotonic()
                await page.close()
                await context.close()

    async def extract_product_data(
        self, url: str, query: str = "", drops: Counter | None = None, default_currency: str = "USD"
    ) -> RawProduct | None:
        """Single worker: Visit URL and extract structured product details."""
        async with self.semaphore:
            context = await self.browser_manager.create_context()
            page = await context.new_page()
            # Any stray locator call fails fast instead of Playwright's 30s default.
            page.set_default_timeout(settings.discovery_page_timeout_ms)
            domain = urlparse(url).netloc.replace("www.", "")

            try:
                resp = await page.goto(url, timeout=settings.discovery_page_timeout_ms, wait_until="domcontentloaded")
                info = await page.evaluate(_PAGE_INFO_JS)
                status = getattr(resp, "status", None)
                if is_blocked_page(status if isinstance(status, int) else None, str(page.url), info["title"], info["body"]):
                    logger.info("Dropped %s: blocked (bot check / CAPTCHA page)", url)
                    if status != 429:  # rate limiting is transient: skip this page, don't persist the host
                        await learn_blocked_host(domain)
                    if drops is not None:
                        drops["blocked"] += 1
                    return None
                try:
                    await page.wait_for_function(_PRODUCT_READY_JS, timeout=settings.discovery_render_wait_ms)
                except Exception:
                    pass  # ponytail: short capped wait for JS-rendered data; extract whatever is there.
                info = await page.evaluate(_PAGE_INFO_JS)

                ld = parse_json_ld(info["ld"])
                title = ld.get("title") or info.get("amazon_title") or info["og_title"] or _strip_title_suffix(info["title"])
                price, currency, via = ld.get("price"), ld.get("currency"), "json_ld"
                if price is None and info["meta_price"]:
                    price, currency, via = parse_price(info["meta_price"]), info["meta_currency"], "meta"
                if price is None and info.get("amazon_price"):
                    price, currency, via = parse_price(info["amazon_price"]), infer_currency(info["amazon_price"], domain), "amazon_dom"
                if price is None and any(_host_matches(domain, s) for s in _SITE_PRICE):
                    price, currency = site_price(domain, await page.content())
                    via = "site"
                if price is None:
                    price, currency = price_from_text(info["body"], title, domain)
                    via = "text"
                    if price is not None:
                        # Body text alone is too weak (e.g. a UN page passed as "100 USD"): require structured data.
                        logger.info("Dropped %s: no_structured_price", url)
                        if drops is not None:
                            drops["no_structured_price"] += 1
                        return None
                if price is not None and not currency:
                    currency = infer_currency(info["meta_price"], domain, default_currency)

                reason = rejection_reason(url, title, price, query)
                if reason:
                    logger.info("Dropped %s: %s (json_ld=%s)", url, reason, bool(ld))
                    if drops is not None:
                        drops[reason] += 1
                    return None

                logger.debug("Extracted %s via %s: %s %s", url, via, price, currency)
                product_id = RawProduct.generate_id(url, title, domain)
                return RawProduct(
                    id=product_id,
                    title=title[:180],
                    price=price,
                    currency=str(currency).upper()[:3],
                    url=url,
                    image_url=ld.get("image_url") or info["og_image"],
                    store_name=domain.capitalize(),
                    rating=ld.get("rating") or info.get("amazon_rating"),
                    review_count=ld.get("review_count") or info.get("amazon_reviews"),
                    description=" ".join(filter(None, [info.get("amazon_availability"), ld.get("description") or info["og_description"]]))[:300],
                    source=domain,
                )
            except Exception as exc:
                logger.warning("Page error on %s: %s", url, _short_error(exc))
                if drops is not None:
                    drops["page_error"] += 1
                return None
            finally:
                await page.close()
                await context.close()

    async def discover(self, search_query: UserSearchQuery) -> list[RawProduct]:
        """Stage 1: marketplace-targeted searches, URL pre-filter, then parallel page extraction."""
        query = search_query.query
        region = resolve_region(search_query.country)
        # Explicit marketplace scope retries previously blocked stores; page CAPTCHA checks still apply.
        queries = [(site, q) for site, q in build_search_queries(query, DISCOVERY_SOURCES, search_query.preferred_stores)
                   if site in DISCOVERY_SOURCES]
        if not queries:
            queries = [(site, f"{query} site:{site}") for site in DISCOVERY_SOURCES]
        search_sem = asyncio.Semaphore(settings.discovery_search_concurrency)
        drops: Counter = Counter()
        target = max(settings.discovery_max_candidates, search_query.limit * 5, 15)

        shopping: list[RawProduct] = []
        results: list[list[str]] | None = None
        provider, n_shop_raw = "marketplace", 0
        if serpapi_enabled():
            async def sa(engine: str, q: str) -> dict[str, Any] | None:
                async with search_sem:
                    try:
                        return await serpapi_get(engine, q, region.gl, region.hl)
                    except SerpApiError as exc:
                        logger.warning("SerpAPI source failed for %r (%s): %s", q, engine, exc)
                        return None

            shop_data, *web_data = await asyncio.gather(
                sa("google_shopping", query), *(sa("google", q) for _, q in queries)
            )
            if shop_data is not None or any(d is not None for d in web_data):
                shop_data = shop_data or {}
                n_shop_raw = len(shop_data.get("shopping_results", []))
                shopping = [p for p in shopping_to_products(shop_data, query, drops, region.currency)
                            if (is_google_link(p.url) and p.offers_token)
                            or any(_host_matches(urlparse(p.url).hostname or "", site) for site, _ in queries)]
                results = [organic_urls(d) if d is not None else [] for d in web_data]
                provider = "serpapi"
            else:
                logger.warning("All SerpAPI sources failed for %r, falling back to direct marketplace search", query)

        if results is None:
            queries = [(site, q) for site, q in queries if site in DISCOVERY_MARKETPLACES]
            results = []
            failures: list[SearchUnavailableError] = []
            for _, q in queries:
                try:
                    results.append(await self.search_candidate_urls(q))
                except SearchUnavailableError as exc:
                    logger.warning("Marketplace search skipped: %s", exc)
                    failures.append(exc)
                    results.append([])
            if failures and not any(results):
                raise next((exc for exc in failures if isinstance(exc, SearchBlockedError)), failures[0])

        skips: Counter = Counter()
        groups: list[list[str]] = []
        per_source: dict[str, str] = {}
        for (source, _), links in zip(queries, results):
            kept = []
            for link in links:
                if not any(_host_matches(urlparse(link).hostname or "", site) for site, _ in queries):
                    skips["outside_marketplace_scope"] += 1
                    continue
                reason = prefilter_reason(link)
                if reason:
                    skips[reason] += 1
                else:
                    kept.append(link)
            groups.append(kept)
            per_source[source] = f"{len(kept)}/{len(links)}"

        shopping_cap = int(target * settings.discovery_shopping_share)
        candidate_urls = merge_candidates(groups, max(target - min(len(shopping), shopping_cap), 0))
        logger.info(
            "Search %r via %s [region=%s gl=%s hl=%s sites=%s]: shopping %d kept/%d found; "
            "web links kept/found per source %s; prefilter skips %s; %d web candidates",
            query, provider, region.label, region.gl, region.hl, [s for s, _ in queries],
            len(shopping), n_shop_raw, per_source, dict(skips), len(candidate_urls),
        )
        if not candidate_urls and not shopping:
            logger.warning("No candidate links for %r (possible block/CAPTCHA)", query)
            return []

        # ponytail: prices stay in their native currency; budget_max (query.currency) is not FX-converted,
        # so mixed-currency candidates can be compared wrongly downstream. Add conversion if that bites.
        tasks = [self.extract_product_data(url, query, drops, region.currency) for url in candidate_urls]
        extracted = [p for p in await asyncio.gather(*tasks) if p is not None]
        # Shopping fills up to its share; leftover slots (web yielded less than reserved) are backfilled with more shopping.
        kept_shopping = min(len(shopping), max(shopping_cap, target - len(extracted)))
        products = shopping[:kept_shopping] + extracted
        logger.debug("Shopping candidates: %s", [clean_url(p.url)[:90] for p in shopping])
        logger.debug("Web candidates: %s", [p.url[:90] for p in extracted])
        logger.info(
            "Extraction %r: %d ok / %d fetched; %d survived gate overall (shopping %d + web %d); drops %s",
            query, len(extracted), len(candidate_urls), len(products), kept_shopping, len(extracted), dict(drops),
        )
        return products


discovery_pool = DiscoveryWorkerPool(concurrency=settings.discovery_concurrency)
