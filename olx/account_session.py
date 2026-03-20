# olx/account_session.py

from __future__ import annotations

from typing import Any

from olx.browser_session import (
    PT_ACCOUNT_URL,
    PT_HOME_URL,
    dismiss_cookie_banner_if_present,
    get_current_context_cookies,
    open_olx_browser_context,
    open_olx_page,
)
from olx.cookies import normalize_cookies
from olx.proxy_bridge import build_bridge_proxy_settings


def get_auth_cookie_names(cookies: list[dict[str, Any]]) -> list[str]:
    important_names = {
        "authstate",
        "sid",
        "access_token",
        "auth_state",
        "user_uuid",
        "user_id",
        "phpsessid",
    }

    found: list[str] = []
    for cookie in cookies:
        name = str(cookie.get("name", "")).lower()
        if name in important_names:
            found.append(name)

    return found


def detect_logged_in_from_page(
    url: str,
    body_text: str,
    auth_cookie_names: list[str],
) -> bool:
    lowered_url = url.lower()
    lowered_body = body_text.lower()

    login_signals = [
        "iniciar sessão",
        "entrar",
        "login",
        "sign in",
        "log in",
        "criar conta",
    ]
    account_signals = [
        "a minha conta",
        "myaccount",
        "mensagens",
        "favoritos",
        "conta",
        "logout",
        "sair",
    ]

    redirected_to_login = "login" in lowered_url or "auth" in lowered_url
    has_login_cta = any(signal in lowered_body for signal in login_signals)
    has_account_signal = any(signal in lowered_body for signal in account_signals)
    has_auth_cookies = len(auth_cookie_names) > 0

    if redirected_to_login and not has_auth_cookies:
        return False

    if has_auth_cookies and has_account_signal:
        return True

    if has_auth_cookies and not redirected_to_login:
        return True

    if has_login_cta and not has_auth_cookies:
        return False

    return False


async def check_account_with_proxy(
    cookies_json: str,
    proxy_text: str,
    *,
    headless: bool = True,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "status": "unknown_error",
        "final_url": None,
        "auth_cookie_names": [],
        "bridge_server": None,
        "error": None,
    }

    try:
        bridge_proxy = build_bridge_proxy_settings(proxy_text)
        result["bridge_server"] = bridge_proxy["server"]
        normalize_cookies(cookies_json)
    except Exception as exc:
        result["status"] = "invalid_input"
        result["error"] = str(exc)
        return result

    try:
        async with open_olx_browser_context(
            cookies_json=cookies_json,
            proxy_text=proxy_text,
            headless=headless,
        ) as (_, context):
            page = await open_olx_page(
                context,
                PT_HOME_URL,
                timeout=90000,
                wait_after_ms=3000,
            )

            await dismiss_cookie_banner_if_present(page)
            await page.wait_for_timeout(1000)

            await page.goto(
                PT_ACCOUNT_URL,
                wait_until="domcontentloaded",
                timeout=90000,
            )
            await page.wait_for_timeout(4000)

            result["final_url"] = page.url

            body_text = await page.locator("body").inner_text()
            current_cookies = await get_current_context_cookies(context)
            auth_cookie_names = get_auth_cookie_names(current_cookies)
            result["auth_cookie_names"] = auth_cookie_names

            is_logged_in = detect_logged_in_from_page(
                url=page.url,
                body_text=body_text,
                auth_cookie_names=auth_cookie_names,
            )

            if is_logged_in:
                result["ok"] = True
                result["status"] = "connected"
                return result

            if auth_cookie_names:
                result["status"] = "cookies_loaded_but_not_confirmed"
            else:
                result["status"] = "invalid_cookies"

            return result

    except Exception as exc:
        message = str(exc).lower()
        result["error"] = str(exc)

        proxy_error_markers = [
            "proxy",
            "tunnel",
            "timeout",
            "net::err_proxy",
            "browser has been closed",
            "socks",
            "connection refused",
            "connection reset",
            "net::err",
        ]

        if any(marker in message for marker in proxy_error_markers):
            result["status"] = "proxy_failed"
        else:
            result["status"] = "browser_failed"

        return result