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
]


async def fill_message_input(locator, message_text: str) -> None:
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


async def click_send_button(page, input_locator) -> bool:
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
    }

    for _ in range(8):
        await page.wait_for_timeout(1000)

        try:
            verification["post_send_url"] = page.url
        except Exception:
            pass

        try:
            verification["post_send_chat_root_found"] = await has_chat_root(page)
        except Exception:
            pass

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

        exact_match_count = 0

        try:
            exact_locator = page.get_by_text(message_text, exact=True)
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
            for selector in [
                "#chatPortalRoot *",
                "#root-portal *",
                '[data-testid="chat"] *',
                '[data-testid="chat-modal"] *',
            ]:
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

        if verification["post_send_message_visible"] and verification["post_send_input_empty"]:
            verification["delivery_verified"] = True
            return verification

    return verification