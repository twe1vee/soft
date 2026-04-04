from __future__ import annotations

from olx.markets.message_packs import get_message_pack


def get_delivery_verified_texts(market_code: str = "olx_pt") -> list[str]:
    return list(get_message_pack(market_code).get("delivery_verified_texts") or [])


def get_delivery_failed_texts(market_code: str = "olx_pt") -> list[str]:
    return list(get_message_pack(market_code).get("delivery_failed_texts") or [])


def get_login_texts(market_code: str = "olx_pt") -> list[str]:
    return list(get_message_pack(market_code).get("login_texts") or [])


def get_empty_dialog_texts(market_code: str = "olx_pt") -> list[str]:
    return list(get_message_pack(market_code).get("empty_dialog_texts") or [])


def get_button_texts(kind: str, market_code: str = "olx_pt") -> list[str]:
    pack = get_message_pack(market_code)
    button_texts = pack.get("button_texts") or {}
    return list(button_texts.get(kind) or [])