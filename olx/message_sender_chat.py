from __future__ import annotations

from olx.message_sender_debug import first_non_empty_text

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


def _chat_button_candidates(page):
    return [
        page.locator('[data-testid="chat-button"]').first,
        page.get_by_role("button", name="Enviar mensagem").first,
        page.locator("button:has-text('Enviar mensagem')").first,
        page.locator("a:has-text('Enviar mensagem')").first,
        page.locator("text=Enviar mensagem").first,
        page.get_by_role("button", name="Chat").first,
        page.locator("button:has-text('Chat')").first,
        page.locator("a:has-text('Chat')").first,
        page.get_by_role("button", name="Contactar").first,
        page.locator("button:has-text('Contactar')").first,
        page.locator("button:has-text('Contactar anunciante')").first,
        page.locator("a:has-text('Contactar anunciante')").first,
    ]


async def has_chat_root(page) -> bool:
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


async def find_message_input(page):
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


async def get_chat_button_debug(page) -> tuple[bool | None, str | None]:
    for locator in _chat_button_candidates(page):
        try:
            if await locator.count() == 0:
                continue
        except Exception:
            continue

        visible = None
        text = None

        try:
            visible = await locator.is_visible()
        except Exception:
            pass

        try:
            text = first_non_empty_text(await locator.inner_text())
        except Exception:
            pass

        return visible, text

    return None, None


async def click_chat_button(page) -> bool:
    for locator in _chat_button_candidates(page):
        try:
            if await locator.count() == 0:
                continue
        except Exception:
            continue

        try:
            await locator.wait_for(state="visible", timeout=5000)
        except Exception:
            continue

        try:
            await locator.scroll_into_view_if_needed()
            await page.wait_for_timeout(300)
        except Exception:
            pass

        try:
            box = await locator.bounding_box()
            if box:
                x = box["x"] + box["width"] / 2
                y = box["y"] + box["height"] / 2
                await page.mouse.move(x, y)
                await page.wait_for_timeout(150)
                await page.mouse.click(x, y)
                await page.wait_for_timeout(800)

                if await has_chat_root(page):
                    return True

                input_locator = await find_message_input(page)
                if input_locator is not None:
                    return True
        except Exception:
            pass

        try:
            await locator.click(timeout=5000)
            await page.wait_for_timeout(800)

            if await has_chat_root(page):
                return True

            input_locator = await find_message_input(page)
            if input_locator is not None:
                return True

            return True
        except Exception:
            pass

        try:
            await locator.click(force=True, timeout=5000)
            await page.wait_for_timeout(800)

            if await has_chat_root(page):
                return True

            input_locator = await find_message_input(page)
            if input_locator is not None:
                return True

            return True
        except Exception:
            continue

    return False


async def wait_for_chat_mount(page) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass

    for _ in range(8):
        try:
            if await has_chat_root(page):
                await page.wait_for_timeout(800)
                return
        except Exception:
            pass

        try:
            input_locator = await find_message_input(page)
            if input_locator is not None:
                await page.wait_for_timeout(800)
                return
        except Exception:
            pass

        await page.wait_for_timeout(1000)