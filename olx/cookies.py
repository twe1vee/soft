from __future__ import annotations

import json
from typing import Any


def normalize_same_site(value: str | None) -> str | None:
    if not value:
        return None

    lowered = value.lower()
    if lowered == "lax":
        return "Lax"
    if lowered == "strict":
        return "Strict"
    if lowered == "none":
        return "None"
    return None


def normalize_cookies(cookies_json: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(cookies_json)
    except json.JSONDecodeError as exc:
        raise ValueError("cookies_json не является валидным JSON") from exc

    if not isinstance(parsed, list):
        raise ValueError("cookies_json должен быть JSON-массивом")

    normalized: list[dict[str, Any]] = []

    for item in parsed:
        if not isinstance(item, dict):
            continue

        name = item.get("name")
        value = item.get("value")

        if not name or value is None:
            continue

        cookie: dict[str, Any] = {
            "name": name,
            "value": str(value),
            "path": item.get("path", "/"),
        }

        domain = item.get("domain")
        url = item.get("url")

        if domain:
            cookie["domain"] = domain
        elif url:
            cookie["url"] = url
        else:
            cookie["domain"] = ".olx.pt"

        expires = item.get("expires")
        if isinstance(expires, (int, float)) and expires > 0:
            cookie["expires"] = expires

        http_only = item.get("httpOnly")
        if isinstance(http_only, bool):
            cookie["httpOnly"] = http_only

        secure = item.get("secure")
        if isinstance(secure, bool):
            cookie["secure"] = secure

        same_site = normalize_same_site(item.get("sameSite"))
        if same_site:
            cookie["sameSite"] = same_site

        normalized.append(cookie)

    if not normalized:
        raise ValueError("После нормализации не осталось ни одной cookies")

    return normalized