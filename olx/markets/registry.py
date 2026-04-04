from __future__ import annotations

import os
from functools import lru_cache

from olx.markets.olx_pl import OLX_PL
from olx.markets.olx_pt import OLX_PT
from olx.markets.types import MarketPolicy


MARKET_REGISTRY: dict[str, MarketPolicy] = {
    OLX_PT.code: OLX_PT,
    OLX_PL.code: OLX_PL,
}

DEFAULT_MARKET_CODE = "olx_pt"


def normalize_market_code(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return DEFAULT_MARKET_CODE
    return raw


@lru_cache(maxsize=1)
def get_default_market_code() -> str:
    env_value = os.getenv("OLX_DEFAULT_MARKET", DEFAULT_MARKET_CODE)
    normalized = normalize_market_code(env_value)
    if normalized in MARKET_REGISTRY:
        return normalized
    return DEFAULT_MARKET_CODE


def get_market_policy(market_code: str | None = None) -> MarketPolicy:
    normalized = normalize_market_code(market_code) or get_default_market_code()
    policy = MARKET_REGISTRY.get(normalized)
    if policy is not None:
        return policy
    return MARKET_REGISTRY[get_default_market_code()]


def require_market_policy(market_code: str | None = None) -> MarketPolicy:
    normalized = normalize_market_code(market_code) or get_default_market_code()
    policy = MARKET_REGISTRY.get(normalized)
    if policy is None:
        raise KeyError(f"Unsupported market code: {normalized}")
    return policy


def get_supported_market_codes() -> list[str]:
    return list(MARKET_REGISTRY.keys())


def get_supported_market_choices() -> list[tuple[str, str]]:
    return [(item.code, item.label) for item in MARKET_REGISTRY.values()]