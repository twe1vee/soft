from __future__ import annotations

import asyncio
from typing import Any


DIALOGS_URL = "https://www.olx.pt/myaccount/answers/?my_ads=0"

_DIALOGS_READY_SELECTORS = [
    '[data-cy="chat-list"]',
    '[data-testid="chat-list"]',
    '[data-cy="chat-item"]',
    '[data-testid="chat-item"]',
    'a[href*="/d/oferta/"]',
    'a[href*="/d/anuncio/"]',
    'a[href*="/myaccount/answers/"]',
    'main',
]

_EMPTY_STATE_SELECTORS = [
    '[data-cy="empty-state"]',
    '[data-testid="empty-state"]',
    'text=/sem mensagens/i',
    'text=/nenhuma mensagem/i',
    'text=/ainda não tens mensagens/i',
    'text=/não tem mensagens/i',
]

_LOGIN_HINT_SELECTORS = [
    'input[name="email"]',
    'input[type="email"]',
    'input[name="username"]',
    'input[name="password"]',
    'form[action*="login"]',
    'text=/iniciar sessão/i',
    'text=/inicia sessão/i',
    'text=/login/i',
]

_BLOCK_SELECTORS = [
    'text=/attention required/i',
    'text=/sorry, you have been blocked/i',
    'text=/cloudflare/i',
    'text=/cloudfront/i',
    'text=/request blocked/i',
    'text=/access denied/i',
]

_OVERLAY_SELECTORS = [
    'button[aria-label="Fechar"]',
    'button[aria-label="Close"]',
    'button[data-cy="close-button"]',
    'button[data-testid="close-button"]',
    '[data-cy="modal"] button',
    '[role="dialog"] button',
    '[data-testid="dialog"] button',
    'button:has-text("Fechar")',
    'button:has-text("Aceitar")',
    'button:has-text("Accept")',
    'button:has-text("Continuar")',
    'button:has-text("Entendi")',
    'button:has-text("OK")',
]


async def _safe_count(page, selector: str) -> int:
    try:
        return await page.locator(selector).count()
    except Exception:
        return 0


async def _safe_visible(page, selector: str) -> bool:
    try:
        locator = page.locator(selector).first
        return await locator.is_visible(timeout=1200)
    except Exception:
        return False


async def _match_any(page, selectors: list[str]) -> str | None:
    for selector in selectors:
        if await _safe_visible(page, selector):
            return selector
        if await _safe_count(page, selector) > 0:
            return selector
    return None


async def _wait_for_any(
    page,
    selectors: list[str],
    *,
    timeout_ms: int,
    poll_ms: int = 500,
) -> str | None:
    loops = max(1, timeout_ms // poll_ms)
    for _ in range(loops):
        matched = await _match_any(page, selectors)
        if matched:
            return matched
        await page.wait_for_timeout(poll_ms)
    return None


async def dismiss_dialogs_overlays_if_present(page) -> bool:
    dismissed = False

    for selector in _OVERLAY_SELECTORS:
        try:
            locator = page.locator(selector).first
            if await locator.count() < 1:
                continue
            if not await locator.is_visible(timeout=500):
                continue
            await locator.click(timeout=1500)
            await page.wait_for_timeout(500)
            dismissed = True
        except Exception:
            continue

    if dismissed:
        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(300)
        except Exception:
            pass

    return dismissed


async def open_dialogs_page(
    page,
    *,
    timeout: int = 45000,
    wait_after_ms: int = 2500,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "target_url": DIALOGS_URL,
        "final_url": None,
        "page_title": None,
        "dialog_rows_found": 0,
        "ready_selector": None,
        "empty_state_found": False,
        "login_hint_found": False,
        "cloudfront_blocked": False,
        "handled_soft_error_page": False,
    }

    await page.goto(DIALOGS_URL, wait_until="domcontentloaded", timeout=timeout)
    await page.wait_for_timeout(wait_after_ms)

    result["final_url"] = getattr(page, "url", None)
    try:
        result["page_title"] = await page.title()
    except Exception:
        result["page_title"] = None

    await dismiss_dialogs_overlays_if_present(page)

    for _ in range(3):
        try:
            await page.mouse.move(300, 220)
            await page.mouse.wheel(0, 700)
            await page.wait_for_timeout(500)
            await page.mouse.wheel(0, -450)
            await page.wait_for_timeout(500)
        except Exception:
            break

    block_match = await _match_any(page, _BLOCK_SELECTORS)
    if block_match:
        result["cloudfront_blocked"] = True
        result["ready_selector"] = block_match
        return result

    login_match = await _match_any(page, _LOGIN_HINT_SELECTORS)
    if login_match:
        result["login_hint_found"] = True
        result["ready_selector"] = login_match
        return result

    ready_match = await _wait_for_any(
        page,
        _DIALOGS_READY_SELECTORS + _EMPTY_STATE_SELECTORS + _LOGIN_HINT_SELECTORS + _BLOCK_SELECTORS,
        timeout_ms=min(timeout, 12000),
        poll_ms=500,
    )

    result["final_url"] = getattr(page, "url", None)
    try:
        result["page_title"] = await page.title()
    except Exception:
        pass

    if ready_match:
        result["ready_selector"] = ready_match

    block_match = await _match_any(page, _BLOCK_SELECTORS)
    if block_match:
        result["cloudfront_blocked"] = True
        if not result["ready_selector"]:
            result["ready_selector"] = block_match
        return result

    login_match = await _match_any(page, _LOGIN_HINT_SELECTORS)
    if login_match:
        result["login_hint_found"] = True
        if not result["ready_selector"]:
            result["ready_selector"] = login_match
        return result

    empty_match = await _match_any(page, _EMPTY_STATE_SELECTORS)
    if empty_match:
        result["empty_state_found"] = True
        result["ready_selector"] = result["ready_selector"] or empty_match
        return result

    total_rows = 0
    for selector in _DIALOGS_READY_SELECTORS:
        total_rows += await _safe_count(page, selector)
    result["dialog_rows_found"] = total_rows

    if total_rows > 0:
        return result

    try:
        await page.reload(wait_until="domcontentloaded", timeout=timeout)
        await page.wait_for_timeout(2000)
        await dismiss_dialogs_overlays_if_present(page)
    except Exception:
        pass

    result["final_url"] = getattr(page, "url", None)

    block_match = await _match_any(page, _BLOCK_SELECTORS)
    if block_match:
        result["cloudfront_blocked"] = True
        result["ready_selector"] = result["ready_selector"] or block_match
        return result

    login_match = await _match_any(page, _LOGIN_HINT_SELECTORS)
    if login_match:
        result["login_hint_found"] = True
        result["ready_selector"] = result["ready_selector"] or login_match
        return result

    empty_match = await _match_any(page, _EMPTY_STATE_SELECTORS)
    if empty_match:
        result["empty_state_found"] = True
        result["ready_selector"] = result["ready_selector"] or empty_match
        return result

    total_rows = 0
    for selector in _DIALOGS_READY_SELECTORS:
        total_rows += await _safe_count(page, selector)
    result["dialog_rows_found"] = total_rows

    if total_rows > 0:
        return result

    raise asyncio.TimeoutError(
        f"dialogs page did not become ready; final_url={result['final_url']} title={result['page_title']}"
    )