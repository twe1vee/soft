from __future__ import annotations

from urllib.parse import urlparse

from olx.markets.registry import get_market_policy

def get_market_home_url(market_code: str | None = None) -> str:
    return get_market_policy(market_code).home_url


def get_market_account_url(market_code: str | None = None) -> str:
    return get_market_policy(market_code).account_url


def get_market_dialogs_url(market_code: str | None = None) -> str:
    return get_market_policy(market_code).dialogs_url


def get_market_base_url(market_code: str | None = None) -> str:
    return get_market_policy(market_code).base_url


def is_market_url(url: str | None, market_code: str | None = None) -> bool:
    return get_market_policy(market_code).is_market_url(url)


def is_market_domain(domain: str | None, market_code: str | None = None) -> bool:
    return get_market_policy(market_code).is_allowed_domain(domain)


def is_market_cookie_domain(domain: str | None, market_code: str | None = None) -> bool:
    return get_market_policy(market_code).is_cookie_domain_allowed(domain)


def extract_url_domain(url: str | None) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
        return (parsed.hostname or "").strip().lower()
    except Exception:
        return ""


def normalize_market_price(
    value: str | int | float | None,
    market_code: str | None = None,
) -> str:
    return get_market_policy(market_code).normalize_price_value(value)