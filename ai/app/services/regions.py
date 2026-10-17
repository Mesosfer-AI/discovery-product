from dataclasses import dataclass

from app.config.settings import settings

GLOBAL_SITES = ["amazon.com", "ebay.com", "aliexpress.com", "walmart.com"]
DISCOVERY_MARKETPLACES = ["shopee.co.id", "tokopedia.com", "alibaba.com", "amazon.com"]
DISCOVERY_SOURCES = DISCOVERY_MARKETPLACES + ["erafone.com", "digimap.co.id", "blibli.com"]
# ponytail: small hand-picked table; unknown countries use GLOBAL_SITES. Add rows as markets are needed.
REGION_SITES = {
    "us": ["amazon.com", "ebay.com", "walmart.com", "bestbuy.com"],
    "gb": ["amazon.co.uk", "ebay.co.uk", "argos.co.uk"],
    "id": ["tokopedia.com", "shopee.co.id", "blibli.com", "lazada.co.id"],
    "sg": ["shopee.sg", "lazada.sg", "amazon.sg"],
    "in": ["amazon.in", "flipkart.com"],
}
# Host/name labels of large retailers trusted for offer selection in any region (plus the region's own sites).
MAJOR_RETAILERS = {"amazon", "ebay", "walmart", "bestbuy", "target", "costco", "newegg", "bhphotovideo", "aliexpress"}
REGION_CURRENCY = {
    "us": "USD", "gb": "GBP", "id": "IDR", "sg": "SGD", "in": "INR",
    "de": "EUR", "fr": "EUR", "it": "EUR", "es": "EUR", "nl": "EUR",
}
REGION_HL = {"us": "en", "gb": "en", "id": "id", "sg": "en", "in": "en"}


@dataclass(frozen=True)
class Region:
    label: str  # country code, or "global" when the request carried none
    sites: list[str]
    gl: str
    hl: str
    currency: str


def resolve_region(country: str | None) -> Region:
    """Sites / Google gl+hl / fallback currency for a request country (already lowercase alpha-2) or None."""
    # DISCOVERY_SITES (if set) overrides the region site list.
    override = [s.strip().lower() for s in settings.discovery_sites.split(",") if s.strip()]
    sites = override or REGION_SITES.get(country or "", GLOBAL_SITES)
    if country:
        gl, hl = country, REGION_HL.get(country, "en")
    else:
        # Backwards compat: explicit SERPAPI_GL / SERPAPI_HL apply only when the request has no country.
        gl, hl = settings.serpapi_gl.lower() or "us", settings.serpapi_hl.lower() or "en"
    currency = REGION_CURRENCY.get(country or settings.serpapi_gl.lower(), "USD")
    return Region(country or "global", sites, gl, hl, currency)
