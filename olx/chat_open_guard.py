from __future__ import annotations

from typing import Any, Awaitable, Callable

from olx.dialogs_page import dismiss_dialogs_overlays_if_present
from olx.message_sender_chat import (
    click_chat_button,
    collect_chat_diagnostics,
    find_message_input,
    get_chat_button_debug,
    has_blocking_chat_gate,
    has_chat_root,
    wait_for_chat_mount,
)
from olx.message_sender_page import handle_olx_soft_error_page, has_login_hint, is_cloudfront_block_page


async def _sleep(page, ms: int) -> None:
    try:
        await page.wait_for_timeout(ms)
    except Exception:
        pass


async def _try_open_once(
    page,
    *,
    settle_ms: int = 700,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "input_locator": None,
        "message_button_clicked": False,
        "message_button_clicked_retry": False,
        "chat_button_retry_debug": None,
        "chat_button_still_visible_after_click": None,
        "chat_button_text_after_click": None,
        "chat_button_still_visible_after_retry": None,
        "chat_button_text_after_retry": None,
    }

    input_locator = await find_message_input(page)
    if input_locator is not None:
        data["input_locator"] = input_locator
        return data

    clicked, click_debug = await click_chat_button(page)
    data["message_button_clicked"] = clicked
    data.update(click_debug or {})

    visible_after_click, text_after_click = await get_chat_button_debug(page)
    data["chat_button_still_visible_after_click"] = visible_after_click
    data["chat_button_text_after_click"] = text_after_click

    if clicked:
        await wait_for_chat_mount(page)
        await dismiss_dialogs_overlays_if_present(page)
        await _sleep(page, settle_ms)
        input_locator = await find_message_input(page)
        if input_locator is not None:
            data["input_locator"] = input_locator
            return data

    await _sleep(page, 350)

    clicked_retry, click_debug_retry = await click_chat_button(page)
    data["message_button_clicked_retry"] = clicked_retry
    data["chat_button_retry_debug"] = click_debug_retry

    visible_after_retry, text_after_retry = await get_chat_button_debug(page)
    data["chat_button_still_visible_after_retry"] = visible_after_retry
    data["chat_button_text_after_retry"] = text_after_retry

    if clicked_retry:
        await wait_for_chat_mount(page)
        await dismiss_dialogs_overlays_if_present(page)
        await _sleep(page, settle_ms)
        input_locator = await find_message_input(page)
        if input_locator is not None:
            data["input_locator"] = input_locator
            return data

    return data


async def ensure_chat_open(
    page,
    *,
    target_url: str | None = None,
    allow_reload: bool = True,
    settle_ms: int = 700,
) -> dict[str, Any]:
    """
    Возвращает dict с:
      - input_locator
      - recovered_by_reload
      - message_button_clicked / retry debug
      - debug_* diagnostics
      - login/block flags
      - cloudfront_blocked
      - handled_soft_error_page
    """

    result: dict[str, Any] = {
        "input_locator": None,
        "recovered_by_reload": False,
        "cloudfront_blocked": False,
        "handled_soft_error_page": False,
        "debug_login_hint_found": False,
        "debug_blocking_chat_gate_found": False,
        "debug_chat_root_found": False,
        "debug_message_input_found": False,
    }

    await dismiss_dialogs_overlays_if_present(page)
    await _sleep(page, 250)

    attempt1 = await _try_open_once(page, settle_ms=settle_ms)
    result.update({k: v for k, v in attempt1.items() if k != "input_locator"})
    result["input_locator"] = attempt1.get("input_locator")

    diag = await collect_chat_diagnostics(page)
    result.update(diag)
    result["debug_login_hint_found"] = await has_login_hint(page)
    result["debug_blocking_chat_gate_found"] = await has_blocking_chat_gate(page)

    if result["input_locator"] is not None:
        return result

    if result["debug_login_hint_found"] or result["debug_blocking_chat_gate_found"]:
        return result

    if await is_cloudfront_block_page(page):
        result["cloudfront_blocked"] = True
        return result

    if not allow_reload or not target_url:
        return result

    try:
        await page.reload(wait_until="domcontentloaded", timeout=45000)
    except Exception:
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
        except Exception:
            return result

    await _sleep(page, 1400)

    handled_soft_error = await handle_olx_soft_error_page(page)
    result["handled_soft_error_page"] = bool(result["handled_soft_error_page"] or handled_soft_error)

    await dismiss_dialogs_overlays_if_present(page)
    await _sleep(page, 400)

    if await is_cloudfront_block_page(page):
        result["cloudfront_blocked"] = True
        return result

    attempt2 = await _try_open_once(page, settle_ms=settle_ms)
    result["recovered_by_reload"] = True
    result["input_locator"] = attempt2.get("input_locator")

    # не затираем первые debug-поля пустыми значениями без необходимости
    for key, value in attempt2.items():
        if key == "input_locator":
            continue
        if value is not None:
            result[key] = value

    diag = await collect_chat_diagnostics(page)
    result.update(diag)
    result["debug_login_hint_found"] = await has_login_hint(page)
    result["debug_blocking_chat_gate_found"] = await has_blocking_chat_gate(page)

    return result