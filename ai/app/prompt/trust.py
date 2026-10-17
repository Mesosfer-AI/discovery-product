"""Trust and fraud verification prompt templates (single product and batch)."""

_TRUST_CRITERIA = """Evaluate:
1. Is the price realistic or suspiciously low (too good to be true)?
2. Is the store known/reputable or obscure with high scam risk?
3. Are the ratings and review volume credible?
4. Are there red flags for counterfeit goods, refurbished hidden as new, or drop-shipping traps?

5. Is this a single purchasable product listing? A homepage, category/collection page, news or review article, or search page is NOT one.
Items with source "google_shopping" come from Google Shopping, an aggregator. If the URL is still a google.com shopping link, judge trust from the store name, price plausibility, rating and review count, and do NOT treat it as a search page.
If it is not a single product listing, or the price is missing or implausible, set is_trusted to false and trust_score below 30."""

TRUST_VERIFICATION_PROMPT = """You are an expert E-Commerce Fraud & Trust Investigator.
Analyze the provided product listing and evaluate seller legitimacy, review authenticity, and pricing risk.

Product Details:
- Title: {title}
- Price: {price} {currency}
- Store: {store_name}
- Rating: {rating}
- Review Count: {review_count}
- Source: {source}
- URL: {url}
- Description: {description}

""" + _TRUST_CRITERIA + """

Return ONLY valid JSON matching this schema:
{{
  "trust_score": <number from 0 to 100>,
  "is_trusted": <true if trust_score >= 60 else false>,
  "trust_verdict": "<short 1-2 sentence verdict>",
  "fraud_flags": ["<flag 1>", "<flag 2>"],
  "sentiment_summary": "<brief summary of buyer safety and product reputation>"
}}
"""

TRUST_BATCH_PROMPT = """You are an expert E-Commerce Fraud & Trust Investigator.
Analyze EACH product listing below independently and evaluate seller legitimacy, review authenticity, and pricing risk.

Products (JSON list; each has an "id"):
{products_json}

""" + _TRUST_CRITERIA + """

Return ONLY valid JSON with exactly one verdict per product id, matching this schema:
{{
  "verdicts": [
    {{
      "id": "<product id from the list>",
      "trust_score": <number from 0 to 100>,
      "is_trusted": <true if trust_score >= 60 else false>,
      "trust_verdict": "<short 1-2 sentence verdict>",
      "fraud_flags": ["<flag 1>", "<flag 2>"],
      "sentiment_summary": "<brief summary of buyer safety and product reputation>"
    }}
  ]
}}
"""
