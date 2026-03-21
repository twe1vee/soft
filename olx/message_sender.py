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
    "#chatPortalRoot textarea",
    "#root-portal textarea",
    '[data-testid="chat-modal"] textarea',
    '[data-testid="chat"] textarea',
    '[data-testid="conversation-message-input"] textarea',
    '[data-testid="message-input"] textarea',
    ".css-1t3t97v textarea",
    'textarea[data-testid="message-input"]',
    'textarea[data-testid="textarea"]',
    'textarea[name="message"]',
    'textarea[placeholder]',
    "textarea",
    "#chatPortalRoot [role='textbox']",
    "#root-portal [role='textbox']",
    '[data-testid="chat-modal"] [role="textbox"]',
    '[data-testid="chat"] [role="textbox"]',
    '[data-testid="conversation-message-input"] [role="textbox"]',
    '[role="textbox"]',
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


def _normalize_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


async def _safe_locator_text(locator) -> str:
    try:
        text = await locator.inner_text()
        return _normalize_text(text)
    except Exception:
        return ""


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
        except Exception:
            continue

        try:
            box = await locator.bounding_box()
            if box:
                x = box["x"] + box["width"] / 2
                y = box["y"] + box["height"] / 2
                await page.mouse.move(x, y)
                await page.wait_for_timeout(150)
                await page.mouse.click(x, y)
                await page.wait_for_timeout(800)
                if await _has_chat_root(page) or await _find_message_input(page):
                    return True
        except Exception:
            pass

        try:
            await locator.click(timeout=5000)
            await page.wait_for_timeout(800)
            if await _has_chat_root(page) or await _find_message_input(page):
                return True
            return True
        except Exception:
            pass

        try:
            await locator.click(force=True, timeout=5000)
            await page.wait_for_timeout(800)
            if await _has_chat_root(page) or await _find_message_input(page):
                return True
            return True
        except Exception:
            continue

    return False


async def _wait_for_chat_mount(page) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass

    for _ in range(8):
        try:
            if await _has_chat_root(page):
                await page.wait_for_timeout(800)
                return
        except Exception:
            pass

        try:
            input_locator = await _find_message_input(page)
            if input_locator is not None:
                await page.wait_for_timeout(800)
                return
        except Exception:
            pass

        await page.wait_for_timeout(1000)


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
    strict_candidates = [
        page.locator('button[aria-label="Submit message"]').first,
        page.locator('button[type="submit"]').first,
        page.locator('form button[type="submit"]').first,
        page.locator('[data-testid="chat"] button[type="submit"]').first,
        page.locator('[data-testid="chat-modal"] button[type="submit"]').first,
        page.locator('#chatPortalRoot button[type="submit"]').first,
        page.locator('#root-portal button[type="submit"]').first,
    ]

    for locator in strict_candidates:
        try:
            if await locator.count() == 0:
                continue

            await locator.wait_for(state="visible", timeout=3000)
            await locator.scroll_into_view_if_needed()

            try:
                box = await locator.bounding_box()
                if box:
                    x = box["x"] + box["width"] / 2
                    y = box["y"] + box["height"] / 2
                    await page.mouse.move(x, y)
                    await page.wait_for_timeout(100)
                    await page.mouse.click(x, y)
                    return True
            except Exception:
                pass

            try:
                await locator.click(timeout=3000)
                return True
            except Exception:
                await locator.click(force=True, timeout=3000)
                return True
        except Exception:
            continue

    fallback_candidates = []
    for text in SEND_BUTTON_TEXTS:
        fallback_candidates.extend(
            [
                page.get_by_role("button", name=text),
                page.locator(f"button:has-text('{text}')"),
            ]
        )

    for locator in fallback_candidates:
        try:
            count = await locator.count()
        except Exception:
            continue

        for i in range(count):
            item = locator.nth(i)
            try:
                if not await item.is_visible():
                    continue

                try:
                    item_type = await item.get_attribute("type")
                except Exception:
                    item_type = None

                try:
                    aria_label = await item.get_attribute("aria-label")
                except Exception:
                    aria_label = None

                if item_type == "submit" or aria_label == "Submit message":
                    await item.scroll_into_view_if_needed()
                    try:
                        await item.click(timeout=3000)
                    except Exception:
                        await item.click(force=True, timeout=3000)
                    return True
            except Exception:
                continue

    for hotkey in ("Control+Enter", "Enter"):
        try:
            await input_locator.focus()
        except Exception:
            pass

        try:
            await input_locator.press(hotkey)
            return True
        except Exception:
            continue

    return False


async def _read_input_value(locator) -> str:
    try:
        tag_name = await locator.evaluate("(el) => el.tagName.toLowerCase()")
    except Exception:
        return ""

    try:
        if tag_name == "textarea":
            value = await locator.input_value()
            return _normalize_text(value)
    except Exception:
        pass

    try:
        contenteditable = await locator.evaluate(
            "(el) => el.getAttribute('contenteditable')"
        )
        if contenteditable:
            text = await locator.evaluate("(el) => el.innerText || el.textContent || ''")
            return _normalize_text(text)
    except Exception:
        pass

    return ""


async def _page_body_text(page) -> str:
    try:
        text = await page.locator("body").inner_text(timeout=3000)
        return _normalize_text(text)
    except Exception:
        return ""


async def _verify_message_sent(page, input_locator, message_text: str) -> dict[str, Any]:
    target_text = _normalize_text(message_text)
    verification: dict[str, Any] = {
        "post_send_message_visible": False,
        "post_send_input_empty": False,
        "post_send_chat_root_found": False,
        "post_send_body_has_text": False,
        "post_send_url": None,
        "delivery_verified": False,
    }

    for _ in range(8):
        await page.wait_for_timeout(1000)

        try:
            verification["post_send_url"] = page.url
        except Exception:
            pass

        try:
            verification["post_send_chat_root_found"] = await _has_chat_root(page)
        except Exception:
            pass

        input_value = await _read_input_value(input_locator)
        verification["post_send_input_empty"] = not bool(input_value)

        body_text = await _page_body_text(page)
        verification["post_send_body_has_text"] = bool(
            target_text and target_text in body_text
        )

        if verification["post_send_body_has_text"]:
            verification["post_send_message_visible"] = True

        if verification["post_send_message_visible"] and verification["post_send_input_empty"]:
            verification["delivery_verified"] = True
            return verification

    return verification


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

                try:
                    chat_btn = page.locator('[data-testid="chat-button"]').first
                    result["chat_button_still_visible_after_click"] = (
                        await chat_btn.count() > 0 and await chat_btn.is_visible()
                    )
                    result["chat_button_text_after_click"] = await _safe_locator_text(chat_btn)
                except Exception:
                    result["chat_button_still_visible_after_click"] = None
                    result["chat_button_text_after_click"] = None

                input_locator = await _find_message_input(page)

            if input_locator is None:
                if result["debug_login_hint_found"]:
                    result["status"] = "login_required_or_chat_blocked"
                    result["error"] = (
                        "После клика по chat-button открылся логин/блокирующий интерфейс вместо поля ввода"
                    )
                    await _save_debug_artifacts(
                        page,
                        result,
                        prefix="login_required_or_chat_blocked",
                    )
                    return result

                result["status"] = "message_input_not_found"
                result["error"] = "Не найдено поле ввода сообщения после клика по chat-button"
                await _save_debug_artifacts(page, result, prefix="message_input_not_found")
                return result

            result["input_found"] = True

            await _fill_message_input(input_locator, message_text)
            await page.wait_for_timeout(1000)

            try:
                submit_btn = page.locator('button[aria-label="Submit message"]').first
                result["submit_button_visible_before_click"] = (
                    await submit_btn.count() > 0 and await submit_btn.is_visible()
                )
                result["submit_button_text_before_click"] = await _safe_locator_text(submit_btn)
            except Exception:
                result["submit_button_visible_before_click"] = None
                result["submit_button_text_before_click"] = None

            send_clicked = await _click_send_button(page, input_locator)
            result["send_button_found"] = send_clicked

            try:
                submit_btn = page.locator('button[aria-label="Submit message"]').first
                result["submit_button_visible_after_click"] = (
                    await submit_btn.count() > 0 and await submit_btn.is_visible()
                )
                result["submit_button_text_after_click"] = await _safe_locator_text(submit_btn)
            except Exception:
                result["submit_button_visible_after_click"] = None
                result["submit_button_text_after_click"] = None

            if not send_clicked:
                result["status"] = "send_button_not_found"
                result["error"] = "Не найдена кнопка отправки сообщения"
                await _save_debug_artifacts(page, result, prefix="send_button_not_found")
                return result

            await page.wait_for_timeout(1500)

            verification = await _verify_message_sent(page, input_locator, message_text)
            result.update(verification)
            result["final_url"] = page.url

            if verification.get("delivery_verified"):
                result["ok"] = True
                result["status"] = "sent"
                result["sent"] = True
                return result

            result["ok"] = False
            result["status"] = "send_clicked_unverified"
            result["sent"] = False
            result["error"] = "Кнопка отправки была нажата, но подтверждение реальной отправки не получено"
            await _save_debug_artifacts(page, result, prefix="send_clicked_unverified")
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