from __future__ import annotations

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from olx.browser_session import (
    dismiss_cookie_banner_if_present,
    open_olx_browser_context,
    open_olx_page,
)
from olx.proxy_bridge import build_bridge_proxy_settings

from olx.message_sender_chat import (
    click_chat_button,
    find_message_input,
    get_chat_button_debug,
    has_chat_root,
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


async def send_message_to_ad(
    cookies_json: str,
    proxy_text: str,
    ad_url: str,
    message_text: str,
    *,
    headless: bool = True,
) -> dict:
    result = base_result()
    result["ad_url"] = ad_url
    result["message_length"] = len(message_text or "")

    if not (ad_url or "").strip():
        result["status"] = "invalid_input"
        result["error"] = "Пустой ad_url"
        return result

    if not (message_text or "").strip():
        result["status"] = "invalid_input"
        result["error"] = "Пустой message_text"
        return result

    try:
        bridge_proxy = build_bridge_proxy_settings(proxy_text)
        result["bridge_server"] = bridge_proxy["server"]
    except Exception as exc:
        result["status"] = "invalid_input"
        result["error"] = str(exc)
        return result

    try:
        async with open_olx_browser_context(
            cookies_json=cookies_json,
            proxy_text=proxy_text,
            headless=headless,
        ) as (_, context):
            page = await open_olx_page(
                context,
                ad_url,
                timeout=90000,
                wait_after_ms=5000,
            )

            result["final_url"] = page.url

            try:
                result["page_title"] = await page.title()
            except Exception:
                pass

            if await is_cloudfront_block_page(page):
                result["status"] = "cloudfront_blocked"
                result["error"] = "OLX/CloudFront заблокировал запрос и вернул 403 block page"
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
                    await save_debug_artifacts(page, result, prefix="cloudfront_blocked")
                    return result

            await dismiss_cookie_banner_if_present(page)
            await page.wait_for_timeout(1500)

            input_locator = await find_message_input(page)

            if input_locator is None:
                clicked = await click_chat_button(page)
                result["message_button_clicked"] = clicked

                visible_after_click, text_after_click = await get_chat_button_debug(page)
                result["chat_button_still_visible_after_click"] = visible_after_click
                result["chat_button_text_after_click"] = text_after_click

                if clicked:
                    await wait_for_chat_mount(page)

                result["debug_chat_root_found"] = await has_chat_root(page)
                result["debug_login_hint_found"] = await has_login_hint(page)

                input_locator = await find_message_input(page)

                if input_locator is None:
                    if result["debug_login_hint_found"]:
                        result["status"] = "login_required_or_chat_blocked"
                        result["error"] = (
                            "После клика по chat-button открылся логин/блокирующий интерфейс вместо поля ввода"
                        )
                        await save_debug_artifacts(
                            page,
                            result,
                            prefix="login_required_or_chat_blocked",
                        )
                        return result

                    result["status"] = "message_input_not_found"
                    result["error"] = "Не найдено поле ввода сообщения после клика по chat-button"
                    await save_debug_artifacts(
                        page,
                        result,
                        prefix="message_input_not_found",
                    )
                    return result

            result["input_found"] = True

            await fill_message_input(input_locator, message_text)
            await page.wait_for_timeout(1000)

            try:
                submit_btn = page.locator('button[aria-label="Submit message"]').first
                result["submit_button_visible_before_click"] = (
                    await submit_btn.count() > 0 and await submit_btn.is_visible()
                )
                result["submit_button_text_before_click"] = await safe_locator_text(submit_btn)
            except Exception:
                result["submit_button_visible_before_click"] = None
                result["submit_button_text_before_click"] = None

            send_clicked = await click_send_button(page, input_locator)
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
                result["status"] = "send_button_not_found"
                result["error"] = "Не найдена кнопка отправки сообщения"
                await save_debug_artifacts(page, result, prefix="send_button_not_found")
                return result

            await page.wait_for_timeout(2000)

            verification = await verify_message_sent(page, input_locator, message_text)
            result.update(verification)
            result["final_url"] = page.url

            if verification.get("delivery_verified"):
                result["ok"] = True
                result["status"] = "sent"
                result["sent"] = True

                await save_debug_artifacts(page, result, prefix="sent_success")
                return result

            result["status"] = "send_clicked_unverified"
            result["error"] = (
                "Кнопка отправки была нажата, но подтверждение реальной отправки не получено"
            )
            await save_debug_artifacts(page, result, prefix="send_clicked_unverified")
            return result

    except PlaywrightTimeoutError as exc:
        result["status"] = "timeout"
        result["error"] = str(exc)
        return result

    except Exception as exc:
        message = str(exc).lower()
        result["error"] = str(exc)

        proxy_error_markers = [
            "proxy",
            "tunnel",
            "timeout",
            "net::err_proxy",
            "browser has been closed",
            "socks",
            "connection refused",
            "connection reset",
            "net::err",
        ]

        if any(marker in message for marker in proxy_error_markers):
            result["status"] = "proxy_failed"
        else:
            result["status"] = "browser_failed"

        try:
            if "page" in locals() and page is not None:
                await save_debug_artifacts(page, result, prefix=result["status"])
        except Exception:
            pass

        return result