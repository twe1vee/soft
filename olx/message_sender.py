from __future__ import annotations

import time

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from olx.account_runtime import close_runtime_page, open_account_runtime_page
from olx.browser_session import dismiss_cookie_banner_if_present
from olx.message_sender_chat import (
    click_chat_button,
    collect_chat_diagnostics,
    find_message_input,
    get_chat_button_debug,
    has_blocking_chat_gate,
    wait_for_chat_mount,
)
from olx.message_sender_debug import (
    base_result,
    safe_locator_text,
    save_debug_artifacts,
)
from olx.message_sender_page import (
    handle_olx_soft_error_page,
    has_login_hint,
    is_cloudfront_block_page,
)
from olx.message_sender_submit import (
    click_send_button,
    fill_message_input,
    verify_message_sent,
)


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


async def send_message_to_ad(
    cookies_json: str,
    proxy_text: str,
    ad_url: str,
    message_text: str,
    *,
    headless: bool = True,
    user_id: int | None = None,
    account_id: int | None = None,
    olx_profile_name: str | None = None,
) -> dict:
    result = base_result()
    result["ad_url"] = ad_url
    result["message_length"] = len(message_text or "")
    result["browser_engine"] = "gologin"
    result["gologin_profile_id"] = None
    result["gologin_profile_name"] = None
    result["debugger_address"] = None

    result["message_button_clicked"] = False
    result["message_button_clicked_retry"] = False
    result["chat_button_retry_debug"] = None
    result["chat_button_still_visible_after_click"] = None
    result["chat_button_text_after_click"] = None
    result["chat_button_still_visible_after_retry"] = None
    result["chat_button_text_after_retry"] = None
    result["input_found"] = False
    result["send_button_found"] = False
    result["timings_ms"] = {}
    result["final_message_text"] = message_text

    if not (ad_url or "").strip():
        result["status"] = "invalid_input"
        result["error"] = "Пустой ad_url"
        return result

    if not (message_text or "").strip():
        result["status"] = "invalid_input"
        result["error"] = "Пустой message_text"
        return result

    page = None
    runtime_entry = None
    t_total = time.perf_counter()

    try:
        t_step = time.perf_counter()
        if not account_id or int(account_id) <= 0:
            result["status"] = "invalid_input"
            result["error"] = f"Некорректный account_id для send_message: {account_id}"
            return result

        page, runtime_entry = await open_account_runtime_page(
            user_id=user_id,
            account_id=int(account_id),
            cookies_json=cookies_json,
            proxy_text=proxy_text,
            url=ad_url,
            headless=headless,
            olx_profile_name=olx_profile_name,
            timeout=90000,
            wait_after_ms=1200,
            busy_reason="send_message",
        )
        result["timings_ms"]["open_account_runtime_page"] = _elapsed_ms(t_step)

        result["browser_engine"] = runtime_entry.runtime.get("browser_engine", "gologin")
        result["gologin_profile_id"] = runtime_entry.runtime.get("gologin_profile_id")
        result["gologin_profile_name"] = runtime_entry.runtime.get("gologin_profile_name")
        result["debugger_address"] = runtime_entry.runtime.get("debugger_address")

        try:
            await page.set_viewport_size({"width": 1440, "height": 1100})
            await page.wait_for_timeout(200)
        except Exception:
            pass

        result["final_url"] = page.url
        try:
            result["page_title"] = await page.title()
        except Exception:
            pass

        if await is_cloudfront_block_page(page):
            result["status"] = "cloudfront_blocked"
            result["error"] = "OLX/CloudFront заблокировал запрос и вернул 403 block page"
            result["timings_ms"]["total"] = _elapsed_ms(t_total)
            await save_debug_artifacts(page, result, prefix="cloudfront_blocked")
            return result

        handled_soft_error = await handle_olx_soft_error_page(page)
        result["handled_soft_error_page"] = handled_soft_error

        if handled_soft_error:
            try:
                result["page_title"] = await page.title()
            except Exception:
                pass

            result["final_url"] = page.url

            if await is_cloudfront_block_page(page):
                result["status"] = "cloudfront_blocked"
                result["error"] = "OLX/CloudFront заблокировал запрос и вернул 403 block page"
                result["timings_ms"]["total"] = _elapsed_ms(t_total)
                await save_debug_artifacts(page, result, prefix="cloudfront_blocked")
                return result

        t_step = time.perf_counter()
        await dismiss_cookie_banner_if_present(page)
        await page.wait_for_timeout(300)
        result["timings_ms"]["dismiss_cookie_banner"] = _elapsed_ms(t_step)

        t_step = time.perf_counter()
        result.update(await collect_chat_diagnostics(page))
        result["timings_ms"]["collect_chat_diagnostics_initial"] = _elapsed_ms(t_step)

        t_step = time.perf_counter()
        input_locator = await find_message_input(page)

        if input_locator is None:
            clicked, click_debug = await click_chat_button(page)
            result["message_button_clicked"] = clicked
            result.update(click_debug)

            visible_after_click, text_after_click = await get_chat_button_debug(page)
            result["chat_button_still_visible_after_click"] = visible_after_click
            result["chat_button_text_after_click"] = text_after_click

            if clicked:
                await wait_for_chat_mount(page)

            input_locator = await find_message_input(page)

            if input_locator is None and clicked:
                await page.wait_for_timeout(350)

                clicked_retry, click_debug_retry = await click_chat_button(page)
                result["message_button_clicked_retry"] = clicked_retry
                result["chat_button_retry_debug"] = click_debug_retry

                visible_after_retry, text_after_retry = await get_chat_button_debug(page)
                result["chat_button_still_visible_after_retry"] = visible_after_retry
                result["chat_button_text_after_retry"] = text_after_retry

                if clicked_retry:
                    await wait_for_chat_mount(page)

                input_locator = await find_message_input(page)

            result.update(await collect_chat_diagnostics(page))
            result["debug_login_hint_found"] = await has_login_hint(page)
            result["debug_blocking_chat_gate_found"] = await has_blocking_chat_gate(page)

            if input_locator is None:
                result["timings_ms"]["find_or_open_chat"] = _elapsed_ms(t_step)

                if result.get("debug_login_hint_found") or result.get("debug_blocking_chat_gate_found"):
                    result["status"] = "login_required_or_chat_blocked"
                    result["error"] = (
                        "После клика по chat-button открылся логин/блокирующий интерфейс вместо поля ввода"
                    )
                    result["timings_ms"]["total"] = _elapsed_ms(t_total)
                    await save_debug_artifacts(
                        page,
                        result,
                        prefix="login_required_or_chat_blocked",
                    )
                    return result

                result["status"] = "message_input_not_found"
                result["error"] = "Не найдено поле ввода сообщения после клика по chat-button"
                result["timings_ms"]["total"] = _elapsed_ms(t_total)
                await save_debug_artifacts(page, result, prefix="message_input_not_found")
                return result

        result["timings_ms"]["find_or_open_chat"] = _elapsed_ms(t_step)
        result["input_found"] = True

        t_step = time.perf_counter()
        result.update(await collect_chat_diagnostics(page))
        result["timings_ms"]["collect_chat_diagnostics_before_fill"] = _elapsed_ms(t_step)

        t_step = time.perf_counter()
        await fill_message_input(input_locator, message_text)
        result["timings_ms"]["fill_message_input"] = _elapsed_ms(t_step)

        await page.wait_for_timeout(250)

        try:
            submit_btn = page.locator('button[aria-label="Submit message"]').first
            result["submit_button_visible_before_click"] = (
                await submit_btn.count() > 0 and await submit_btn.is_visible()
            )
            result["submit_button_text_before_click"] = await safe_locator_text(submit_btn)
        except Exception:
            result["submit_button_visible_before_click"] = None
            result["submit_button_text_before_click"] = None

        t_step = time.perf_counter()
        send_clicked = await click_send_button(page, input_locator)
        result["timings_ms"]["click_send_button"] = _elapsed_ms(t_step)
        result["send_button_found"] = send_clicked

        try:
            submit_btn = page.locator('button[aria-label="Submit message"]').first
            result["submit_button_visible_after_click"] = (
                await submit_btn.count() > 0 and await submit_btn.is_visible()
            )
            result["submit_button_text_after_click"] = await safe_locator_text(submit_btn)
        except Exception:
            result["submit_button_visible_after_click"] = None
            result["submit_button_text_after_click"] = None

        if not send_clicked:
            t_step = time.perf_counter()
            result.update(await collect_chat_diagnostics(page))
            result["timings_ms"]["collect_chat_diagnostics_send_button_not_found"] = _elapsed_ms(t_step)

            result["status"] = "send_button_not_found"
            result["error"] = "Не найдена кнопка отправки сообщения"
            result["timings_ms"]["total"] = _elapsed_ms(t_total)
            await save_debug_artifacts(page, result, prefix="send_button_not_found")
            return result

        await page.wait_for_timeout(600)

        t_step = time.perf_counter()
        verification = await verify_message_sent(page, input_locator, message_text)
        result["timings_ms"]["verify_message_sent"] = _elapsed_ms(t_step)

        result.update(verification)
        result["final_url"] = page.url

        t_step = time.perf_counter()
        result.update(await collect_chat_diagnostics(page))
        result["timings_ms"]["collect_chat_diagnostics_after_verify"] = _elapsed_ms(t_step)

        if verification.get("delivery_verified"):
            result["ok"] = True
            result["status"] = "sent"
            result["sent"] = True
            result["timings_ms"]["total"] = _elapsed_ms(t_total)
            await save_debug_artifacts(page, result, prefix="sent_success")
            return result

        result["status"] = "send_clicked_unverified"
        result["error"] = (
            "Кнопка отправки была нажата, но подтверждение реальной отправки не получено"
        )
        result["timings_ms"]["total"] = _elapsed_ms(t_total)
        await save_debug_artifacts(page, result, prefix="send_clicked_unverified")
        return result

    except PlaywrightTimeoutError as exc:
        result["status"] = "timeout"
        result["error"] = str(exc)
        result["timings_ms"]["total"] = _elapsed_ms(t_total)
        return result

    except Exception as exc:
        result["error"] = str(exc)
        result["status"] = "browser_failed"
        result["timings_ms"]["total"] = _elapsed_ms(t_total)

        try:
            if page is not None:
                await save_debug_artifacts(page, result, prefix=result["status"])
        except Exception:
            pass

        return result

    finally:
        if runtime_entry is not None:
            await close_runtime_page(runtime_entry, page)