from __future__ import annotations

from playwright.async_api import Page

from olx.browser_session import dismiss_cookie_banner_if_present
from olx.message_sender_page import handle_olx_soft_error_page, has_login_hint, is_cloudfront_block_page

PT_DIALOGS_URL = "https://www.olx.pt/myaccount/answers/"

DIALOGS_LIST_SELECTORS = [
    '[data-testid="chat-list"]',
    '[data-testid="conversation-list"]',
    '[data-testid="inbox-list"]',
    '[data-testid*="conversation"]',
    '[data-testid*="chat-list"]',
    '[data-cy="chat-list"]',
    '[data-cy="conversation-list"]',
    'a[href*="/myaccount/answers/"]',
    'main a[href*="/myaccount/answers/"]',
]

DIALOG_ROW_SELECTORS = [
    '[data-testid="chat-list-item"]',
    '[data-testid="conversation-item"]',
    '[data-testid*="conversation-item"]',
    '[data-testid*="chat-list-item"]',
    '[data-cy="conversation-row"]',
    '[data-cy="chat-row"]',
    'main a[href*="/myaccount/answers/"]',
]

OVERLAY_CLOSE_SELECTORS = [
    'button[aria-label="Close"]',
    'button[aria-label="Fechar"]',
    'button:has-text("Fechar")',
    'button:has-text("Close")',
]


async def goto_dialogs_page(
    page: Page,
    *,
    timeout: int = 90000,
    wait_after_ms: int = 4000,
) -> None:
    await page.goto(PT_DIALOGS_URL, wait_until="domcontentloaded", timeout=timeout)
    if wait_after_ms > 0:
        await page.wait_for_timeout(wait_after_ms)


async def dismiss_dialogs_overlays_if_present(page: Page) -> None:
    await dismiss_cookie_banner_if_present(page)

    for selector in OVERLAY_CLOSE_SELECTORS:
        try:
            locator = page.locator(selector).first
            if await locator.count() == 0:
                continue
            if await locator.is_visible():
                await locator.click(timeout=2000)
                await page.wait_for_timeout(500)
                return
        except Exception:
            continue


async def wait_for_dialogs_page_ready(
    page: Page,
    *,
    timeout_ms: int = 15000,
) -> bool:
    for selector in DIALOGS_LIST_SELECTORS:
        try:
            locator = page.locator(selector).first
            await locator.wait_for(state="visible", timeout=timeout_ms)
            return True
        except Exception:
            continue

    for selector in DIALOG_ROW_SELECTORS:
        try:
            locator = page.locator(selector).first
            await locator.wait_for(state="visible", timeout=2000)
            return True
        except Exception:
            continue

    return False


async def ensure_dialogs_page_loaded(
    page: Page,
    *,
    timeout: int = 90000,
    wait_after_ms: int = 4000,
) -> dict:
    await goto_dialogs_page(page, timeout=timeout, wait_after_ms=wait_after_ms)
    await dismiss_dialogs_overlays_if_present(page)

    handled_soft_error_page = await handle_olx_soft_error_page(page)
    if handled_soft_error_page:
        await dismiss_dialogs_overlays_if_present(page)

    ready = await wait_for_dialogs_page_ready(page)

    return {
        "ok": ready,
        "final_url": page.url,
        "page_title": await _safe_page_title(page),
        "handled_soft_error_page": handled_soft_error_page,
        "cloudfront_blocked": await is_cloudfront_block_page(page),
        "login_hint_found": await has_login_hint(page),
    }


async def open_dialogs_page(
    page: Page,
    *,
    timeout: int = 90000,
    wait_after_ms: int = 4000,
) -> dict:
    info = await ensure_dialogs_page_loaded(
        page,
        timeout=timeout,
        wait_after_ms=wait_after_ms,
    )

    if not info["ok"]:
        info["dialog_rows_found"] = await count_dialog_rows(page)
    else:
        info["dialog_rows_found"] = await count_dialog_rows(page)

    return info


async def count_dialog_rows(page: Page) -> int:
    best = 0
    for selector in DIALOG_ROW_SELECTORS:
        try:
            count = await page.locator(selector).count()
            if count > best:
                best = count
        except Exception:
            continue
    return best


async def _safe_page_title(page: Page) -> str | None:
    try:
        return await page.title()
    except Exception:
        return None