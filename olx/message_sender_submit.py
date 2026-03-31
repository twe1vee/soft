from __future__ import annotations

from typing import Any

from olx.message_sender_chat import has_chat_root
from olx.message_sender_debug import normalize_text
from olx.message_sender_page import page_body_text


SEND_BUTTON_TEXTS = [
    "Enviar mensagem",
    "Wyślij",
    "Отправить",
    "Send",
    "Enviar",
]

STRICT_SEND_BUTTON_SELECTORS = [
    '[data-testid="chat-form-container"] button[aria-label="Submit message"][type="submit"]',
    'button[aria-label="Submit message"][type="submit"]',
    '[data-testid="chat-form-container"] button[type="submit"]',
]

MESSAGE_SURFACE_SELECTORS = [
    '[data-testid="messages-list-container"] [data-testid="sent-message"]',
    '[data-testid="messages-list-container"] [data-cy="chat-message-bubble"]',
    '[data-testid="messages-list-container"] [data-testid="status-icon-SENT"]',
]


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


async def click_send_button(page, input_locator) -> bool:
    for selector in STRICT_SEND_BUTTON_SELECTORS:
        locator = page.locator(selector).first

        try:
            await locator.wait_for(state="attached", timeout=2000)
        except Exception:
            pass

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
                return True
        except Exception:
            pass

        try:
            await locator.click(timeout=2500)
            return True
        except Exception:
            pass

        try:
            await locator.click(force=True, timeout=2500)
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
                return True
            except Exception:
                pass

            try:
                await item.click(force=True, timeout=2500)
                return True
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
            return True
        except Exception:
            continue

    return False


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


async def verify_message_sent(page, input_locator, message_text: str) -> dict[str, Any]:
    target_text = normalize_text(message_text)

    verification: dict[str, Any] = {
        "post_send_message_visible": False,
        "post_send_input_empty": False,
        "post_send_chat_root_found": False,
        "post_send_body_has_text": False,
        "post_send_url": None,
        "delivery_verified": False,
        "post_send_exact_message_match_count": 0,
        "post_send_sent_status_found": False,
        "post_send_sent_message_found": False,
    }

    for _ in range(10):
        await page.wait_for_timeout(1000)

        try:
            verification["post_send_url"] = page.url
        except Exception:
            pass

        try:
            verification["post_send_chat_root_found"] = await has_chat_root(page)
        except Exception:
            pass

        input_value = ""
        try:
            input_value = await read_input_value(input_locator)
            verification["post_send_input_empty"] = not bool(input_value)
        except Exception:
            verification["post_send_input_empty"] = False

        try:
            body_text = await page_body_text(page)
            verification["post_send_body_has_text"] = bool(
                target_text and target_text in body_text
            )
        except Exception:
            verification["post_send_body_has_text"] = False

        try:
            sent_status = page.locator(
                '[data-testid="messages-list-container"] [data-testid="status-icon-SENT"]'
            ).first
            verification["post_send_sent_status_found"] = (
                await sent_status.count() > 0 and await sent_status.is_visible()
            )
        except Exception:
            verification["post_send_sent_status_found"] = False

        try:
            sent_message = page.locator(
                '[data-testid="messages-list-container"] [data-testid="sent-message"]'
            ).first
            verification["post_send_sent_message_found"] = (
                await sent_message.count() > 0 and await sent_message.is_visible()
            )
        except Exception:
            verification["post_send_sent_message_found"] = False

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
                                exact_match_count += 1
                                break
                        except Exception:
                            continue

                    if verification["post_send_message_visible"]:
                        break
                except Exception:
                    continue

        verification["post_send_exact_message_match_count"] = exact_match_count

        if (
            verification["post_send_sent_status_found"]
            and verification["post_send_input_empty"]
        ):
            verification["delivery_verified"] = True
            return verification

        if (
            verification["post_send_sent_message_found"]
            and verification["post_send_input_empty"]
        ):
            verification["delivery_verified"] = True
            return verification

        if verification["post_send_message_visible"] and verification["post_send_input_empty"]:
            verification["delivery_verified"] = True
            return verification

        if verification["post_send_input_empty"] and verification["post_send_chat_root_found"]:
            verification["delivery_verified"] = True
            return verification

        if (
            verification["post_send_body_has_text"]
            and verification["post_send_chat_root_found"]
            and verification["post_send_input_empty"]
        ):
            verification["delivery_verified"] = True
            return verification

    return verification