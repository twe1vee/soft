from __future__ import annotations

from typing import Any

from db import (
    create_conversation_message,
    create_or_update_conversation,
    get_conversation_by_key,
)
from olx.account_runtime import close_runtime_page, open_account_runtime_page
from olx.dialogs_page import open_dialogs_page
from olx.dialogs_parser import (
    build_incoming_message_key,
    parse_dialogs_page,
)
from olx.message_sender_page import has_login_hint, is_cloudfront_block_page


def _normalize_text(value: str | None) -> str:
    return (value or "").strip()


def _is_incoming_candidate(item: dict[str, Any]) -> bool:
    if not _normalize_text(item.get("last_message_text")):
        return False

    direction_guess = item.get("last_message_direction_guess") or "unknown"
    is_unread = bool(item.get("is_unread"))

    if direction_guess == "incoming":
        return True

    if direction_guess == "outgoing":
        return False

    return is_unread


async def check_account_dialogs(
    *,
    user_id: int,
    account_id: int,
    cookies_json: str,
    proxy_text: str,
    headless: bool = True,
    olx_profile_name: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "status": "unknown",
        "user_id": user_id,
        "account_id": account_id,
        "browser_engine": "gologin",
        "gologin_profile_id": None,
        "gologin_profile_name": None,
        "debugger_address": None,
        "final_url": None,
        "page_title": None,
        "cloudfront_blocked": False,
        "login_hint_found": False,
        "handled_soft_error_page": False,
        "dialog_rows_found": 0,
        "parsed_dialogs_count": 0,
        "new_incoming_count": 0,
        "conversations_upserted": 0,
        "new_incoming_events": [],
        "parsed_dialogs": [],
        "error": None,
    }

    page = None
    runtime_entry = None

    try:
        page, runtime_entry = await open_account_runtime_page(
            user_id=user_id,
            account_id=account_id,
            cookies_json=cookies_json,
            proxy_text=proxy_text,
            url=None,
            headless=headless,
            olx_profile_name=olx_profile_name,
            timeout=90000,
            wait_after_ms=0,
            busy_reason="dialogs_check",
        )

        result["browser_engine"] = runtime_entry.runtime.get("browser_engine", "gologin")
        result["gologin_profile_id"] = runtime_entry.runtime.get("gologin_profile_id")
        result["gologin_profile_name"] = runtime_entry.runtime.get("gologin_profile_name")
        result["debugger_address"] = runtime_entry.runtime.get("debugger_address")

        try:
            await page.set_viewport_size({"width": 1440, "height": 1100})
            await page.wait_for_timeout(600)
        except Exception:
            pass

        page_info = await open_dialogs_page(
            page,
            timeout=90000,
            wait_after_ms=4000,
        )
        result.update(page_info)
        result["final_url"] = page.url

        if await is_cloudfront_block_page(page):
            result["status"] = "cloudfront_blocked"
            result["cloudfront_blocked"] = True
            result["error"] = "OLX/CloudFront вернул block page при открытии диалогов"
            return result

        if await has_login_hint(page):
            result["status"] = "not_logged_in"
            result["login_hint_found"] = True
            result["error"] = "OLX показывает логин вместо списка диалогов"
            return result

        parsed_dialogs = await parse_dialogs_page(page)
        result["parsed_dialogs_count"] = len(parsed_dialogs)
        result["parsed_dialogs"] = parsed_dialogs

        conversations_upserted = 0
        new_incoming_events: list[dict[str, Any]] = []

        for item in parsed_dialogs:
            conversation_key = item["conversation_key"]

            existing_conversation = get_conversation_by_key(
                user_id=user_id,
                account_id=account_id,
                conversation_key=conversation_key,
            )

            incoming_message_key = None
            if _is_incoming_candidate(item):
                incoming_message_key = build_incoming_message_key(
                    conversation_key=conversation_key,
                    seller_name=item.get("seller_name"),
                    last_message_text=item.get("last_message_text"),
                    updated_hint=item.get("updated_hint"),
                )

            conversation_id = create_or_update_conversation(
                user_id=user_id,
                account_id=account_id,
                conversation_key=conversation_key,
                conversation_url=item.get("conversation_url"),
                seller_name=item.get("seller_name"),
                ad_title=item.get("ad_title"),
                ad_url=item.get("ad_url"),
                ad_external_id=item.get("ad_external_id"),
                last_message_preview=item.get("last_message_text"),
                last_message_at_hint=item.get("updated_hint"),
                is_unread=bool(item.get("is_unread")),
                last_incoming_message_key=incoming_message_key,
                status="active",
            )
            conversations_upserted += 1

            if not incoming_message_key:
                continue

            message_id = create_conversation_message(
                conversation_id=conversation_id,
                account_id=account_id,
                external_message_key=incoming_message_key,
                direction="incoming",
                sender_name=item.get("seller_name"),
                text=item.get("last_message_text") or "",
                is_unread=bool(item.get("is_unread")),
                sent_at_hint=item.get("updated_hint"),
                status="new_incoming",
            )

            if message_id is None:
                continue

            new_incoming_events.append(
                {
                    "conversation_id": conversation_id,
                    "conversation_key": conversation_key,
                    "message_id": message_id,
                    "account_id": account_id,
                    "seller_name": item.get("seller_name"),
                    "ad_title": item.get("ad_title"),
                    "ad_url": item.get("ad_url"),
                    "ad_external_id": item.get("ad_external_id"),
                    "conversation_url": item.get("conversation_url"),
                    "text": item.get("last_message_text"),
                    "is_unread": bool(item.get("is_unread")),
                    "updated_hint": item.get("updated_hint"),
                    "is_new_conversation": existing_conversation is None,
                }
            )

        result["conversations_upserted"] = conversations_upserted
        result["new_incoming_events"] = new_incoming_events
        result["new_incoming_count"] = len(new_incoming_events)
        result["ok"] = True
        result["status"] = "ok"
        return result

    except Exception as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        return result

    finally:
        if runtime_entry is not None:
            await close_runtime_page(runtime_entry, page)


async def check_user_dialogs(
    *,
    user_id: int,
    accounts: list[dict],
    proxies_by_id: dict[int, dict],
    headless: bool = True,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "ok": True,
        "status": "ok",
        "user_id": user_id,
        "accounts_checked": 0,
        "accounts_skipped": 0,
        "total_new_incoming_count": 0,
        "account_results": [],
        "new_incoming_events": [],
    }

    for account in accounts:
        cookies_json = account.get("cookies_json")
        proxy_id = account.get("proxy_id")
        proxy = proxies_by_id.get(proxy_id) if proxy_id else None
        proxy_text = proxy.get("proxy_text") if proxy else None

        if not cookies_json or not proxy_text:
            summary["accounts_skipped"] += 1
            summary["account_results"].append(
                {
                    "ok": False,
                    "status": "skipped_missing_credentials",
                    "account_id": account["id"],
                }
            )
            continue

        account_result = await check_account_dialogs(
            user_id=user_id,
            account_id=account["id"],
            cookies_json=cookies_json,
            proxy_text=proxy_text,
            headless=headless,
            olx_profile_name=account.get("olx_profile_name"),
        )

        summary["accounts_checked"] += 1
        summary["account_results"].append(account_result)
        summary["total_new_incoming_count"] += account_result.get("new_incoming_count", 0)
        summary["new_incoming_events"].extend(account_result.get("new_incoming_events", []))

    return summary