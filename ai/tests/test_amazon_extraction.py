import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.dedup import clean_url
from app.services.discovery import DiscoveryWorkerPool, _PAGE_INFO_JS, merge_candidates


@pytest.mark.parametrize("price_html,price,currency", [
    ('<div id="apex_price"><span class="apex-pricetopay-value"><span class="a-offscreen"></span><span aria-hidden="true">IDR9,202,769.55</span></span></div>', 9202769.55, "IDR"),
    ('<div id="corePriceDisplay_desktop_feature_div"><span class="a-price priceToPay"><span class="a-offscreen">$499.99</span></span><span class="a-price a-text-price"><span class="a-offscreen">$999.99</span></span></div>', 499.99, "USD"),
    ('<div id="corePriceDisplay_desktop_feature_div"><span class="a-price priceToPay"><span class="a-offscreen"> </span><span aria-hidden="true"><span>IDR</span><span>9,202,769.</span><span>55</span></span></span></div>', 9202769.55, "IDR"),
    ('<div id="recommendations"><span class="a-price"><span class="a-offscreen">$10.00</span></span></div>', None, None),
])
def test_amazon_dom_price_belongs_to_product_not_related_items(price_html, price, currency):
    html = f'''<title>Amazon.com</title><span id="productTitle">Apple MacBook Pro M1 256GB (Renewed)</span>
    {price_html}<span id="acrPopover" title="4.2 out of 5 stars"></span><a id="acrCustomerReviewText">(1,176)</a>
    <div id="availability"><script>window.internalAvailabilityScript = true;</script>This item cannot be shipped to your selected delivery location.</div>
    <div id="related"><span class="a-price"><span class="a-offscreen">$1.00</span></span></div>'''

    async def run():
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.route("**/*", lambda route: route.fulfill(status=200, content_type="text/html", body=html))
            await page.goto("https://www.amazon.com/dp/B08PPZMDPK")
            info = await page.evaluate(_PAGE_INFO_JS)
            await browser.close()
        fake_page = MagicMock(url="https://www.amazon.com/dp/B08PPZMDPK")
        fake_page.goto = AsyncMock(return_value=MagicMock(status=200))
        fake_page.evaluate = AsyncMock(return_value=info)
        fake_page.wait_for_function = AsyncMock()
        fake_page.close = AsyncMock()
        context = MagicMock(new_page=AsyncMock(return_value=fake_page), close=AsyncMock())
        pool = DiscoveryWorkerPool()
        pool.browser_manager = MagicMock(create_context=AsyncMock(return_value=context))
        return await pool.extract_product_data("https://www.amazon.com/dp/B08PPZMDPK", "macbook m1", default_currency="IDR")

    product = asyncio.run(run())
    if price is None:
        assert product is None
    else:
        assert product is not None
        assert (product.price, product.currency) == (price, currency)
        assert (product.rating, product.review_count) == (4.2, 1176)
        assert "cannot be shipped" in product.description
        assert "internalAvailabilityScript" not in product.description
        assert product.title == "Apple MacBook Pro M1 256GB (Renewed)"


def test_amazon_asin_deduplication_happens_before_fetch():
    a = "https://www.amazon.com/Apple-MacBook/dp/B08PPZMDPK/ref=sr_1_1?keywords=macbook"
    b = "https://www.amazon.com/dp/B08PPZMDPK/ref=cs_sr_dp_loc_1"
    c = "https://www.amazon.com/gp/product/B08PPZMDPK?tag=tracking"
    other = "https://www.amazon.com/dp/B09V31JB9D"
    assert clean_url(a) == clean_url(b) == clean_url(c)
    assert merge_candidates([[a, b], [c, other]], 20) == [a, other]
