import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.settings import settings
from app.schemas.product import UserSearchQuery
from app.services.discovery import build_search_queries, infer_currency
from app.services.regions import GLOBAL_SITES, resolve_region


@pytest.fixture(autouse=True)
def _clean_settings(monkeypatch) -> None:
    monkeypatch.setattr(settings, "discovery_sites", "")
    monkeypatch.setattr(settings, "serpapi_gl", "")
    monkeypatch.setattr(settings, "serpapi_hl", "")


def test_country_normalized_and_validated() -> None:
    assert UserSearchQuery(query="phone", country=" US ").country == "us"
    assert UserSearchQuery(query="phone").country is None
    for bad in ("usa", "u", "1d", ""):
        with pytest.raises(ValidationError):
            UserSearchQuery(query="phone", country=bad)


def test_region_resolution() -> None:
    us = resolve_region("us")
    assert (us.label, us.gl, us.hl, us.currency) == ("us", "us", "en", "USD") and "bestbuy.com" in us.sites
    idn = resolve_region("id")
    assert (idn.gl, idn.hl, idn.currency) == ("id", "id", "IDR") and "tokopedia.com" in idn.sites
    unk = resolve_region("zz")
    assert (unk.sites, unk.gl, unk.hl, unk.currency) == (GLOBAL_SITES, "zz", "en", "USD")
    none = resolve_region(None)
    assert (none.label, none.sites, none.gl, none.hl, none.currency) == ("global", GLOBAL_SITES, "us", "en", "USD")


def test_discovery_sites_override(monkeypatch) -> None:
    monkeypatch.setattr(settings, "discovery_sites", "Foo.com, bar.com")
    assert resolve_region("us").sites == ["foo.com", "bar.com"] == resolve_region(None).sites


def test_explicit_serpapi_gl_used_without_country(monkeypatch) -> None:
    monkeypatch.setattr(settings, "serpapi_gl", "id")
    monkeypatch.setattr(settings, "serpapi_hl", "id")
    r = resolve_region(None)
    assert (r.gl, r.hl, r.currency) == ("id", "id", "IDR")
    assert resolve_region("us").gl == "us"  # request country wins


def test_build_search_queries_uses_region_sites() -> None:
    qs = build_search_queries("tv", resolve_region("gb").sites)
    assert qs == [("amazon.co.uk", "tv site:amazon.co.uk"), ("ebay.co.uk", "tv site:ebay.co.uk"),
                  ("argos.co.uk", "tv site:argos.co.uk"), ("web", "tv")]


def test_currency_falls_back_to_region_default() -> None:
    assert infer_currency("1299", "example.com", "SGD") == "SGD"
    assert infer_currency("1299", "shop.co.id", "SGD") == "IDR"
