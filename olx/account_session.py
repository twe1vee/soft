import json
from typing import Any

from playwright.async_api import async_playwright


OLX_HOME_URL = "https://www.olx.pl/"
OLX_ACCOUNT_URL = "https://www.olx.pl/moj-olx/"


def parse_proxy_text(proxy_text: str) -> dict[str, str]:
    value = proxy_text.strip()

    if not value:
        raise ValueError("Пустая строка proxy")

    if value.startswith("http://") or value.startswith("https://"):
        return {"server": value}

    parts = value.split(":")

    if len(parts) == 2:
        host, port = parts
        return {
            "server": f"http://{host}:{port}",
        }

    if len(parts) == 4:
        host, port, username, password = parts
        return {
            "server": f"http://{host}:{port}",
            "username": username,
            "password": password,
        }

    raise ValueError(
        "Неверный формат proxy. Ожидается host:port или host:port:login:password"
    )


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
            cookie["domain"] = ".olx.pl"

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

    found = []

    for cookie in cookies:
        name = str(cookie.get("name", "")).lower()
        if name in important_names:
            found.append(name)

    return found


def detect_logged_in_from_page(url: str, body_text: str, auth_cookie_names: list[str]) -> bool:
    lowered_url = url.lower()
    lowered_body = body_text.lower()

    login_signals = [
        "zaloguj",
        "zarejestruj",
        "sign in",
        "log in",
        "utwórz konto",
    ]

    account_signals = [
        "moj olx",
        "twoje konto",
        "twoje ogłoszenia",
        "obserwowane",
        "wiadomości",
        "konto",
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


async def check_account_with_proxy(cookies_json: str, proxy_text: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "status": "unknown_error",
        "final_url": None,
        "auth_cookie_names": [],
        "profile_name": None,
        "error": None,
    }

    try:
        proxy = parse_proxy_text(proxy_text)
        cookies = normalize_cookies(cookies_json)
    except Exception as exc:
        result["status"] = "invalid_input"
        result["error"] = str(exc)
        return result

    browser = None
    context = None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                proxy=proxy,
            )

            context = await browser.new_context()
            await context.add_cookies(cookies)

            page = await context.new_page()

            await page.goto(OLX_HOME_URL, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)

            await page.goto(OLX_ACCOUNT_URL, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2500)

            final_url = page.url
            result["final_url"] = final_url

            body_text = await page.locator("body").inner_text()

            current_cookies = await context.cookies()
            auth_cookie_names = get_auth_cookie_names(current_cookies)
            result["auth_cookie_names"] = auth_cookie_names

            is_logged_in = detect_logged_in_from_page(
                url=final_url,
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
        ]

        if any(marker in message for marker in proxy_error_markers):
            result["status"] = "proxy_failed"
        else:
            result["status"] = "browser_failed"

        return result

    finally:
        try:
            if context:
                await context.close()
        except Exception:
            pass

        try:
            if browser:
                await browser.close()
        except Exception:
            pass