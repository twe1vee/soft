from __future__ import annotations

from typing import Any

from db import (
    create_conversation_message,
    get_account_by_id,
    get_conversation_by_id,
    get_proxy_by_id,
    update_conversation_last_preview,
)
from olx.account_runtime import close_runtime_page, open_account_runtime_page
from olx.dialogs_page import dismiss_dialogs_overlays_if_present
from olx.message_sender_chat import (
    collect_chat_diagnostics,
    find_message_input,
    has_blocking_chat_gate,
    wait_for_chat_mount,
)
from olx.message_sender_debug import base_result, safe_locator_text
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


def _build_outgoing_message_key(
    conversation_id: int,
    text: str,
) -> str:
    import hashlib

    stable = f"{conversation_id}|outgoing|{(text or '').strip()}"
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


async def send_reply_to_conversation(
    *,
    user_id: int,
    conversation_id: int,
    account_id: int,
    message_text: str,
    headless: bool = True,
) -> dict[str, Any]:
    result = base_result()
    result["conversation_id"] = conversation_id
    result["account_id"] = account_id
    result["message_length"] = len(message_text or "")
    result["browser_engine"] = "gologin"
    result["gologin_profile_id"] = None
    result["gologin_profile_name"] = None
    result["debugger_address"] = None
    result["input_found"] = False
    result["send_button_found"] = False

    if not (message_text or "").strip():
        result["status"] = "invalid_input"
        result["error"] = "Пустой message_text"
        return result

    conversation = get_conversation_by_id(user_id, conversation_id)
    if not conversation:
        result["status"] = "conversation_not_found"
        result["error"] = "Диалог не найден"
        return result

    account = get_account_by_id(user_id, account_id)
    if not account:
        result["status"] = "account_not_found"
        result["error"] = "Аккаунт не найден"
        return result

    cookies_json = account.get("cookies_json")
    if not cookies_json:
        result["status"] = "missing_cookies"
        result["error"] = "У аккаунта отсутствуют cookies_json"
        return result

    proxy_id = account.get("proxy_id")
    if not proxy_id:
        result["status"] = "missing_proxy"
        result["error"] = "У аккаунта отсутствует proxy"
        return result

    proxy = get_proxy_by_id(user_id, proxy_id)
    if not proxy or not proxy.get("proxy_text"):
        result["status"] = "proxy_not_found"
        result["error"] = "Proxy не найден"
        return result

    target_url = (
        conversation.get("conversation_url")
        or conversation.get("ad_url")
        or "https://www.olx.pt/myaccount/answers/"
    )
    result["target_url"] = target_url

    page = None
    runtime_entry = None

    try:
        page, runtime_entry = await open_account_runtime_page(
            user_id=user_id,
            account_id=account_id,
            cookies_json=cookies_json,
            proxy_text=proxy["proxy_text"],
            url=target_url,
            headless=headless,
            olx_profile_name=account.get("olx_profile_name"),
            timeout=90000,
            wait_after_ms=4000,
            busy_reason="reply_dialog",
        )

        result["browser_engine"] = runtime_entry.runtime.get("browser_engine", "gologin")
        result["gologin_profile_id"] = runtime_entry.runtime.get("gologin_profile_id")
        result["gologin_profile_name"] = runtime_entry.runtime.get("gologin_profile_name")
        result["debugger_address"] = runtime_entry.runtime.get("debugger_address")

        try:
            await page.set_viewport_size({"width": 1440, "height": 1100})
            await page.wait_for_timeout(800)
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
            return result

        handled_soft_error = await handle_olx_soft_error_page(page)
        result["handled_soft_error_page"] = handled_soft_error

        await dismiss_dialogs_overlays_if_present(page)
        await page.wait_for_timeout(1200)

        if handled_soft_error:
            result["final_url"] = page.url

        if await is_cloudfront_block_page(page):
            result["status"] = "cloudfront_blocked"
            result["error"] = "OLX/CloudFront заблокировал запрос и вернул 403 block page"
            return result

        result.update(await collect_chat_diagnostics(page))

        input_locator = await find_message_input(page)
        if input_locator is None:
            await wait_for_chat_mount(page)
            input_locator = await find_message_input(page)

        result["debug_login_hint_found"] = await has_login_hint(page)
        result["debug_blocking_chat_gate_found"] = await has_blocking_chat_gate(page)

        if input_locator is None:
            if result.get("debug_login_hint_found") or result.get("debug_blocking_chat_gate_found"):
                result["status"] = "login_required_or_chat_blocked"
                result["error"] = "Вместо поля ввода открылся логин/блокирующий интерфейс"
                return result

            result["status"] = "message_input_not_found"
            result["error"] = "Не найдено поле ввода сообщения в диалоге"
            return result

        result["input_found"] = True

        await fill_message_input(input_locator, message_text)
        await page.wait_for_timeout(700)

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
            return result

        await page.wait_for_timeout(1800)

        verification = await verify_message_sent(page, input_locator, message_text)
        result.update(verification)
        result["final_url"] = page.url
        result.update(await collect_chat_diagnostics(page))

        if verification.get("delivery_verified"):
            outgoing_key = _build_outgoing_message_key(conversation_id, message_text)
            create_conversation_message(
                conversation_id=conversation_id,
                account_id=account_id,
                external_message_key=outgoing_key,
                direction="outgoing",
                sender_name=account.get("olx_profile_name"),
                text=message_text,
                is_unread=False,
                sent_at_hint=None,
                status="sent",
                notified_at=None,
            )
            update_conversation_last_preview(
                user_id,
                conversation_id,
                last_message_preview=message_text,
                last_message_at_hint=None,
                last_incoming_message_key=conversation.get("last_incoming_message_key"),
            )

            result["ok"] = True
            result["status"] = "sent"
            result["sent"] = True
            return result

        result["status"] = "send_clicked_unverified"
        result["error"] = "Кнопка отправки нажата, но подтверждение отправки не получено"
        return result

    except Exception as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        return result

    finally:
        if runtime_entry is not None:
            await close_runtime_page(runtime_entry, page)