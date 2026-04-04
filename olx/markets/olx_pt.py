from __future__ import annotations

from olx.markets.types import MarketPolicy


OLX_PT = MarketPolicy(
    code="olx_pt",
    platform="olx",
    country_code="pt",
    label="OLX PT",
    base_url="https://www.olx.pt",
    home_url="https://www.olx.pt/",
    account_url="https://www.olx.pt/myaccount/",
    dialogs_url="https://www.olx.pt/myaccount/answers/",
    allowed_domains=(
        "olx.pt",
        "www.olx.pt",
    ),
    cookie_domains=(
        "olx.pt",
        "www.olx.pt",
        "static.olx.pt",
    ),
    currency_code="EUR",
    currency_symbol="€",
    decimal_separator=",",
    thousands_separator=".",
    default_locale="pt-PT",
    price_decimals=2,
    ad_url_prefixes=(
        "https://www.olx.pt/d/",
        "https://www.olx.pt/",
    ),
)