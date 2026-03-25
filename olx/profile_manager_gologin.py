from __future__ import annotations

import os
from urllib.parse import urlparse
from typing import Any

from gologin import GoLogin

from db.accounts import (
    get_account_by_id,
    update_account_browser_engine,
    update_account_gologin_profile,
)
from olx.cookies import normalize_cookies


def get_gologin_token() -> str:
    token = (os.getenv("GOLOGIN_TOKEN") or os.getenv("GL_API_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("Не найден GOLOGIN_TOKEN в .env")
    return token


def build_gologin_client(
    *,
    profile_id: str | None = None,
    headless: bool = True,
) -> GoLogin:
    token = get_gologin_token()
    extra_params: list[str] = []

    if headless:
        extra_params.append("--headless=new")

    return GoLogin({
        "token": token,
        "profile_id": profile_id,
        "extra_params": extra_params,
        "uploadCookiesToServer": True,
        "writeCookesFromServer": True,
    })


def _normalize_same_site_for_gologin(value: str | None) -> str | None:
    if not value:
        return None

    lowered = value.lower()
    if lowered == "lax":
        return "lax"
    if lowered == "strict":
        return "strict"
    if lowered == "none":
        return "no_restriction"
    return None


def cookies_to_gologin(cookies_json: str) -> list[dict[str, Any]]:
    cookies = normalize_cookies(cookies_json)
    result: list[dict[str, Any]] = []

    for item in cookies:
        cookie: dict[str, Any] = {
            "name": item["name"],
            "value": item["value"],
            "path": item.get("path", "/"),
            "secure": bool(item.get("secure", False)),
            "httpOnly": bool(item.get("httpOnly", False)),
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
            cookie["expirationDate"] = expires

        same_site = _normalize_same_site_for_gologin(item.get("sameSite"))
        if same_site:
            cookie["sameSite"] = same_site

        result.append(cookie)

    if not result:
        raise ValueError("После конвертации не осталось cookies для GoLogin")

    return result


def parse_proxy_text(proxy_text: str) -> dict[str, Any]:
    raw = (proxy_text or "").strip()
    if not raw:
        raise ValueError("Пустой proxy_text")

    if "://" in raw:
        parsed = urlparse(raw)
        mode = (parsed.scheme or "http").lower()
        if mode == "https":
            mode = "http"

        if mode not in {"http", "socks5"}:
            raise ValueError(f"Неподдерживаемый тип прокси для GoLogin: {mode}")

        host = parsed.hostname
        port = parsed.port
        username = parsed.username
        password = parsed.password

        if not host or not port:
            raise ValueError("proxy_text имеет неверный формат")

        payload: dict[str, Any] = {
            "mode": mode,
            "host": host,
            "port": int(port),
        }
        if username:
            payload["username"] = username
        if password:
            payload["password"] = password
        return payload

    parts = raw.split(":")

    if len(parts) == 2:
        host, port = parts
        return {
            "mode": "http",
            "host": host.strip(),
            "port": int(port.strip()),
        }

    if len(parts) >= 4:
        host = parts[0].strip()
        port = int(parts[1].strip())
        username = parts[2].strip()
        password = ":".join(parts[3:]).strip()

        return {
            "mode": "http",
            "host": host,
            "port": port,
            "username": username,
            "password": password,
        }

    raise ValueError(
        "proxy_text должен быть в формате "
        "'http://user:pass@host:port', 'socks5://user:pass@host:port', "
        "'host:port' или 'host:port:user:pass'"
    )


def _build_profile_name(
    *,
    user_id: int | None,
    account_id: int | None,
    olx_profile_name: str | None,
) -> str:
    if (olx_profile_name or "").strip():
        return olx_profile_name.strip()

    if account_id is not None:
        return f"OLX Account {account_id}"

    if user_id is not None:
        return f"OLX User {user_id}"

    return "OLX Runtime Profile"


def ensure_gologin_profile(
    *,
    cookies_json: str,
    proxy_text: str,
    user_id: int | None = None,
    account_id: int | None = None,
    olx_profile_name: str | None = None,
) -> dict[str, Any]:
    account: dict[str, Any] | None = None
    existing_profile_id: str | None = None
    existing_profile_name: str | None = None

    if user_id is not None and account_id is not None:
        account = get_account_by_id(user_id, account_id)
        if account:
            existing_profile_id = account.get("gologin_profile_id")
            existing_profile_name = (
                account.get("gologin_profile_name")
                or account.get("olx_profile_name")
            )

    final_profile_name = _build_profile_name(
        user_id=user_id,
        account_id=account_id,
        olx_profile_name=olx_profile_name or existing_profile_name,
    )

    proxy_payload = parse_proxy_text(proxy_text)
    cookies_payload = cookies_to_gologin(cookies_json)

    gl = build_gologin_client(profile_id=None, headless=True)

    profile_id = existing_profile_id
    profile_name = final_profile_name

    if not profile_id:
        created = gl.createProfileRandomFingerprint({
            "os": "win",
            "name": profile_name,
        })

        profile_id = (
            created.get("id")
            or created.get("profile_id")
            or created.get("_id")
        )

        if not profile_id:
            raise RuntimeError(f"GoLogin не вернул profile_id: {created}")

    gl.changeProfileProxy(profile_id, proxy_payload)
    gl.addCookiesToProfile(profile_id, cookies_payload)

    if user_id is not None and account_id is not None:
        update_account_gologin_profile(
            user_id=user_id,
            account_id=account_id,
            gologin_profile_id=profile_id,
            gologin_profile_name=profile_name,
        )
        update_account_browser_engine(
            user_id=user_id,
            account_id=account_id,
            browser_engine="gologin",
        )

    return {
        "browser_engine": "gologin",
        "gologin_profile_id": profile_id,
        "gologin_profile_name": profile_name,
        "proxy_payload": proxy_payload,
        "cookies_count": len(cookies_payload),
    }