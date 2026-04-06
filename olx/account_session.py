from __future__ import annotations

from typing import Any

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from olx.account_runtime import use_account_runtime_page
from olx.browser_session import dismiss_cookie_banner_if_present
from olx.markets.helpers import (
    extract_url_domain,
    get_market_account_url,
    get_market_home_url,
    is_market_domain,
)
from olx.message_sender_page import is_cloudfront_block_page


DEFAULT_ACCOUNT_MARKET = "olx_pt"


def _classify_account_error(error_text: str) -> tuple[str, str]:
    lowered = (error_text or "").lower()

    if "cloudfront" in lowered or "access denied" in lowered:
        return "cloudfront_blocked", "OLX/CloudFront blocked the request"

    timeout_markers = [
        "net::err_timed_out",
        "timed out",
        "timeout",
    ]
    for marker in timeout_markers:
        if marker in lowered:
            return "timeout", error_text or "Превышено время ожидания при проверке аккаунта"

    proxy_markers = [
        "net::err_proxy",
        "proxy authentication required",
        "proxy error",
        "407",
        "tunnel connection failed",
        "net::err_no_supported_proxies",
        "net::err_socks_connection_failed",
        "net::err_connection_closed",
        "net::err_connection_reset",
        "net::err_connection_refused",
        "remote end closed connection without response",
        "connection aborted",
        "connection refused",
        "name not resolved",
        "net::err_name_not_resolved",
        "dns",
    ]
    for marker in proxy_markers:
        if marker in lowered:
            return "proxy_failed", error_text

    return "failed", error_text or "Неизвестная ошибка проверки аккаунта"


def _looks_like_logged_in_by_url(url: str | None) -> bool:
    value = (url or "").lower()
    positive_markers = [
        "/myaccount",
        "/conta",
        "/account",
        "/ads",
        "/favoritos",
        "/messages",
        "/mojekonto",
    ]
    return any(marker in value for marker in positive_markers)


async def _has_login_indicators(page) -> bool:
    selectors = [
        'form[action*="login"]',
        'input[name="login[email]"]',
        'input[name="username"]',
        'input[type="password"]',
        '[data-testid*="login"]',
        '[data-testid*="auth"]',
        'text=Iniciar sessão',
        'text=Entrar',
        'text=Login',
        'text=Sign in',
        'text=Zaloguj',
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if await locator.count() == 0:
                continue
            if await locator.is_visible():
                return True
        except Exception:
            continue

    try:
        body_text = (await page.locator("body").inner_text(timeout=5000)).lower()
    except Exception:
        body_text = ""

    login_markers = [
        "iniciar sessão",
        "entrar",
        "sign in",
        "login",
        "continuar com google",
        "continuar com facebook",
        "zaloguj",
        "logowanie",
    ]
    return any(marker in body_text for marker in login_markers)


async def _has_logged_in_indicators(page) -> bool:
    selectors = [
        '[data-testid*="account"]',
        '[data-testid*="profile"]',
        '[data-testid*="user"]',
        '[data-testid*="avatar"]',
        'a[href*="/myaccount"]',
        'a[href*="/conta"]',
        'a[href*="/messages"]',
        'a[href*="/favorites"]',
        'a[href*="/mojekonto"]',
        'button[aria-label*="account" i]',
        'button[aria-label*="profile" i]',
        'img[alt*="avatar" i]',
        'img[src*="avatar"]',
        '[class*="avatar"]',
        '[class*="profile"]',
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if await locator.count() == 0:
                continue
            if await locator.is_visible():
                return True
        except Exception:
            continue

    try:
        await page.wait_for_timeout(2500)
    except Exception:
        pass

    try:
        body_text = (await page.locator("body").inner_text(timeout=7000)).lower()
    except Exception:
        body_text = ""

    positive_markers = [
        "minha conta",
        "my account",
        "perfil",
        "os meus anúncios",
        "meus anúncios",
        "favoritos",
        "mensagens",
        "conta",
        "moje konto",
        "wiadomości",
    ]
    return any(marker in body_text for marker in positive_markers)


async def _open_account_area_with_retry(
    page,
    *,
    market_code: str = DEFAULT_ACCOUNT_MARKET,
    attempts: int = 2,
) -> tuple[str | None, str | None, str | None]:
    last_error: str | None = None
    last_title: str | None = None
    last_body: str | None = None

    urls_to_try = [
        get_market_account_url(market_code),
        get_market_home_url(market_code),
    ]

    for attempt in range(1, attempts + 1):
        for target_url in urls_to_try:
            try:
                await page.goto(
                    target_url,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                await page.wait_for_timeout(4000)

                try:
                    await dismiss_cookie_banner_if_present(page)
                except Exception:
                    pass

                await page.wait_for_timeout(1500)

                try:
                    last_title = await page.title()
                except Exception:
                    last_title = None

                try:
                    last_body = await page.locator("body").inner_text(timeout=7000)
                except Exception:
                    last_body = ""

                return page.url, last_title, last_body

            except PlaywrightTimeoutError as exc:
                last_error = str(exc)
            except Exception as exc:
                last_error = str(exc)

        if attempt < attempts:
            try:
                await page.goto("about:blank", timeout=10000)
                await page.wait_for_timeout(2000)
            except Exception:
                pass

    raise RuntimeError(last_error or "Не удалось открыть OLX account area")


async def check_account_alive(
    cookies_json: str,
    proxy_text: str,
    *,
    headless: bool = True,
    user_id: int | None = None,
    account_id: int | None = None,
    olx_profile_name: str | None = None,
    market_code: str = DEFAULT_ACCOUNT_MARKET,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "status": "failed",
        "final_url": None,
        "page_title": None,
        "browser_engine": "gologin",
        "gologin_profile_id": None,
        "gologin_profile_name": None,
        "debugger_address": None,
        "error": None,
        "attempts_used": 0,
        "body_length": 0,
        "debug_login_detected": False,
        "debug_logged_in_detected": False,
        "debug_logged_in_by_url": False,
        "market_code": market_code,
    }

    try:
        if not account_id or int(account_id) <= 0:
            result["status"] = "failed"
            result["error"] = f"Некорректный account_id для check_account_alive: {account_id}"
            return result

        async with use_account_runtime_page(
            user_id=user_id,
            account_id=int(account_id),
            cookies_json=cookies_json,
            proxy_text=proxy_text,
            url=None,
            headless=headless,
            olx_profile_name=olx_profile_name,
            timeout=90000,
            wait_after_ms=0,
            busy_reason="check_account_alive",
        ) as (page, runtime_entry):
            result["browser_engine"] = runtime_entry.runtime.get("browser_engine", "gologin")
            result["gologin_profile_id"] = runtime_entry.runtime.get("gologin_profile_id")
            result["gologin_profile_name"] = runtime_entry.runtime.get("gologin_profile_name")
            result["debugger_address"] = runtime_entry.runtime.get("debugger_address")

            result["attempts_used"] = 2
            final_url, page_title, body_text = await _open_account_area_with_retry(
                page,
                market_code=market_code,
                attempts=2,
            )

            result["final_url"] = final_url
            result["page_title"] = page_title
            result["body_length"] = len((body_text or "").strip())

            if await is_cloudfront_block_page(page):
                result["status"] = "cloudfront_blocked"
                result["error"] = "OLX/CloudFront blocked the request"
                return result

            login_detected = await _has_login_indicators(page)
            logged_in_detected = await _has_logged_in_indicators(page)
            logged_in_by_url = _looks_like_logged_in_by_url(final_url)

            result["debug_login_detected"] = login_detected
            result["debug_logged_in_detected"] = logged_in_detected
            result["debug_logged_in_by_url"] = logged_in_by_url

            if login_detected and not logged_in_by_url:
                result["status"] = "not_logged_in"
                result["error"] = "OLX открыл login flow, сессия не подтверждена"
                return result

            if logged_in_detected or logged_in_by_url:
                result["ok"] = True
                result["status"] = "connected"
                result["error"] = None
                return result

            if final_url and is_market_domain(extract_url_domain(final_url), market_code):
                result["status"] = "unstable"
                result["error"] = "OLX открылся, но аккаунт подтвердился неуверенно"
                return result

            result["status"] = "failed"
            result["error"] = "Проверка аккаунта не смогла подтвердить активную сессию"
            return result

    except Exception as exc:
        status, human_error = _classify_account_error(str(exc))
        result["status"] = status
        result["error"] = human_error
        return result


check_account_with_proxy = check_account_alive