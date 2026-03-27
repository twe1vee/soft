from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _normalize_multiline_text(value: str) -> str:
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_numeric_token(token: str) -> str:
    token = (token or "").strip()
    token = token.replace(" ", "").replace("\u00a0", "")

    if not token:
        return ""

    comma_count = token.count(",")
    dot_count = token.count(".")

    if comma_count and dot_count:
        last_comma = token.rfind(",")
        last_dot = token.rfind(".")

        if last_comma > last_dot:
            token = token.replace(".", "")
            token = token.replace(",", ".")
        else:
            token = token.replace(",", "")
        return token

    if comma_count:
        if comma_count > 1:
            parts = token.split(",")
            token = "".join(parts[:-1]) + "." + parts[-1]
        else:
            left, right = token.split(",", 1)
            if right.isdigit() and 1 <= len(right) <= 2:
                token = left + "." + right
            else:
                token = left + right
        return token

    if dot_count:
        if dot_count > 1:
            parts = token.split(".")
            last = parts[-1]
            if last.isdigit() and 1 <= len(last) <= 2:
                token = "".join(parts[:-1]) + "." + last
            else:
                token = "".join(parts)
        else:
            left, right = token.split(".", 1)
            if right.isdigit() and 1 <= len(right) <= 2:
                token = left + "." + right
            else:
                token = left + right
        return token

    return token


def _extract_price_number(raw_price) -> str:
    if raw_price is None:
        return ""

    text = _normalize_multiline_text(str(raw_price))
    if not text:
        return ""

    text = text.replace("EUR", " ").replace("eur", " ").replace("€", " ")
    text = re.sub(r"\s+", " ", text).strip()

    matches = re.findall(r"\d[\d\s.,]*", text)
    if not matches:
        return ""

    for match in matches:
        cleaned = _normalize_numeric_token(match)
        if cleaned:
            return cleaned

    return ""


def _format_pt_price(raw_price) -> str:
    numeric_text = _extract_price_number(raw_price)
    if not numeric_text:
        return ""

    try:
        value = Decimal(numeric_text).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return ""

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