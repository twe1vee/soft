from __future__ import annotations

import hashlib
import re
from typing import Any

from playwright.async_api import Locator, Page

DIALOG_ITEM_SELECTORS = [
    '[data-testid="chat-list-item"]',
    '[data-testid="conversation-item"]',
    '[data-testid*="conversation-item"]',
    '[data-testid*="chat-list-item"]',
    '[data-cy="conversation-row"]',
    '[data-cy="chat-row"]',
    'main a[href*="/myaccount/answers/"]',
]

SELLER_NAME_SELECTORS = [
    '[data-testid="conversation-user-name"]',
    '[data-testid="chat-user-name"]',
    '[data-testid*="seller-name"]',
    '[data-testid*="user-name"]',
    'h4',
    'h3',
    'strong',
]

AD_TITLE_SELECTORS = [
    '[data-testid="conversation-ad-title"]',
    '[data-testid="chat-ad-title"]',
    '[data-testid*="ad-title"]',
    '[data-testid*="listing-title"]',
    '[data-cy="ad-title"]',
    'p',
    'span',
]

LAST_MESSAGE_SELECTORS = [
    '[data-testid="conversation-last-message"]',
    '[data-testid="chat-last-message"]',
    '[data-testid*="last-message"]',
    '[data-testid*="message-preview"]',
    '[data-cy="last-message"]',
    'p',
    'span',
]

TIME_HINT_SELECTORS = [
    'time',
    '[data-testid="conversation-time"]',
    '[data-testid="chat-time"]',
    '[data-testid*="timestamp"]',
    '[data-testid*="time"]',
]

UNREAD_SELECTORS = [
    '[data-testid="unread-badge"]',
    '[data-testid*="unread"]',
    '[data-cy="unread-badge"]',
    '[aria-label*="unread" i]',
    '[aria-label*="não lida" i]',
]


def _normalize_space(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _extract_ad_external_id(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"\bID[A-Za-z0-9]+\b", value)
    return match.group(0) if match else None


def _make_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def collect_dialog_rows(page: Page) -> list[Locator]:
    best_selector = None
    best_count = 0

    for selector in DIALOG_ITEM_SELECTORS:
        try:
            locator = page.locator(selector)
            count = await locator.count()
            if count > best_count:
                best_count = count
                best_selector = selector
        except Exception:
            continue

    if not best_selector or best_count == 0:
        return []

    locator = page.locator(best_selector)
    return [locator.nth(i) for i in range(best_count)]


async def parse_dialog_row(locator: Locator) -> dict[str, Any]:
    seller_name = await extract_dialog_seller_name(locator)
    ad_title = await extract_dialog_ad_title(locator)
    last_message_text = await extract_dialog_last_message(locator)
    conversation_url = await extract_dialog_href(locator)
    updated_hint = await extract_dialog_updated_hint(locator)
    is_unread = await extract_dialog_unread_flag(locator)
    raw_preview = await _safe_inner_text(locator)

    ad_external_id = (
        _extract_ad_external_id(ad_title)
        or _extract_ad_external_id(last_message_text)
        or _extract_ad_external_id(conversation_url)
        or _extract_ad_external_id(raw_preview)
    )

    ad_url = await extract_dialog_ad_url(locator, raw_preview)

    conversation_key = build_dialog_fingerprint(
        conversation_url=conversation_url,
        seller_name=seller_name,
        ad_title=ad_title,
        ad_external_id=ad_external_id,
    )

    last_message_direction_guess = guess_message_direction(
        last_message_text=last_message_text,
        raw_preview=raw_preview,
        seller_name=seller_name,
    )

    return {
        "conversation_key": conversation_key,
        "conversation_url": conversation_url,
        "seller_name": seller_name,
        "ad_title": ad_title,
        "ad_url": ad_url,
        "ad_external_id": ad_external_id,
        "last_message_text": last_message_text,
        "last_message_direction_guess": last_message_direction_guess,
        "is_unread": is_unread,
        "updated_hint": updated_hint,
        "raw_preview": raw_preview,
    }


async def parse_dialogs_page(page: Page) -> list[dict[str, Any]]:
    rows = await collect_dialog_rows(page)
    parsed: list[dict[str, Any]] = []

    for row in rows:
        try:
            item = await parse_dialog_row(row)
            if item["conversation_key"]:
                parsed.append(item)
        except Exception:
            continue

    return parsed


def build_dialog_fingerprint(
    *,
    conversation_url: str | None,
    seller_name: str | None,
    ad_title: str | None,
    ad_external_id: str | None,
) -> str:
    stable = "|".join(
        [
            _normalize_space(conversation_url),
            _normalize_space(seller_name).lower(),
            _normalize_space(ad_title).lower(),
            _normalize_space(ad_external_id),
        ]
    )
    return _make_sha256(stable)


def build_incoming_message_key(
    *,
    conversation_key: str,
    seller_name: str | None,
    last_message_text: str | None,
    updated_hint: str | None,
) -> str:
    stable = "|".join(
        [
            _normalize_space(conversation_key),
            _normalize_space(seller_name).lower(),
            _normalize_space(last_message_text),
            _normalize_space(updated_hint),
        ]
    )
    return _make_sha256(stable)


def guess_message_direction(
    *,
    last_message_text: str | None,
    raw_preview: str | None,
    seller_name: str | None,
) -> str:
    text = _normalize_space(last_message_text).lower()
    preview = _normalize_space(raw_preview).lower()
    seller = _normalize_space(seller_name).lower()

    if not text and not preview:
        return "unknown"

    if seller and seller in text:
        return "incoming"

    if seller and seller in preview:
        return "incoming"

    if text.startswith("você:") or text.startswith("tu:") or text.startswith("you:") or text.startswith("eu:"):
        return "outgoing"

    if preview.startswith("você:") or preview.startswith("tu:") or preview.startswith("you:") or preview.startswith("eu:"):
        return "outgoing"

    if (
        "respondeu" in preview
        or "enviou uma mensagem" in preview
        or "mandou mensagem" in preview
        or "nova mensagem" in preview
    ):
        return "incoming"

    return "unknown"

async def extract_dialog_href(locator: Locator) -> str | None:
    candidates = [
        locator,
        locator.locator('a[href*="/myaccount/answers/"]').first,
        locator.locator("a").first,
    ]

    for candidate in candidates:
        try:
            href = await candidate.get_attribute("href")
            href = _normalize_space(href)
            if href:
                return href
        except Exception:
            continue

    return None


async def extract_dialog_ad_url(locator: Locator, raw_preview: str | None = None) -> str | None:
    try:
        links = locator.locator('a[href*="/d/anuncio/"]')
        count = await links.count()
        for i in range(count):
            href = _normalize_space(await links.nth(i).get_attribute("href"))
            if href:
                return href
    except Exception:
        pass

    match = re.search(r'https?://[^\s"]+/d/anuncio/[^\s"]+', raw_preview or "")
    if match:
        return match.group(0)

    return None


async def extract_dialog_seller_name(locator: Locator) -> str | None:
    for selector in SELLER_NAME_SELECTORS:
        try:
            candidate = locator.locator(selector).first
            if await candidate.count() == 0:
                continue
            text = _normalize_space(await candidate.inner_text())
            if text and len(text) <= 120:
                return text
        except Exception:
            continue
    return None


async def extract_dialog_ad_title(locator: Locator) -> str | None:
    texts_seen: list[str] = []

    for selector in AD_TITLE_SELECTORS:
        try:
            candidates = locator.locator(selector)
            count = await candidates.count()
            for i in range(min(count, 5)):
                text = _normalize_space(await candidates.nth(i).inner_text())
                if not text or text in texts_seen:
                    continue
                texts_seen.append(text)

                if len(text) < 3:
                    continue

                if _extract_ad_external_id(text):
                    return text

                if len(text) <= 220 and not _looks_like_time_hint(text):
                    return text
        except Exception:
            continue

    return None


async def extract_dialog_last_message(locator: Locator) -> str | None:
    for selector in LAST_MESSAGE_SELECTORS:
        try:
            candidates = locator.locator(selector)
            count = await candidates.count()
            for i in range(min(count, 6)):
                text = _normalize_space(await candidates.nth(i).inner_text())
                if not text:
                    continue
                if _looks_like_time_hint(text):
                    continue
                if len(text) <= 500:
                    return text
        except Exception:
            continue

    return None


async def extract_dialog_updated_hint(locator: Locator) -> str | None:
    for selector in TIME_HINT_SELECTORS:
        try:
            candidate = locator.locator(selector).first
            if await candidate.count() == 0:
                continue
            text = _normalize_space(await candidate.inner_text())
            if text:
                return text
        except Exception:
            continue
    return None


async def extract_dialog_unread_flag(locator: Locator) -> bool:
    for selector in UNREAD_SELECTORS:
        try:
            candidate = locator.locator(selector).first
            if await candidate.count() == 0:
                continue
            if await candidate.is_visible():
                return True
        except Exception:
            continue

    try:
        class_name = await locator.get_attribute("class")
        if class_name and "unread" in class_name.lower():
            return True
    except Exception:
        pass

    try:
        aria_label = await locator.get_attribute("aria-label")
        if aria_label:
            label = aria_label.lower()
            if "unread" in label or "não lida" in label:
                return True
    except Exception:
        pass

    return False


def _looks_like_time_hint(value: str) -> bool:
    text = _normalize_space(value).lower()
    if not text:
        return False

    patterns = [
        r"^\d{1,2}:\d{2}$",
        r"^\d{1,2}/\d{1,2}$",
        r"^\d{1,2}-\d{1,2}$",
        r"^(hoje|ontem|today|yesterday)$",
        r"^\d+\s*(min|mins|minutos|h|horas|d|dias)$",
    ]
    return any(re.match(pattern, text) for pattern in patterns)


async def _safe_inner_text(locator: Locator) -> str | None:
    try:
        return _normalize_space(await locator.inner_text())
    except Exception:
        return None