from __future__ import annotations

from typing import Any

from olx.message_sender_debug import first_non_empty_text

MESSAGE_INPUT_SELECTORS = [
    '[data-testid="chat-form-container"] textarea[name="message.text"]',
    '[data-testid="chat-form-container"] textarea[placeholder="Escreve uma mensagem..."]',
    'textarea[name="message.text"]',
    'textarea[placeholder="Escreve uma mensagem..."]',
    '[data-testid="chat-form-container"] textarea',
    "textarea",
]

CHAT_ROOT_SELECTORS = [
    '[data-cy="conversation-top-bar"]',
    '[data-testid="messages-list-container"]',
    '[data-testid="chat-form-container"]',
]

BLOCKING_HINT_SELECTORS = [
    'form[action*="login"]',
    'input[name="login[email]"]',
    'input[type="password"]',
    '[data-testid*="login"]',
    '[data-testid*="auth"]',
    'button:has-text("Iniciar sessão")',
    'button:has-text("Entrar")',
    'a:has-text("Iniciar sessão")',
    'a:has-text("Entrar")',
    'text=Iniciar sessão',
    'text=Entrar',
    'text=Faça login',
    'text=Fazer login',
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
            "ad_contact_message_button_data_cy",
            page.locator('button[data-cy="ad-contact-message-button"]').first,
        ),
        (
            "ad_contact_message_button_data_testid",
            page.locator('button[data-testid="ad-contact-message-button"]').first,
        ),
        (
            "ad_contact_message_button_aria",
            page.locator('button[aria-label="Enviar mensagem"]').first,
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
        "data_cy": None,
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
        info["data_cy"] = await el.get_attribute("data-cy")
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
                        dataCy: el.getAttribute("data-cy"),
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
            await locator.wait_for(state="attached", timeout=2000)
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
            visible = await locator.first.is_visible()
        except Exception:
            continue

        text = None
        try:
            text = first_non_empty_text(await locator.first.inner_text())
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
            await locator.wait_for(state="visible", timeout=4000)
        except Exception:
            continue

        debug["clicked_candidate"] = name
        debug["clicked_candidate_debug"] = await collect_element_debug(page, locator, f"clicked::{name}")

        try:
            await locator.scroll_into_view_if_needed()
            await page.wait_for_timeout(250)
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
                    await page.wait_for_timeout(120)
                    await page.mouse.click(x, y)
                elif click_mode == "normal":
                    await locator.click(timeout=4000)
                else:
                    await locator.click(force=True, timeout=4000)

                await page.wait_for_timeout(900)

                if await has_chat_root(page):
                    debug["click_mode"] = click_mode
                    return True, debug

                input_locator = await find_message_input(page)
                if input_locator is not None:
                    debug["click_mode"] = click_mode
                    return True, debug

            except Exception as exc:
                debug[f"{name}_{click_mode}_error"] = str(exc)

    return False, debug


async def wait_for_chat_mount(page) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=6000)
    except Exception:
        pass

    for _ in range(8):
        try:
            if await has_chat_root(page):
                await page.wait_for_timeout(700)
                return
        except Exception:
            pass

        try:
            input_locator = await find_message_input(page)
            if input_locator is not None:
                await page.wait_for_timeout(700)
                return
        except Exception:
            pass

        await page.wait_for_timeout(800)


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
        "debug_message_input_found": False,
        "debug_message_input_tag": None,
        "debug_message_input_placeholder": None,
        "debug_message_input_name": None,
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
        locator = await find_message_input(page)
        if locator is not None:
            data["debug_message_input_found"] = True
            try:
                data["debug_message_input_tag"] = await locator.evaluate(
                    "(el) => el.tagName.toLowerCase()"
                )
            except Exception:
                pass
            try:
                data["debug_message_input_placeholder"] = await locator.get_attribute("placeholder")
            except Exception:
                pass
            try:
                data["debug_message_input_name"] = await locator.get_attribute("name")
            except Exception:
                pass
    except Exception:
        pass

    return data