from __future__ import annotations

import asyncio
from typing import Any

from olx.markets.dialog_packs import get_dialog_pack
from olx.markets.helpers import get_market_dialogs_url


DEFAULT_DIALOGS_MARKET = "olx_pt"


def _build_dialogs_url(market_code: str = DEFAULT_DIALOGS_MARKET) -> str:
    pack = get_dialog_pack(market_code)
    base_url = get_market_dialogs_url(market_code)
    suffix = (pack.get("dialogs_url_suffix") or "").strip()
    return f"{base_url}{suffix}"


def _get_pack_selectors(market_code: str = DEFAULT_DIALOGS_MARKET) -> dict:
    pack = get_dialog_pack(market_code)
    return {
        "ready": list(pack.get("ready_selectors") or []),
        "empty": list(pack.get("empty_state_selectors") or []),
        "login": list(pack.get("login_hint_selectors") or []),
        "block": list(pack.get("block_selectors") or []),
        "overlay": list(pack.get("overlay_selectors") or []),
    }


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


async def dismiss_dialogs_overlays_if_present(
    page,
    *,
    market_code: str = DEFAULT_DIALOGS_MARKET,
) -> bool:
    selectors = _get_pack_selectors(market_code)["overlay"]
    dismissed = False

    for selector in selectors:
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
    market_code: str = DEFAULT_DIALOGS_MARKET,
) -> dict[str, Any]:
    selectors = _get_pack_selectors(market_code)
    dialogs_url = _build_dialogs_url(market_code)

    result: dict[str, Any] = {
        "target_url": dialogs_url,
        "final_url": None,
        "page_title": None,
        "dialog_rows_found": 0,
        "ready_selector": None,
        "empty_state_found": False,
        "login_hint_found": False,
        "cloudfront_blocked": False,
        "handled_soft_error_page": False,
        "market_code": market_code,
    }

    await page.goto(dialogs_url, wait_until="domcontentloaded", timeout=timeout)
    await page.wait_for_timeout(wait_after_ms)

    result["final_url"] = getattr(page, "url", None)
    try:
        result["page_title"] = await page.title()
    except Exception:
        result["page_title"] = None

    await dismiss_dialogs_overlays_if_present(page, market_code=market_code)

    for _ in range(3):
        try:
            await page.mouse.move(300, 220)
            await page.mouse.wheel(0, 700)
            await page.wait_for_timeout(500)
            await page.mouse.wheel(0, -450)
            await page.wait_for_timeout(500)
        except Exception:
            break

    block_match = await _match_any(page, selectors["block"])
    if block_match:
        result["cloudfront_blocked"] = True
        result["ready_selector"] = block_match
        return result

    login_match = await _match_any(page, selectors["login"])
    if login_match:
        result["login_hint_found"] = True
        result["ready_selector"] = login_match
        return result

    ready_match = await _wait_for_any(
        page,
        selectors["ready"] + selectors["empty"] + selectors["login"] + selectors["block"],
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

    block_match = await _match_any(page, selectors["block"])
    if block_match:
        result["cloudfront_blocked"] = True
        if not result["ready_selector"]:
            result["ready_selector"] = block_match
        return result

    login_match = await _match_any(page, selectors["login"])
    if login_match:
        result["login_hint_found"] = True
        if not result["ready_selector"]:
            result["ready_selector"] = login_match
        return result

    empty_match = await _match_any(page, selectors["empty"])
    if empty_match:
        result["empty_state_found"] = True
        result["ready_selector"] = result["ready_selector"] or empty_match
        return result

    total_rows = 0
    for selector in selectors["ready"]:
        total_rows += await _safe_count(page, selector)
    result["dialog_rows_found"] = total_rows

    if total_rows > 0:
        return result

    try:
        await page.reload(wait_until="domcontentloaded", timeout=timeout)
        await page.wait_for_timeout(2000)
        await dismiss_dialogs_overlays_if_present(page, market_code=market_code)
    except Exception:
        pass

    result["final_url"] = getattr(page, "url", None)

    block_match = await _match_any(page, selectors["block"])
    if block_match:
        result["cloudfront_blocked"] = True
        result["ready_selector"] = result["ready_selector"] or block_match
        return result

    login_match = await _match_any(page, selectors["login"])
    if login_match:
        result["login_hint_found"] = True
        result["ready_selector"] = result["ready_selector"] or login_match
        return result

    empty_match = await _match_any(page, selectors["empty"])
    if empty_match:
        result["empty_state_found"] = True
        result["ready_selector"] = result["ready_selector"] or empty_match
        return result

    total_rows = 0
    for selector in selectors["ready"]:
        total_rows += await _safe_count(page, selector)
    result["dialog_rows_found"] = total_rows

    if total_rows > 0:
        return result

    raise asyncio.TimeoutError(
        f"dialogs page did not become ready; "
        f"market={market_code} final_url={result['final_url']} title={result['page_title']}"
    )