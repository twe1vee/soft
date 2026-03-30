from __future__ import annotations

import re
from typing import Any

LIST_ROW_SELECTORS = [
    '[data-testid^="conversations-list-item-"]',
    '[data-testid*="conversations-list-item"]',
    'a[href*="/myaccount/answer/"]',
    'a[href*="/myaccount/answers/"]',
]

NAME_SELECTOR = '[data-testid="list-item-user-name"]'
TITLE_SELECTOR = '[data-testid="list-item-context-title"]'
MESSAGE_SELECTOR = '[data-testid="list-item-message-text"]'
DATETIME_SELECTOR = '[data-testid="list-item-datetime"]'


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


async def _safe_count(locator) -> int:
    try:
        return await locator.count()
    except Exception:
        return 0


async def _safe_inner_text(locator, timeout_ms: int = 1200) -> str:
    try:
        return _norm(await locator.inner_text(timeout=timeout_ms))
    except Exception:
        return ""


async def _safe_attr(locator, name: str, timeout_ms: int = 1200) -> str | None:
    try:
        return await locator.get_attribute(name, timeout=timeout_ms)
    except Exception:
        return None


def build_incoming_message_key(
    *,
    conversation_key: str,
    seller_name: str | None,
    last_message_text: str | None,
    updated_hint: str | None,
) -> str:
    base = "|".join(
        [
            _norm(conversation_key),
            _norm(seller_name),
            _norm(last_message_text),
            _norm(updated_hint),
        ]
    )
    return f"incoming:{base}"


async def _pick_rows(page):
    best_locator = None
    best_selector = None
    best_count = 0

    for selector in LIST_ROW_SELECTORS:
        locator = page.locator(selector)
        count = await _safe_count(locator)
        print(f"[dialogs_parser] selector={selector} count={count}")

        if count > best_count:
            best_count = count
            best_locator = locator
            best_selector = selector

    print(f"[dialogs_parser] picked selector={best_selector} count={best_count}")
    return best_locator, best_selector, best_count


async def _extract_conversation_id(row) -> str | None:
    testid = _norm(await _safe_attr(row, "data-testid"))
    if testid:
        m = re.search(r"conversations-list-item-([A-Za-z0-9\-]+)$", testid)
        if m:
            return m.group(1)

    href = _norm(await _safe_attr(row, "href"))
    if not href:
        href = _norm(await _safe_attr(row.locator("a").first, "href"))

    if href:
        m = re.search(r"/myaccount/answer[s]?/([A-Za-z0-9\-]+)/?", href)
        if m:
            return m.group(1)

    return None


async def _is_outgoing_by_icon(row) -> bool:
    """
    Считаем сообщение исходящим только если иконка галочек находится
    максимально близко к preview последнего сообщения.

    Не берем любые svg из широких ancestor-контейнеров строки, потому что
    из-за этого unread-входящие тоже начинают считаться outgoing.
    """
    try:
        message_el = row.locator(MESSAGE_SELECTOR).first
        if await _safe_count(message_el) <= 0:
            return False
    except Exception:
        return False

    # 1) Самый надежный кейс: svg среди прямых соседей preview
    try:
        preceding_svg = message_el.locator('xpath=preceding-sibling::*[name()="svg"]')
        if await _safe_count(preceding_svg) > 0:
            return True
    except Exception:
        pass

    try:
        following_svg = message_el.locator('xpath=following-sibling::*[name()="svg"]')
        if await _safe_count(following_svg) > 0:
            return True
    except Exception:
        pass

    # 2) Иконка внутри ближайшего родителя preview, но только если там мало svg
    # и они локальны для блока сообщения, а не для всей строки диалога.
    try:
        parent = message_el.locator("xpath=ancestor::*[1]").first
        if await _safe_count(parent) > 0:
            svg_count = await _safe_count(parent.locator("svg"))
            if 0 < svg_count <= 2:
                return True
    except Exception:
        pass

    # 3) Очень узкий wrapper вокруг message-text
    try:
        wrappers = row.locator(
            'xpath=.//*[contains(@data-testid,"list-item-message-text")]/ancestor::*[count(.//svg) > 0][1]'
        )
        if await _safe_count(wrappers) > 0:
            wrapper = wrappers.first
            svg_count = await _safe_count(wrapper.locator("svg"))

            # Берем только маленький локальный контейнер, а не широкий блок строки
            text_preview = await _safe_inner_text(message_el, timeout_ms=600)
            wrapper_text = await _safe_inner_text(wrapper, timeout_ms=600)

            if (
                0 < svg_count <= 2
                and wrapper_text
                and text_preview
                and len(wrapper_text) <= max(len(text_preview) + 40, 120)
            ):
                return True
    except Exception:
        pass

    return False

async def _is_unread_by_section(row) -> bool:
    """
    Пытаемся понять, находится ли строка в секции NÃO LIDAS / unread.
    """
    try:
        unread_title = row.locator(
            'xpath=preceding::*[@data-testid="unread-section-title"][1]'
        ).first
        read_title = row.locator(
            'xpath=preceding::*[@data-testid="read-section-title"][1]'
        ).first

        unread_exists = await _safe_count(unread_title) > 0
        read_exists = await _safe_count(read_title) > 0

        if unread_exists and not read_exists:
            return True

        if unread_exists and read_exists:
            unread_text = (await _safe_inner_text(unread_title, timeout_ms=600)).lower()
            read_text = (await _safe_inner_text(read_title, timeout_ms=600)).lower()
            if unread_text and not read_text:
                return True
    except Exception:
        pass

    try:
        section = row.locator("xpath=ancestor::section[1]").first
        if await _safe_count(section) > 0:
            section_text = (await _safe_inner_text(section, timeout_ms=1200)).lower()
            if "não lidas" in section_text or "nao lidas" in section_text:
                return True
            if "lidas" in section_text:
                return False
    except Exception:
        pass

    return False


async def _parse_single_row(row) -> dict[str, Any] | None:
    conversation_id = await _extract_conversation_id(row)
    if not conversation_id:
        print("[dialogs_parser] row_skip no conversation_id")
        return None

    seller_name = await _safe_inner_text(row.locator(NAME_SELECTOR).first)
    ad_title = await _safe_inner_text(row.locator(TITLE_SELECTOR).first)
    last_message_text = await _safe_inner_text(row.locator(MESSAGE_SELECTOR).first)
    updated_hint = await _safe_inner_text(row.locator(DATETIME_SELECTOR).first)

    if not seller_name and not ad_title and not last_message_text:
        print(f"[dialogs_parser] row_skip empty conversation_id={conversation_id}")
        return None

    is_outgoing = await _is_outgoing_by_icon(row)
    is_unread = await _is_unread_by_section(row)

    if is_outgoing:
        direction_guess = "outgoing"
    elif is_unread:
        direction_guess = "incoming"
    else:
        direction_guess = "unknown"

    conversation_key = conversation_id
    conversation_url = f"https://www.olx.pt/myaccount/answer/{conversation_id}/?my_ads=0"

    return {
        "conversation_key": conversation_key,
        "conversation_url": conversation_url,
        "seller_name": seller_name or None,
        "ad_title": ad_title or None,
        "ad_url": None,
        "ad_external_id": None,
        "last_message_text": last_message_text or None,
        "updated_hint": updated_hint or None,
        "is_unread": is_unread,
        "last_message_direction_guess": direction_guess,
    }


async def parse_dialogs_page(page) -> list[dict[str, Any]]:
    locator, selector, count = await _pick_rows(page)

    if locator is None or count <= 0:
        print("[dialogs_parser] rows_found=0")
        return []

    parsed: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    for i in range(count):
        try:
            row = locator.nth(i)
            item = await _parse_single_row(row)
        except Exception as exc:
            print(f"[dialogs_parser] row_failed index={i} error={exc!r}")
            continue

        if not item:
            print(f"[dialogs_parser] row_empty index={i}")
            continue

        key = item["conversation_key"]
        if key in seen_keys:
            print(f"[dialogs_parser] row_duplicate index={i} key={key}")
            continue

        seen_keys.add(key)
        parsed.append(item)

        print(
            f"[dialogs_parser] row_ok index={i} "
            f"key={item['conversation_key']} "
            f"seller={item.get('seller_name')} "
            f"title={item.get('ad_title')} "
            f"msg={item.get('last_message_text')} "
            f"time={item.get('updated_hint')} "
            f"is_unread={item.get('is_unread')} "
            f"direction={item.get('last_message_direction_guess')}"
        )

    print(f"[dialogs_parser] parsed_total={len(parsed)} selector={selector}")
    return parsed