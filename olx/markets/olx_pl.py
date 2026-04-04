from __future__ import annotations

from olx.markets.types import MarketPolicy


OLX_PL = MarketPolicy(
    code="olx_pl",
    platform="olx",
    country_code="pl",
    label="OLX PL",
    base_url="https://www.olx.pl",
    home_url="https://www.olx.pl/",
    account_url="https://www.olx.pl/mojekonto/",
    dialogs_url="https://www.olx.pl/mojekonto/answers/",
    allowed_domains=(
        "olx.pl",
        "www.olx.pl",
    ),
    cookie_domains=(
        "olx.pl",
        "www.olx.pl",
        "static.olx.pl",
    ),
    currency_code="PLN",
    currency_symbol="zł",
    decimal_separator=",",
    thousands_separator=" ",
    default_locale="pl-PL",
    price_decimals=2,
    ad_url_prefixes=(
        "https://www.olx.pl/d/",
        "https://www.olx.pl/",
    ),
)