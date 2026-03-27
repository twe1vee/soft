from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _normalize_multiline_text(value: str) -> str:
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _format_pt_price(raw_price) -> str:
    if raw_price is None:
        return ""

    text = str(raw_price).strip()
    if not text:
        return ""

    text = text.replace("€", "").replace("EUR", "").replace(" ", "")

    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")

    try:
        value = Decimal(text).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        fallback = _normalize_multiline_text(str(raw_price))
        if not fallback:
            return ""
        return fallback

    return f"{value:.2f}".replace(".", ",")


def render_template(template_text: str, ad_data: dict) -> str:
    seller_name = _normalize_multiline_text(ad_data.get("seller_name") or "")
    price = _format_pt_price(ad_data.get("price"))
    url = _normalize_multiline_text(ad_data.get("url") or "")

    rendered = (
        (template_text or "")
        .replace("{seller_name}", seller_name)
        .replace("{price}", price)
        .replace("{url}", url)
    )

    return _normalize_multiline_text(rendered)