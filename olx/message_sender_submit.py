from __future__ import annotations

from typing import Any
from pathlib import Path

from olx.markets.message_helpers import (
    get_button_texts,
    get_delivery_failed_texts,
)
from olx.message_sender_chat import has_chat_root
from olx.message_sender_debug import normalize_text
from olx.message_sender_page import page_body_text


DEFAULT_MESSAGE_MARKET = "olx_pt"

STRICT_SEND_BUTTON_SELECTORS = [
    '[data-testid="chat-form-container"] button[aria-label="Submit message"][type="submit"]',
    'button[aria-label="Submit message"][type="submit"]',
    '[data-testid="chat-form-container"] button[type="submit"]',
]

STRICT_SENT_STATUS_SELECTORS = [
    '[data-testid="messages-list-container"] [data-testid="status-icon-SENT"]',
    '[data-testid="messages-list-container"] [data-testid="sentChatIcon-SENT"]',
]

STRICT_FAILED_STATUS_SELECTORS = [
    '[data-testid="messages-list-container"] [data-testid="status-icon-ERROR"]',
    '[data-testid="messages-list-container"] [data-testid="sentChatIcon-ERROR"]',
]

MESSAGE_SURFACE_SELECTORS = [
    '[data-testid="messages-list-container"] [data-testid="sent-message"]',
    '[data-testid="messages-list-container"] [data-cy="sent-message"]',
    '[data-testid="messages-list-container"] [data-cy="chat-message-bubble"]',
    '[data-testid="messages-list-container"] [data-testid="message"]',
]

ATTACHMENT_INPUT_SELECTORS = [
    'input[data-testid="attachment-upload-button"]',
    'input[data-cy="attachment-upload-button"]',
    'input#documents-upload',
]

ATTACHMENT_PREVIEW_SELECTORS = [
    '[data-testid="attachment-preview-item"]',
]

ATTACHMENT_REMOVE_SELECTORS = [
    '[data-testid="attachment-remove"]',
]

POST_SEND_LOADING_SELECTORS = [
    '[data-testid="chat-form-container"] [data-testid="loader"]',
    '[data-testid="chat-form-container"] [data-cy="loader"]',
    '[data-testid="chat-form-container"] [data-nx-name="OLoader"]',
]


def _build_send_button_texts(market_code: str = DEFAULT_MESSAGE_MARKET) -> list[str]:
    values = []
    seen = set()

    defaults = [
        "Enviar mensagem",
        "Wyślij",
        "Отправить",
        "Send",
        "Enviar",
    ]
    packed = get_button_texts("send", market_code)

    for item in [*packed, *defaults]:
        text = (item or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        values.append(text)

    return values


def _build_failed_message_hints(market_code: str = DEFAULT_MESSAGE_MARKET) -> list[str]:
    values = []
    seen = set()

    defaults = [
        "Não podes enviar esta mensagem",
        "Clica para tentar de novo",
        "Toca para tentar de novo",
        "Tenta de novo",
        "Não foi possível enviar",
        "Mensagem não enviada",
    ]
    packed = get_delivery_failed_texts(market_code)

    for item in [*packed, *defaults]:
        text = (item or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        values.append(text)

    return values


def _build_failed_message_selectors(market_code: str = DEFAULT_MESSAGE_MARKET) -> list[str]:
    return [f"text={item}" for item in _build_failed_message_hints(market_code)]


def _build_pending_message_hints(market_code: str = DEFAULT_MESSAGE_MARKET) -> list[str]:
    values = []
    seen = set()

    defaults = [
        "A enviar",
        "A enviar…",
        "A enviar...",
        "Enviando",
        "Sending",
    ]

    for item in defaults:
        text = (item or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        values.append(text)

    return values


async def _find_first_visible_locator(page, selectors: list[str]):
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if await locator.count() == 0:
                continue
            if await locator.is_visible():
                return locator
        except Exception:
            continue
    return None


async def _remove_existing_attachment_previews(page) -> int:
    removed = 0

    try:
        remove_locator = await _find_first_visible_locator(page, ATTACHMENT_REMOVE_SELECTORS)
        if remove_locator is None:
            return removed
    except Exception:
        return removed

    for _ in range(5):
        try:
            locator = await _find_first_visible_locator(page, ATTACHMENT_REMOVE_SELECTORS)
            if locator is None:
                break

            try:
                await locator.scroll_into_view_if_needed()
            except Exception:
                pass

            try:
                await locator.click(timeout=2000)
            except Exception:
                await locator.click(force=True, timeout=2000)

            removed += 1
            await page.wait_for_timeout(350)
        except Exception:
            break

    return removed


async def attach_template_image(
    page,
    image_path: str,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "template_image_requested": bool((image_path or "").strip()),
        "template_image_path": image_path,
        "template_image_attached": False,
        "template_image_preview_visible": False,
        "template_image_error": None,
        "template_image_filename": None,
        "template_image_removed_old_previews": 0,
    }

    path_text = (image_path or "").strip()
    if not path_text:
        return data

    path = Path(path_text)
    if not path.exists() or not path.is_file():
        data["template_image_error"] = f"Файл фото шаблона не найден: {path_text}"
        return data

    data["template_image_filename"] = path.name

    try:
        data["template_image_removed_old_previews"] = await _remove_existing_attachment_previews(page)
    except Exception:
        pass

    input_locator = None
    for selector in ATTACHMENT_INPUT_SELECTORS:
        try:
            locator = page.locator(selector).first
            if await locator.count() == 0:
                continue
            input_locator = locator
            break
        except Exception:
            continue

    if input_locator is None:
        data["template_image_error"] = "Не найден input для загрузки вложения"
        return data

    try:
        await input_locator.set_input_files(str(path))
    except Exception as exc:
        data["template_image_error"] = f"Не удалось загрузить файл в input: {exc}"
        return data

    preview_visible = False

    for _ in range(12):
        await page.wait_for_timeout(500)

        for selector in ATTACHMENT_PREVIEW_SELECTORS:
            try:
                previews = page.locator(selector)
                count = await previews.count()
                if count <= 0:
                    continue

                for i in range(min(count, 10)):
                    item = previews.nth(i)
                    try:
                        if not await item.is_visible():
                            continue

                        filename = (await item.get_attribute("data-filename") or "").strip()
                        if not filename or filename == path.name:
                            preview_visible = True
                            break
                    except Exception:
                        continue

                if preview_visible:
                    break
            except Exception:
                continue

        if preview_visible:
            break

    data["template_image_preview_visible"] = preview_visible
    data["template_image_attached"] = preview_visible

    if not preview_visible and not data["template_image_error"]:
        data["template_image_error"] = "OLX не показал preview загруженного вложения"

    return data


async def fill_message_input(locator, message_text: str) -> None:
    tag_name = await locator.evaluate("(el) => el.tagName.toLowerCase()")

    if tag_name == "textarea":
        try:
            await locator.fill(message_text)
            return
        except Exception:
            await locator.click()
            await locator.press("Control+A")
            await locator.type(message_text, delay=20)
            return

    contenteditable = await locator.evaluate(
        "(el) => el.getAttribute('contenteditable')"
    )
    if contenteditable:
        await locator.click()
        try:
            await locator.fill(message_text)
        except Exception:
            try:
                await locator.evaluate(
                    "(el, value) => { el.innerHTML = ''; el.textContent = value; }",
                    message_text,
                )
            except Exception:
                await locator.type(message_text, delay=20)
        return

    try:
        await locator.fill(message_text)
    except Exception:
        await locator.click()
        await locator.type(message_text, delay=20)


async def _is_clickable_send_button(locator) -> bool:
    try:
        if await locator.count() == 0:
            return False
    except Exception:
        return False

    try:
        if not await locator.is_visible():
            return False
    except Exception:
        return False

    try:
        disabled = await locator.get_attribute("disabled")
        aria_disabled = await locator.get_attribute("aria-disabled")
        if disabled is not None:
            return False
        if (aria_disabled or "").lower() == "true":
            return False
    except Exception:
        pass

    return True


async def _click_share_personal_data_warning_if_present(page) -> bool:
    candidates = [
        page.locator(
            'button[data-clickoutsideidentifier="fraud-got-it"][data-button-variant="tertiary"]'
        ).filter(has_text="Partilhar").first,
        page.locator(
            'button[data-clickoutsideidentifier="fraud-got-it"][data-button-variant="tertiary"]'
        ).first,
        page.get_by_role("button", name="Partilhar").first,
        page.locator('button:has-text("Partilhar")').first,
    ]

    for warning_btn in candidates:
        try:
            if await warning_btn.count() == 0:
                continue

            if not await warning_btn.is_visible():
                continue

            try:
                await warning_btn.scroll_into_view_if_needed()
            except Exception:
                pass

            try:
                await warning_btn.click(timeout=2500)
            except Exception:
                try:
                    box = await warning_btn.bounding_box()
                    if box:
                        x = box["x"] + box["width"] / 2
                        y = box["y"] + box["height"] / 2
                        await page.mouse.move(x, y)
                        await page.wait_for_timeout(100)
                        await page.mouse.click(x, y)
                    else:
                        raise RuntimeError("warning button bounding box is empty")
                except Exception:
                    try:
                        await warning_btn.click(force=True, timeout=2500)
                    except Exception:
                        continue

            await page.wait_for_timeout(1000)
            return True

        except Exception:
            continue

    return False


async def _try_unblock_send_button_by_warning(page) -> dict[str, Any]:
    handled = await _click_share_personal_data_warning_if_present(page)
    if not handled:
        return {
            "warning_handled": False,
            "submit_unblocked": False,
        }

    for selector in STRICT_SEND_BUTTON_SELECTORS:
        locator = page.locator(selector).first
        if await _is_clickable_send_button(locator):
            return {
                "warning_handled": True,
                "submit_unblocked": True,
            }

    try:
        submit_btn = page.locator('button[aria-label="Submit message"]').first
        return {
            "warning_handled": True,
            "submit_unblocked": await _is_clickable_send_button(submit_btn),
        }
    except Exception:
        return {
            "warning_handled": True,
            "submit_unblocked": False,
        }


async def click_send_button(
    page,
    input_locator,
    *,
    market_code: str = DEFAULT_MESSAGE_MARKET,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "send_clicked": False,
        "personal_data_warning_handled": False,
    }

    warning_unblock_attempted = False

    for selector in STRICT_SEND_BUTTON_SELECTORS:
        locator = page.locator(selector).first

        try:
            await locator.wait_for(state="attached", timeout=2000)
        except Exception:
            pass

        if not await _is_clickable_send_button(locator):
            if not warning_unblock_attempted:
                warning_unblock_attempted = True
                warning_result = await _try_unblock_send_button_by_warning(page)
                if warning_result.get("warning_handled"):
                    result["personal_data_warning_handled"] = True

            if not await _is_clickable_send_button(locator):
                continue

        try:
            await locator.scroll_into_view_if_needed()
        except Exception:
            pass

        try:
            box = await locator.bounding_box()
            if box:
                x = box["x"] + box["width"] / 2
                y = box["y"] + box["height"] / 2
                await page.mouse.move(x, y)
                await page.wait_for_timeout(100)
                await page.mouse.click(x, y)
                result["send_clicked"] = True
                return result
        except Exception:
            pass

        try:
            await locator.click(timeout=2500)
            result["send_clicked"] = True
            return result
        except Exception:
            pass

        try:
            await locator.click(force=True, timeout=2500)
            result["send_clicked"] = True
            return result
        except Exception:
            continue

    fallback_candidates = []
    for text in _build_send_button_texts(market_code):
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

            if not await _is_clickable_send_button(item):
                if not warning_unblock_attempted:
                    warning_unblock_attempted = True
                    warning_result = await _try_unblock_send_button_by_warning(page)
                    if warning_result.get("warning_handled"):
                        result["personal_data_warning_handled"] = True

                if not await _is_clickable_send_button(item):
                    continue

            try:
                item_type = await item.get_attribute("type")
            except Exception:
                item_type = None

            try:
                aria_label = await item.get_attribute("aria-label")
            except Exception:
                aria_label = None

            allow_click = (
                item_type == "submit"
                or (aria_label or "").lower() == "submit message"
            )

            if not allow_click:
                continue

            try:
                await item.scroll_into_view_if_needed()
            except Exception:
                pass

            try:
                await item.click(timeout=2500)
                result["send_clicked"] = True
                return result
            except Exception:
                pass

            try:
                await item.click(force=True, timeout=2500)
                result["send_clicked"] = True
                return result
            except Exception:
                continue

    for hotkey in ("Control+Enter", "Meta+Enter", "Enter"):
        try:
            await input_locator.focus()
        except Exception:
            pass

        try:
            await input_locator.press(hotkey)
            await page.wait_for_timeout(300)
            result["send_clicked"] = True
            return result
        except Exception:
            continue

    return result


async def read_input_value(locator) -> str:
    try:
        tag_name = await locator.evaluate("(el) => el.tagName.toLowerCase()")
    except Exception:
        return ""

    try:
        if tag_name == "textarea":
            value = await locator.input_value()
            return normalize_text(value)
    except Exception:
        pass

    try:
        contenteditable = await locator.evaluate(
            "(el) => el.getAttribute('contenteditable')"
        )
        if contenteditable:
            text = await locator.evaluate("(el) => el.innerText || el.textContent || ''")
            return normalize_text(text)
    except Exception:
        pass

    return ""


async def detect_failed_message_state(
    page,
    *,
    market_code: str = DEFAULT_MESSAGE_MARKET,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "failed_message_detected": False,
        "failed_message_reason": None,
    }

    failed_hints = _build_failed_message_hints(market_code)
    failed_hints_lower = [(x or "").strip().lower() for x in failed_hints if (x or "").strip()]

    for selector in STRICT_FAILED_STATUS_SELECTORS:
        try:
            locator = page.locator(selector)
            count = await locator.count()

            for i in range(min(count, 20)):
                item = locator.nth(i)
                try:
                    if not await item.is_visible():
                        continue

                    reason_text = ""
                    try:
                        reason_text = normalize_text(await item.inner_text())
                    except Exception:
                        reason_text = ""

                    data["failed_message_detected"] = True
                    data["failed_message_reason"] = reason_text or selector
                    return data
                except Exception:
                    continue
        except Exception:
            continue

    label_selector = '[data-testid="messages-list-container"] [data-testid="message-status-label"]'
    try:
        labels = page.locator(label_selector)
        count = await labels.count()

        for i in range(min(count, 20)):
            item = labels.nth(i)
            try:
                if not await item.is_visible():
                    continue

                label_text = normalize_text(await item.inner_text())
                label_text_lower = label_text.lower()

                if any(hint in label_text_lower for hint in failed_hints_lower):
                    data["failed_message_detected"] = True
                    data["failed_message_reason"] = label_text
                    return data
            except Exception:
                continue
    except Exception:
        pass

    failed_selectors = _build_failed_message_selectors(market_code)

    for selector in failed_selectors:
        try:
            locator = page.locator(selector).first
            if await locator.count() == 0:
                continue
            if await locator.is_visible():
                data["failed_message_detected"] = True
                data["failed_message_reason"] = selector.replace("text=", "")
                return data
        except Exception:
            continue

    try:
        body_text = await page_body_text(page)
        body_text_lower = (body_text or "").lower()

        for hint in failed_hints:
            if hint.lower() in body_text_lower:
                data["failed_message_detected"] = True
                data["failed_message_reason"] = hint
                return data
    except Exception:
        pass

    return data


async def detect_pending_message_state(
    page,
    *,
    market_code: str = DEFAULT_MESSAGE_MARKET,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "pending_message_detected": False,
        "pending_message_reason": None,
    }

    pending_hints = _build_pending_message_hints(market_code)
    pending_hints_lower = [(x or "").strip().lower() for x in pending_hints if (x or "").strip()]

    label_selector = '[data-testid="messages-list-container"] [data-testid="message-status-label"]'
    try:
        labels = page.locator(label_selector)
        count = await labels.count()

        for i in range(min(count, 20)):
            item = labels.nth(i)
            try:
                if not await item.is_visible():
                    continue

                label_text = normalize_text(await item.inner_text())
                label_text_lower = label_text.lower()

                if any(hint in label_text_lower for hint in pending_hints_lower):
                    data["pending_message_detected"] = True
                    data["pending_message_reason"] = label_text
                    return data
            except Exception:
                continue
    except Exception:
        pass

    try:
        body_text = await page_body_text(page)
        body_text_lower = (body_text or "").lower()

        for hint in pending_hints:
            if hint.lower() in body_text_lower:
                data["pending_message_detected"] = True
                data["pending_message_reason"] = hint
                return data
    except Exception:
        pass

    return data


async def _has_visible_selector(page, selector: str, limit: int = 20) -> bool:
    try:
        locator = page.locator(selector)
        count = await locator.count()

        for i in range(min(count, limit)):
            item = locator.nth(i)
            try:
                if await item.is_visible():
                    return True
            except Exception:
                continue
    except Exception:
        return False

    return False


async def _detect_post_send_loader(page) -> bool:
    for selector in POST_SEND_LOADING_SELECTORS:
        if await _has_visible_selector(page, selector):
            return True
    return False


async def verify_message_sent(
    page,
    input_locator,
    message_text: str,
    *,
    market_code: str = DEFAULT_MESSAGE_MARKET,
    attachment_expected: bool = False,
    max_rounds: int = 14,
    round_wait_ms: int = 1250,
) -> dict[str, Any]:
    target_text = normalize_text(message_text)

    verification: dict[str, Any] = {
        "post_send_message_visible": False,
        "post_send_input_empty": False,
        "post_send_chat_root_found": False,
        "post_send_body_has_text": False,
        "post_send_url": None,
        "delivery_verified": False,
        "delivery_failed": False,
        "delivery_failed_reason": None,
        "post_send_exact_message_match_count": 0,
        "post_send_sent_status_found": False,
        "post_send_sent_message_found": False,
        "failed_message_detected": False,
        "failed_message_reason": None,
        "pending_message_detected": False,
        "pending_message_reason": None,
        "market_code": market_code,
        "attachment_expected": attachment_expected,
        "verification_rounds_used": 0,
        "post_send_loader_visible": False,
        "post_send_loader_rounds": 0,
        "post_send_input_nonempty_rounds": 0,
        "post_send_chat_root_rounds": 0,
        "post_send_sent_status_rounds": 0,
        "post_send_message_visible_rounds": 0,
    }

    for round_index in range(max_rounds):
        verification["verification_rounds_used"] = round_index + 1
        await page.wait_for_timeout(round_wait_ms)

        try:
            verification["post_send_url"] = page.url
        except Exception:
            pass

        try:
            verification["post_send_chat_root_found"] = await has_chat_root(page)
            if verification["post_send_chat_root_found"]:
                verification["post_send_chat_root_rounds"] += 1
        except Exception:
            pass

        try:
            input_value = await read_input_value(input_locator)
            verification["post_send_input_empty"] = not bool(input_value)
            if not verification["post_send_input_empty"]:
                verification["post_send_input_nonempty_rounds"] += 1
        except Exception:
            verification["post_send_input_empty"] = False

        try:
            verification["post_send_loader_visible"] = await _detect_post_send_loader(page)
            if verification["post_send_loader_visible"]:
                verification["post_send_loader_rounds"] += 1
        except Exception:
            verification["post_send_loader_visible"] = False

        try:
            body_text = await page_body_text(page)
            verification["post_send_body_has_text"] = bool(
                target_text and target_text in body_text
            )
        except Exception:
            verification["post_send_body_has_text"] = False

        try:
            failed_info = await detect_failed_message_state(page, market_code=market_code)
            verification["failed_message_detected"] = failed_info["failed_message_detected"]
            verification["failed_message_reason"] = failed_info["failed_message_reason"]
        except Exception:
            verification["failed_message_detected"] = False
            verification["failed_message_reason"] = None

        if verification["failed_message_detected"]:
            verification["delivery_verified"] = False
            verification["delivery_failed"] = True
            verification["delivery_failed_reason"] = (
                verification["failed_message_reason"]
                or "OLX показал ошибку доставки сообщения"
            )
            return verification

        try:
            pending_info = await detect_pending_message_state(page, market_code=market_code)
            verification["pending_message_detected"] = pending_info["pending_message_detected"]
            verification["pending_message_reason"] = pending_info["pending_message_reason"]
        except Exception:
            verification["pending_message_detected"] = False
            verification["pending_message_reason"] = None

        verification["post_send_sent_status_found"] = False
        for selector in STRICT_SENT_STATUS_SELECTORS:
            if await _has_visible_selector(page, selector):
                verification["post_send_sent_status_found"] = True
                verification["post_send_sent_status_rounds"] += 1
                break

        verification["post_send_sent_message_found"] = False
        for selector in [
            '[data-testid="messages-list-container"] [data-testid="sent-message"]',
            '[data-testid="messages-list-container"] [data-cy="sent-message"]',
        ]:
            if await _has_visible_selector(page, selector):
                verification["post_send_sent_message_found"] = True
                break

        exact_match_count = 0
        try:
            exact_locator = page.locator('[data-testid="messages-list-container"]').get_by_text(
                message_text,
                exact=True,
            )
            exact_match_count = await exact_locator.count()

            if exact_match_count > 0:
                for i in range(min(exact_match_count, 5)):
                    item = exact_locator.nth(i)
                    try:
                        if await item.is_visible():
                            verification["post_send_message_visible"] = True
                            verification["post_send_message_visible_rounds"] += 1
                            break
                    except Exception:
                        continue
        except Exception:
            pass

        if not verification["post_send_message_visible"]:
            for selector in MESSAGE_SURFACE_SELECTORS:
                try:
                    locator = page.locator(selector)
                    count = await locator.count()

                    for i in range(min(count, 80)):
                        item = locator.nth(i)
                        try:
                            if not await item.is_visible():
                                continue
                            text = normalize_text(await item.inner_text())
                            if text == target_text:
                                verification["post_send_message_visible"] = True
                                verification["post_send_message_visible_rounds"] += 1
                                exact_match_count += 1
                                break
                        except Exception:
                            continue

                    if verification["post_send_message_visible"]:
                        break
                except Exception:
                    continue

        verification["post_send_exact_message_match_count"] = exact_match_count

        if verification["post_send_sent_status_found"]:
            verification["delivery_verified"] = True
            return verification

        if (
            verification["post_send_sent_message_found"]
            and verification["post_send_input_empty"]
            and not verification["failed_message_detected"]
            and not verification["pending_message_detected"]
        ):
            verification["delivery_verified"] = True
            return verification

        if (
            verification["post_send_message_visible"]
            and verification["post_send_input_empty"]
            and not verification["failed_message_detected"]
            and not verification["pending_message_detected"]
        ):
            verification["delivery_verified"] = True
            return verification

        if (
            attachment_expected
            and verification["post_send_input_empty"]
            and verification["post_send_chat_root_found"]
            and not verification["failed_message_detected"]
            and not verification["pending_message_detected"]
            and round_index >= 3
        ):
            verification["delivery_verified"] = True
            return verification

        if verification["pending_message_detected"]:
            continue

    return verification