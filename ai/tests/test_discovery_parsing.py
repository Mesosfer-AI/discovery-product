import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.discovery import (
    build_search_queries,
    infer_currency,
    merge_candidates,
    parse_json_ld,
    parse_price,
    prefilter_reason,
    price_from_text,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Rp 1.299.000", 1299000),
        ("Rp1.299.000,00", 1299000),
        ("IDR 24.999.000", 24999000),
        ("$1,299.99", 1299.99),
        ("1.299,99 €", 1299.99),
        ("1299", 1299),
        ("1299.5", 1299.5),
        ("4999000.00", 4999000),
        (349.99, 349.99),
        ("Rp 0", None),
        ("", None),
        (None, None),
        ("call us", None),
    ],
)
def test_parse_price(raw, expected) -> None:
    assert parse_price(raw) == expected


def test_infer_currency() -> None:
    assert infer_currency("Rp 1.299.000") == "IDR"
    assert infer_currency("IDR 24.999.000") == "IDR"
    assert infer_currency("$1,299.99") == "USD"
    assert infer_currency("1.299,99 €") == "EUR"
    assert infer_currency("£499") == "GBP"
    assert infer_currency("¥45,000", "shop.jp") == "JPY"
    assert infer_currency("¥3,000", "jd.cn") == "CNY"
    assert infer_currency("1299000", "tokopedia.co.id") == "IDR"
    assert infer_currency(None, "blibli.id") == "IDR"
    assert infer_currency(None, "example.com") == "USD"


def test_price_from_text_prefers_after_title() -> None:
    body = "Promo Rp 50.000 cashback\n" + "x" * 50 + "\nSony WH-1000XM5 Black\nRp 4.999.000\n"
    assert price_from_text(body, "Sony WH-1000XM5 Black", "tokopedia.com") == (4999000, "IDR")
    assert price_from_text("Price: $1,299.99", "Missing title", "a.com") == (1299.99, "USD")
    assert price_from_text("no prices here", "t", "a.com") == (None, None)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.tokopedia.com/sonyofficial/sony-wh-1000xm5-wireless-noise-cancelling-black",
        "https://shopee.co.id/Sony-WH-1000XM5-Headphone-i.123456.7890123",
        "https://shopee.co.id/product/123456/7890123",
        "https://www.blibli.com/p/sony-wh-1000xm5/ps--SOI-60030-01234",
        "https://www.lazada.co.id/products/sony-wh-1000xm5-i1234567-s2345678.html",
        "https://www.bukalapak.com/p/elektronik/audio/abc123-jual-sony-wh-1000xm5",
        "https://www.someshop.com/products/sony-wh-1000xm5",
    ],
)
def test_prefilter_accepts_product_urls(url) -> None:
    assert prefilter_reason(url) is None


@pytest.mark.parametrize(
    "url,reason",
    [
        ("https://www.sonyliv.com/", "bare_root"),
        ("https://electronics.sony.com/", "bare_root"),
        ("https://ibox.co.id/", "bare_root"),
        ("https://en.wikipedia.org/wiki/Sony", "non_shop_site"),
        ("https://www.youtube.com/watch?v=abc", "non_shop_site"),
        ("https://shopee.co.id/sonyofficial", "marketplace_non_product"),
        ("https://shopee.co.id/list/Apple/iPhone", "marketplace_non_product"),
        ("https://www.tokopedia.com/sonyofficial", "marketplace_non_product"),
        ("https://www.tokopedia.com/search?q=iphone", "marketplace_non_product"),
        ("https://www.tokopedia.com/p/handphone-tablet/handphone", "marketplace_non_product"),
        ("https://www.tokopedia.com/sonyofficial/product", "marketplace_non_product"),
        ("https://ibox.co.id/pages/lihat-semua-iphone-810", "listing_or_content_path"),
        ("https://erablue.id/blog/daftar-harga-iphone-1571793", "listing_or_content_path"),
        ("https://www.digimap.co.id/pages/view-all-iphone", "listing_or_content_path"),
        ("https://www.91mobiles.com/id/daftar-hp-apple", "listing_or_content_path"),
    ],
)
def test_prefilter_rejects_non_product_urls(url, reason) -> None:
    assert prefilter_reason(url) == reason


def test_json_ld_graph_and_offers_list() -> None:
    doc = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "Organization", "name": "Shop"},
            {
                "@type": ["Product"],
                "name": "Sony WH-1000XM5",
                "image": [{"url": "https://img/1.jpg"}],
                "offers": [{"@type": "Offer", "price": "4999000", "priceCurrency": "IDR"}],
                "aggregateRating": {"ratingValue": "4.8", "reviewCount": "1,234"},
            },
        ],
    }
    out = parse_json_ld(["not json", json.dumps(doc)])
    assert out["title"] == "Sony WH-1000XM5"
    assert (out["price"], out["currency"]) == (4999000, "IDR")
    assert out["image_url"] == "https://img/1.jpg"
    assert (out["rating"], out["review_count"]) == (4.8, 1234)


def test_json_ld_aggregate_offer_and_price_specification() -> None:
    agg = {"@type": "ProductGroup", "name": "iPhone 15", "image": "https://img/a.jpg",
           "offers": {"@type": "AggregateOffer", "lowPrice": 13999000, "priceCurrency": "IDR"}}
    assert parse_json_ld([json.dumps([agg])])["price"] == 13999000
    spec = {"@type": "Product", "name": "X",
            "offers": {"@type": "Offer", "priceSpecification": [{"price": "1.299,99", "priceCurrency": "EUR"}]}}
    out = parse_json_ld([json.dumps(spec)])
    assert (out["price"], out["currency"]) == (1299.99, "EUR")
    variants = {"@type": "ProductGroup", "name": "G", "hasVariant": [{"@type": "Product", "offers": {"price": "10"}}]}
    assert parse_json_ld([json.dumps(variants)])["price"] == 10


def test_build_search_queries() -> None:
    sites = ["tokopedia.com", "shopee.co.id", "blibli.com"]
    assert build_search_queries("iphone 15", sites) == [
        ("tokopedia.com", "iphone 15 site:tokopedia.com"),
        ("shopee.co.id", "iphone 15 site:shopee.co.id"),
        ("blibli.com", "iphone 15 site:blibli.com"),
        ("web", "iphone 15"),
    ]
    pref = build_search_queries("iphone 15", sites, ["Shopee", "https://www.ibox.co.id/", "unknownstore"])
    assert pref == [
        ("shopee.co.id", "iphone 15 site:shopee.co.id"),
        ("ibox.co.id", "iphone 15 site:ibox.co.id"),
        ("web", "iphone 15"),
    ]
    assert build_search_queries("x", sites, ["unknownstore"])[-1] == ("web", "x")
    assert len(build_search_queries("x", sites, ["unknownstore"])) == 4


def test_merge_candidates_interleaves_and_dedupes() -> None:
    a = ["https://a.com/1", "https://a.com/2", "https://a.com/3"]
    b = ["https://b.com/1", "https://www.a.com/1/"]
    assert merge_candidates([a, b], 10) == ["https://a.com/1", "https://b.com/1", "https://a.com/2", "https://a.com/3"]
    assert merge_candidates([a, b], 2) == ["https://a.com/1", "https://b.com/1"]
