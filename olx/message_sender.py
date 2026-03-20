from __future__ import annotations

from typing import Any
import json
from pathlib import Path
from datetime import datetime
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from olx.browser_session import (
    dismiss_cookie_banner_if_present,
    open_olx_browser_context,
    open_olx_page,
)
from olx.proxy_bridge import build_bridge_proxy_settings


SEND_BUTTON_TEXTS = [
    "Enviar mensagem",
    "Wyślij",
    "Отправить",
    "Send",
]

MESSAGE_INPUT_SELECTORS = [
    # portal/chat roots
    "#chatPortalRoot textarea",
    "#root-portal textarea",
    '[data-testid="chat-modal"] textarea',
    '[data-testid="chat"] textarea',
    '[data-testid="conversation-message-input"] textarea',
    '[data-testid="message-input"] textarea',
    '.css-1t3t97v textarea',
    # generic textarea variants
    'textarea[data-testid="message-input"]',
    'textarea[data-testid="textarea"]',
    'textarea[name="message"]',
    'textarea[placeholder]',
    "textarea",
    # role=textbox
    "#chatPortalRoot [role='textbox']",
    "#root-portal [role='textbox']",
    '[data-testid="chat-modal"] [role="textbox"]',
    '[data-testid="chat"] [role="textbox"]',
    '[data-testid="conversation-message-input"] [role="textbox"]',
    '[role="textbox"]',
    # contenteditable
    '#chatPortalRoot [contenteditable="true"]',
    '#root-portal [contenteditable="true"]',
    '[data-testid="chat-modal"] [contenteditable="true"]',
    '[data-testid="chat"] [contenteditable="true"]',
    '[data-testid="conversation-message-input"] [contenteditable="true"]',
    '[contenteditable="true"]',
    'div[contenteditable="true"]',
]

CHAT_ROOT_SELECTORS = [
    "#chatPortalRoot",
    "#root-portal",
    '[data-testid="chat-modal"]',
    '[data-testid="chat"]',
    '[data-testid="conversation-message-input"]',
]

LOGIN_HINT_SELECTORS = [
    'a[href*="conta"]',
    'a[href*="login"]',
    'button:has-text("Entrar")',
    'button:has-text("Iniciar sessão")',
    'text=Entrar',
    'text=Iniciar sessão',
]


def _base_result() -> dict[str, Any]:
    return {
        "page_title": None,
        "debug_chat_root_found": False,
        "debug_login_hint_found": False,
        "debug_html_path": None,
        "debug_png_path": None,
        "debug_json_path": None,
        "debug_html_error": None,
        "debug_png_error": None,
        "debug_json_error": None,
        "error": None,
    }
def _debug_dir() -> Path:
    path = Path("debug_artifacts")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _debug_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


async def _save_debug_artifacts(page, result: dict, prefix: str = "send_debug") -> dict:
    stamp = _debug_stamp()
    debug_dir = _debug_dir()

    html_path = debug_dir / f"{prefix}_{stamp}.html"
    png_path = debug_dir / f"{prefix}_{stamp}.png"
    json_path = debug_dir / f"{prefix}_{stamp}.json"

    try:
        html = await page.content()
        html_path.write_text(html, encoding="utf-8")
        result["debug_html_path"] = str(html_path)
    except Exception as exc:
        result["debug_html_error"] = str(exc)

    try:
        await page.screenshot(path=str(png_path), full_page=True)
        result["debug_png_path"] = str(png_path)
    except Exception as exc:
        result["debug_png_error"] = str(exc)

    try:
        json_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result["debug_json_path"] = str(json_path)
    except Exception as exc:
        result["debug_json_error"] = str(exc)

    return result

async def _click_chat_button(page) -> bool:
    candidates = [
        page.locator('[data-testid="chat-button"]').first,
        page.get_by_role("button", name="Enviar mensagem"),
        page.locator("button:has-text('Enviar mensagem')").first,
        page.locator("a:has-text('Enviar mensagem')").first,
        page.locator("text=Enviar mensagem").first,
    ]

    for locator in candidates:
        try:
            if await locator.count() == 0:
                continue
        except Exception:
            continue

        try:
            await locator.scroll_into_view_if_needed()
        except Exception:
            pass

        try:
            await locator.wait_for(state="visible", timeout=5000)
            await locator.click(timeout=5000)
            return True
        except Exception:
            try:
                await locator.click(force=True, timeout=5000)
                return True
            except Exception:
                continue

    return False


async def _wait_for_chat_mount(page) -> None:
    for selector in CHAT_ROOT_SELECTORS:
        try:
            locator = page.locator(selector).first
            if await locator.count() > 0:
                await locator.wait_for(state="visible", timeout=7000)
                await page.wait_for_timeout(1200)
                return
        except Exception:
            continue

    # fallback: wait for any plausible input
    for selector in MESSAGE_INPUT_SELECTORS:
        try:
            locator = page.locator(selector).first
            if await locator.count() > 0:
                await locator.wait_for(state="attached", timeout=7000)
                await page.wait_for_timeout(1200)
                return
        except Exception:
            continue

    await page.wait_for_timeout(5000)


async def _find_message_input(page):
    for selector in MESSAGE_INPUT_SELECTORS:
        locator = page.locator(selector).first

        try:
            if await locator.count() == 0:
                continue
        except Exception:
            continue

        try:
            await locator.wait_for(state="attached", timeout=3000)
        except Exception:
            pass

        try:
            if await locator.is_visible():
                return locator
        except Exception:
            pass

        try:
            return locator
        except Exception:
            continue

    return None


async def _has_login_hint(page) -> bool:
    for selector in LOGIN_HINT_SELECTORS:
        try:
            locator = page.locator(selector).first
            if await locator.count() == 0:
                continue
            if await locator.is_visible():
                return True
        except Exception:
            continue
    return False


async def _has_chat_root(page) -> bool:
    for selector in CHAT_ROOT_SELECTORS:
        try:
            locator = page.locator(selector).first
            if await locator.count() == 0:
                continue
            if await locator.is_visible():
                return True
        except Exception:
            continue
    return False


async def _fill_message_input(locator, message_text: str) -> None:
    tag_name = await locator.evaluate("(el) => el.tagName.toLowerCase()")

    if tag_name == "textarea":
        await locator.fill(message_text)
        return

    contenteditable = await locator.evaluate(
        "(el) => el.getAttribute('contenteditable')"
    )
    if contenteditable:
        await locator.click()
        try:
            await locator.fill(message_text)
        except Exception:
            await locator.type(message_text, delay=20)
        return

    try:
        await locator.fill(message_text)
    except Exception:
        await locator.click()
        await locator.type(message_text, delay=20)


async def _click_send_button(page, input_locator) -> bool:
    candidates = []

    for text in SEND_BUTTON_TEXTS:
        candidates.extend([
            page.get_by_role("button", name=text),
            page.locator(f"button:has-text('{text}')"),
            page.locator(f"text={text}"),
        ])

    for locator in candidates:
        try:
            count = await locator.count()
        except Exception:
            continue

        for i in range(count):
            item = locator.nth(i)
            try:
                if await item.is_visible():
                    await item.scroll_into_view_if_needed()
                    await item.click(timeout=5000)
                    return True
            except Exception:
                try:
                    await item.click(force=True, timeout=5000)
                    return True
                except Exception:
                    continue

    for hotkey in ("Control+Enter", "Enter"):
        try:
            await input_locator.press(hotkey)
            return True
        except Exception:
            continue

    return False


async def send_message_to_ad(
    cookies_json: str,
    proxy_text: str,
    ad_url: str,
    message_text: str,
    *,
    headless: bool = True,
) -> dict[str, Any]:
    result = _base_result()
    result["ad_url"] = ad_url
    result["message_length"] = len(message_text or "")

    if not (ad_url or "").strip():
        result["status"] = "invalid_input"
        result["error"] = "Пустой ad_url"
        return result

    if not (message_text or "").strip():
        result["status"] = "invalid_input"
        result["error"] = "Пустой message_text"
        return result

    try:
        bridge_proxy = build_bridge_proxy_settings(proxy_text)
        result["bridge_server"] = bridge_proxy["server"]
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
                ad_url,
                timeout=90000,
                wait_after_ms=5000,
            )

            result["final_url"] = page.url

            try:
                result["page_title"] = await page.title()
            except Exception:
                pass

            await dismiss_cookie_banner_if_present(page)
            await page.wait_for_timeout(1500)

            input_locator = await _find_message_input(page)

            if input_locator is None:
                clicked = await _click_chat_button(page)
                result["message_button_clicked"] = clicked

                if clicked:
                    await _wait_for_chat_mount(page)

                result["debug_chat_root_found"] = await _has_chat_root(page)
                result["debug_login_hint_found"] = await _has_login_hint(page)

                input_locator = await _find_message_input(page)

            if input_locator is None:
                if result["debug_login_hint_found"]:
                    result["status"] = "login_required_or_chat_blocked"
                    result[
                        "error"] = "После клика по chat-button открылся логин/блокирующий интерфейс вместо поля ввода"
                    await _save_debug_artifacts(page, result, prefix="login_required_or_chat_blocked")
                    return result

                result["status"] = "message_input_not_found"
                result["error"] = "Не найдено поле ввода сообщения после клика по chat-button"
                await _save_debug_artifacts(page, result, prefix="message_input_not_found")
                return result

            result["input_found"] = True

            await _fill_message_input(input_locator, message_text)
            await page.wait_for_timeout(1000)

            send_clicked = await _click_send_button(page, input_locator)
            result["send_button_found"] = send_clicked

            if not send_clicked:
                result["status"] = "send_button_not_found"
                result["error"] = "Не найдена кнопка отправки сообщения"
                await _save_debug_artifacts(page, result, prefix="send_button_not_found")
                return result

            await page.wait_for_timeout(4000)

            result["ok"] = True
            result["status"] = "sent"
            result["sent"] = True
            result["final_url"] = page.url
            return result

    except PlaywrightTimeoutError as exc:
        result["status"] = "timeout"
        result["error"] = str(exc)
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

        try:
            if "page" in locals() and page is not None:
                await _save_debug_artifacts(page, result, prefix=result["status"])
        except Exception:
            pass

        return result