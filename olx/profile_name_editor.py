import random
from typing import Any

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from olx.account_runtime import close_runtime_page, open_account_runtime_page

USER_SETTINGS_URL = "https://www.olx.pt/myaccount/user-settings/"

EDIT_PROFILE_TOGGLE_SELECTORS = [
    '[data-testid="settings.set_contact__toggle"]',
    'text="Editar perfil"',
]

NAME_INPUT_SELECTORS = [
    'input[name="userName"]',
    'input[aria-label="O teu nome no OLX"]',
]

SAVE_BUTTON_SELECTORS = [
    'button[type="submit"]',
    'button[data-nx-name="NexusButton"]',
]

SUCCESS_TEXT = "Guardámos as tuas alterações"


def normalize_profile_name(raw_name: str) -> str:
    value = " ".join((raw_name or "").replace("\n", " ").split()).strip()
    return value


async def _wait_for_visible(page, selectors: list[str], timeout: int = 15000):
    last_error = None
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            await locator.wait_for(state="visible", timeout=timeout)
            return locator
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise RuntimeError("No selectors provided")


async def _find_first(page, selectors: list[str]):
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.count() > 0:
                return locator
        except Exception:
            continue
    return None


async def _open_user_settings_page(page) -> None:
    await page.goto(USER_SETTINGS_URL, wait_until="domcontentloaded", timeout=90000)
    await page.wait_for_timeout(1500)

    try:
        await page.wait_for_url("**/myaccount/user-settings/**", timeout=15000)
    except Exception:
        pass

    try:
        await _wait_for_visible(page, EDIT_PROFILE_TOGGLE_SELECTORS, timeout=15000)
    except Exception:
        await _wait_for_visible(page, NAME_INPUT_SELECTORS, timeout=15000)


async def _expand_edit_profile_section_if_needed(page) -> None:
    input_locator = await _find_first(page, NAME_INPUT_SELECTORS)
    if input_locator is not None:
        try:
            if await input_locator.is_visible():
                return
        except Exception:
            pass

    toggle = await _wait_for_visible(page, EDIT_PROFILE_TOGGLE_SELECTORS, timeout=10000)
    await toggle.click()
    await page.wait_for_timeout(800)

    await _wait_for_visible(page, NAME_INPUT_SELECTORS, timeout=10000)


async def _get_name_input(page):
    return await _wait_for_visible(page, NAME_INPUT_SELECTORS, timeout=10000)


async def _get_save_button(page):
    button = await _wait_for_visible(page, SAVE_BUTTON_SELECTORS, timeout=10000)
    try:
        text = ((await button.inner_text()) or "").strip()
        if text and "Guardar" not in text:
            alt = page.get_by_role("button", name="Guardar").first
            await alt.wait_for(state="visible", timeout=3000)
            return alt
    except Exception:
        pass
    return button


async def _read_current_name(page) -> str:
    name_input = await _get_name_input(page)
    value = await name_input.input_value()
    return normalize_profile_name(value)


async def _apply_random_human_delay(page) -> float:
    delay_seconds = round(random.uniform(2.0, 4.0), 2)
    await page.wait_for_timeout(int(delay_seconds * 1000))
    return delay_seconds


async def _fill_new_name(page, new_name: str) -> None:
    name_input = await _get_name_input(page)

    await name_input.click()
    try:
        await name_input.press("Control+A")
    except Exception:
        pass

    await name_input.fill(new_name)
    await page.wait_for_timeout(250)

    try:
        await name_input.press("Tab")
    except Exception:
        try:
            await name_input.blur()
        except Exception:
            pass

    await page.wait_for_timeout(500)


async def _wait_save_enabled(button, timeout_ms: int = 10000) -> bool:
    waited = 0
    step = 250

    while waited < timeout_ms:
        try:
            disabled_attr = await button.get_attribute("disabled")
            aria_disabled = await button.get_attribute("aria-disabled")
            is_disabled = False

            if disabled_attr is not None:
                is_disabled = True
            elif aria_disabled and aria_disabled.lower() == "true":
                is_disabled = True

            if not is_disabled:
                return True
        except Exception:
            pass

        await button.page.wait_for_timeout(step)
        waited += step

    return False


async def _wait_success_dialog(page, timeout_ms: int = 12000) -> bool:
    success_locator = page.locator('[data-testid="dialog"]').filter(has_text=SUCCESS_TEXT).first
    success_text_locator = page.locator('[data-nx-name="P4"]').filter(has_text=SUCCESS_TEXT).first

    try:
        await success_locator.wait_for(state="visible", timeout=timeout_ms)
        return True
    except Exception:
        pass

    try:
        await success_text_locator.wait_for(state="visible", timeout=timeout_ms)
        return True
    except Exception:
        return False


async def update_olx_profile_name(
    *,
    user_id: int,
    account_id: int,
    cookies_json: str,
    proxy_text: str,
    olx_profile_name: str | None,
    requested_name: str,
    headless: bool = True,
) -> dict[str, Any]:
    normalized_name = normalize_profile_name(requested_name)

    if len(normalized_name) < 2:
        return {
            "ok": False,
            "status": "invalid_name",
            "requested_name": normalized_name,
            "previous_name": None,
            "saved_name": None,
            "delay_seconds": 0,
            "final_url": USER_SETTINGS_URL,
            "error": "Имя слишком короткое.",
        }

    if len(normalized_name) > 40:
        return {
            "ok": False,
            "status": "invalid_name",
            "requested_name": normalized_name,
            "previous_name": None,
            "saved_name": None,
            "delay_seconds": 0,
            "final_url": USER_SETTINGS_URL,
            "error": "Имя слишком длинное.",
        }

    page = None
    entry = None

    result: dict[str, Any] = {
        "ok": False,
        "status": "failed",
        "requested_name": normalized_name,
        "previous_name": None,
        "saved_name": None,
        "delay_seconds": 0,
        "final_url": USER_SETTINGS_URL,
        "error": None,
    }

    try:
        page, entry = await open_account_runtime_page(
            user_id=user_id,
            account_id=account_id,
            cookies_json=cookies_json,
            proxy_text=proxy_text,
            url=USER_SETTINGS_URL,
            headless=headless,
            olx_profile_name=olx_profile_name,
            timeout=90000,
            wait_after_ms=2500,
            busy_reason="rename_profile_name",
        )

        await _open_user_settings_page(page)
        await _expand_edit_profile_section_if_needed(page)

        previous_name = await _read_current_name(page)
        result["previous_name"] = previous_name
        result["final_url"] = page.url

        if normalize_profile_name(previous_name).lower() == normalized_name.lower():
            result["ok"] = True
            result["status"] = "unchanged"
            result["saved_name"] = previous_name
            return result

        delay_seconds = await _apply_random_human_delay(page)
        result["delay_seconds"] = delay_seconds

        await _fill_new_name(page, normalized_name)

        save_button = await _get_save_button(page)
        save_enabled = await _wait_save_enabled(save_button, timeout_ms=10000)
        if not save_enabled:
            result["status"] = "save_not_enabled"
            result["error"] = "Кнопка Guardar не стала активной после изменения имени."
            return result

        await save_button.click()
        await page.wait_for_timeout(600)

        if not await _wait_success_dialog(page, timeout_ms=12000):
            # fallback: перечитать поле
            reread_name = await _read_current_name(page)
            if normalize_profile_name(reread_name).lower() != normalized_name.lower():
                result["status"] = "save_failed"
                result["error"] = "OLX не подтвердил сохранение имени."
                result["saved_name"] = reread_name
                return result

        saved_name = await _read_current_name(page)

        result["ok"] = True
        result["status"] = "updated"
        result["saved_name"] = saved_name
        result["final_url"] = page.url
        return result

    except PlaywrightTimeoutError as exc:
        result["status"] = "timeout"
        result["error"] = f"Timeout при смене имени: {exc}"
        return result
    except PlaywrightError as exc:
        result["status"] = "failed"
        result["error"] = f"Playwright error: {exc}"
        return result
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        return result
    finally:
        if page is not None and entry is not None:
            await close_runtime_page(entry, page)