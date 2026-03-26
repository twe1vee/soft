from __future__ import annotations

from typing import Any

from olx.message_sender_debug import first_non_empty_text

MESSAGE_INPUT_SELECTORS = [
    "#chatPortalRoot textarea",
    "#root-portal textarea",
    '[data-testid="chat-modal"] textarea',
    '[data-testid="chat"] textarea',
    '[data-testid="conversation-message-input"] textarea',
    '[data-testid="message-input"] textarea',
    '[data-testid*="message"] textarea',
    '[data-testid*="conversation"] textarea',
    '[data-cy*="message"] textarea',
    ".css-1t3t97v textarea",
    'textarea[data-testid="message-input"]',
    'textarea[data-testid="textarea"]',
    'textarea[name="message"]',
    'textarea[placeholder*="mensagem" i]',
    'textarea[placeholder*="message" i]',
    'textarea[placeholder*="mensagem ao anunciante" i]',
    "textarea",
    "#chatPortalRoot [role='textbox']",
    "#root-portal [role='textbox']",
    '[data-testid="chat-modal"] [role="textbox"]',
    '[data-testid="chat"] [role="textbox"]',
    '[data-testid="conversation-message-input"] [role="textbox"]',
    '[data-testid*="message"] [role="textbox"]',
    '[data-testid*="conversation"] [role="textbox"]',
    '[role="dialog"] [role="textbox"]',
    '[role="textbox"]',
    '#chatPortalRoot [contenteditable="true"]',
    '#root-portal [contenteditable="true"]',
    '[data-testid="chat-modal"] [contenteditable="true"]',
    '[data-testid="chat"] [contenteditable="true"]',
    '[data-testid="conversation-message-input"] [contenteditable="true"]',
    '[role="dialog"] [contenteditable="true"]',
    '[contenteditable="true"]',
    'div[contenteditable="true"]',
]

CHAT_ROOT_SELECTORS = [
    "#chatPortalRoot",
    "#root-portal",
    '[data-testid="chat-modal"]',
    '[data-testid="chat"]',
    '[data-testid="conversation-message-input"]',
    '[data-testid*="chat"]',
    '[data-testid*="conversation"]',
    '[role="dialog"]',
    'aside[role="dialog"]',
    'div[role="dialog"]',
]

BLOCKING_HINT_SELECTORS = [
    'form[action*="login"]',
    'input[name="login[email]"]',
    'input[name="username"]',
    'input[type="password"]',
    '[data-testid*="login"]',
    '[data-testid*="auth"]',
    'button:has-text("Iniciar sessão")',
    'button:has-text("Entrar")',
    'button:has-text("Login")',
    'a:has-text("Iniciar sessão")',
    'a:has-text("Entrar")',
    'text=Iniciar sessão',
    'text=Entrar',
    'text=Faça login',
    'text=Fazer login',
    'text=Sign in',
    'text=Login',
    'text=Zaloguj',
    'text=Please log in',
    'text=Esta opção não está disponível',
    'text=Não foi possível iniciar o chat',
    'text=Não é possível enviar mensagem',
    'text=Anúncio inativo',
    'text=Usuário indisponível',
    'text=Este anúncio já não está disponível',
]


def _chat_button_candidates(page):
    return [
        (
            "seller_card_chat_button",
            page.locator('[data-cy="seller_card"] [data-testid="chat-button"]').first,
        ),
        (
            "ad_action_box_chat_button",
            page.locator('[data-testid="ad-action-box"] [data-testid="chat-button"]').first,
        ),
        (
            "generic_chat_button_enviar",
            page.locator('button[data-testid="chat-button"]').filter(has_text="Enviar mensagem").first,
        ),
        (
            "generic_chat_button_contactar",
            page.locator('button[data-testid="chat-button"]').filter(has_text="Contactar").first,
        ),
        (
            "role_button_enviar",
            page.get_by_role("button", name="Enviar mensagem").first,
        ),
        (
            "button_text_enviar",
            page.locator("button:has-text('Enviar mensagem')").first,
        ),
    ]


async def collect_element_debug(page, locator, label: str) -> dict[str, Any]:
    info: dict[str, Any] = {
        "label": label,
        "count": 0,
        "visible": None,
        "enabled": None,
        "text": None,
        "data_testid": None,
        "href": None,
        "class": None,
        "bounding_box": None,
        "click_point": None,
        "element_from_point": None,
        "outer_html": None,
    }

    try:
        info["count"] = await locator.count()
    except Exception as exc:
        info["error"] = f"count_failed: {exc}"
        return info

    if info["count"] == 0:
        return info

    el = locator.first

    try:
        info["visible"] = await el.is_visible()
    except Exception:
        pass

    try:
        info["enabled"] = await el.is_enabled()
    except Exception:
        pass

    try:
        info["text"] = first_non_empty_text(await el.inner_text())
    except Exception:
        pass

    try:
        info["data_testid"] = await el.get_attribute("data-testid")
        info["href"] = await el.get_attribute("href")
        info["class"] = await el.get_attribute("class")
        info["outer_html"] = await el.evaluate("(node) => node.outerHTML")
    except Exception:
        pass

    try:
        box = await el.bounding_box()
        info["bounding_box"] = box
        if box:
            x = box["x"] + box["width"] / 2
            y = box["y"] + box["height"] / 2
            info["click_point"] = {"x": x, "y": y}
            info["element_from_point"] = await page.evaluate(
                """([x, y]) => {
                    const el = document.elementFromPoint(x, y);
                    if (!el) return null;
                    return {
                        tag: el.tagName,
                        text: (el.innerText || "").trim().slice(0, 200),
                        dataTestid: el.getAttribute("data-testid"),
                        className: String(el.className || "").slice(0, 300),
                        outerHTML: (el.outerHTML || "").slice(0, 1500)
                    };
                }""",
                [x, y],
            )
    except Exception:
        pass

    return info


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


async def _locator_is_interactable(locator) -> bool:
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
        readonly = await locator.get_attribute("readonly")
        if disabled is not None:
            return False
        if (aria_disabled or "").lower() == "true":
            return False
        if readonly is not None:
            return False
    except Exception:
        pass

    return True


async def find_message_input(page):
    best_fallback = None

    for selector in MESSAGE_INPUT_SELECTORS:
        locator = page.locator(selector).first

        try:
            if await locator.count() == 0:
                continue
        except Exception:
            continue

        try:
            await locator.wait_for(state="attached", timeout=2500)
        except Exception:
            pass

        if await _locator_is_interactable(locator):
            return locator

        if best_fallback is None:
            try:
                if await locator.is_visible():
                    best_fallback = locator
            except Exception:
                pass

    return best_fallback


async def get_chat_button_debug(page) -> tuple[bool | None, str | None]:
    for _, locator in _chat_button_candidates(page):
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


async def click_chat_button(page) -> tuple[bool, dict[str, Any]]:
    debug: dict[str, Any] = {
        "chat_button_candidates": {},
        "clicked_candidate": None,
        "clicked_candidate_debug": None,
    }

    for name, locator in _chat_button_candidates(page):
        debug["chat_button_candidates"][name] = await collect_element_debug(page, locator, name)

    for name, locator in _chat_button_candidates(page):
        try:
            if await locator.count() == 0:
                continue
        except Exception:
            continue

        try:
            await locator.wait_for(state="visible", timeout=5000)
        except Exception:
            continue

        debug["clicked_candidate"] = name
        debug["clicked_candidate_debug"] = await collect_element_debug(page, locator, f"clicked::{name}")

        try:
            await locator.scroll_into_view_if_needed()
            await page.wait_for_timeout(300)
        except Exception:
            pass

        for click_mode in ("mouse", "normal", "force"):
            try:
                if click_mode == "mouse":
                    box = await locator.bounding_box()
                    if not box:
                        raise RuntimeError("bounding_box is empty")
                    x = box["x"] + box["width"] / 2
                    y = box["y"] + box["height"] / 2
                    await page.mouse.move(x, y)
                    await page.wait_for_timeout(150)
                    await page.mouse.click(x, y)
                elif click_mode == "normal":
                    await locator.click(timeout=5000)
                else:
                    await locator.click(force=True, timeout=5000)

                await page.wait_for_timeout(1200)

                if await has_chat_root(page):
                    debug["click_mode"] = click_mode
                    return True, debug

                input_locator = await find_message_input(page)
                if input_locator is not None:
                    debug["click_mode"] = click_mode
                    return True, debug

                if "chat=1" in (page.url or ""):
                    debug["click_mode"] = click_mode
                    return True, debug

            except Exception as exc:
                debug[f"{name}_{click_mode}_error"] = str(exc)

    return False, debug


async def wait_for_chat_mount(page) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass

    for _ in range(10):
        try:
            if await has_chat_root(page):
                await page.wait_for_timeout(900)
                return
        except Exception:
            pass

        try:
            input_locator = await find_message_input(page)
            if input_locator is not None:
                await page.wait_for_timeout(900)
                return
        except Exception:
            pass

        if "chat=1" in (page.url or ""):
            await page.wait_for_timeout(1200)

        await page.wait_for_timeout(1000)


async def has_blocking_chat_gate(page) -> bool:
    for selector in BLOCKING_HINT_SELECTORS:
        try:
            locator = page.locator(selector).first
            if await locator.count() == 0:
                continue
            if await locator.is_visible():
                return True
        except Exception:
            continue
    return False


async def collect_chat_diagnostics(page) -> dict[str, Any]:
    data: dict[str, Any] = {
        "debug_chat_root_found": False,
        "debug_blocking_chat_gate_found": False,
        "debug_message_input_selector": None,
        "debug_message_input_tag": None,
        "debug_message_input_type": None,
        "debug_message_input_disabled": None,
        "debug_message_input_readonly": None,
        "debug_message_input_aria_disabled": None,
        "debug_textarea_count": 0,
        "debug_textbox_count": 0,
        "debug_contenteditable_count": 0,
        "debug_dialog_count": 0,
    }

    try:
        data["debug_chat_root_found"] = await has_chat_root(page)
    except Exception:
        pass

    try:
        data["debug_blocking_chat_gate_found"] = await has_blocking_chat_gate(page)
    except Exception:
        pass

    try:
        data["debug_textarea_count"] = await page.locator("textarea").count()
    except Exception:
        pass

    try:
        data["debug_textbox_count"] = await page.locator('[role="textbox"]').count()
    except Exception:
        pass

    try:
        data["debug_contenteditable_count"] = await page.locator('[contenteditable="true"]').count()
    except Exception:
        pass

    try:
        data["debug_dialog_count"] = await page.locator('[role="dialog"]').count()
    except Exception:
        pass

    for selector in MESSAGE_INPUT_SELECTORS:
        locator = page.locator(selector).first

        try:
            if await locator.count() == 0:
                continue
        except Exception:
            continue

        try:
            if not await locator.is_visible():
                continue
        except Exception:
            continue

        data["debug_message_input_selector"] = selector

        try:
            data["debug_message_input_tag"] = await locator.evaluate(
                "(el) => el.tagName.toLowerCase()"
            )
        except Exception:
            pass

        try:
            data["debug_message_input_type"] = await locator.get_attribute("type")
        except Exception:
            pass

        try:
            data["debug_message_input_disabled"] = (
                await locator.get_attribute("disabled")
            ) is not None
        except Exception:
            pass

        try:
            data["debug_message_input_readonly"] = (
                await locator.get_attribute("readonly")
            ) is not None
        except Exception:
            pass

        try:
            data["debug_message_input_aria_disabled"] = await locator.get_attribute(
                "aria-disabled"
            )
        except Exception:
            pass

        break

    return data