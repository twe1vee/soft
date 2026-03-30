from __future__ import annotations

import asyncio
from typing import Any

from db import (
    create_conversation_message,
    create_or_update_conversation,
    get_account_by_id,
    get_conversation_by_key,
)
from olx.account_runtime import close_runtime_page, open_account_runtime_page
from olx.dialogs_page import open_dialogs_page
from olx.dialogs_parser import (
    build_incoming_message_key,
    parse_dialogs_page,
)
from olx.message_sender_page import has_login_hint, is_cloudfront_block_page
from olx.profile_manager_gologin import AccountRuntimeBlockedError

DIALOGS_OPEN_TIMEOUT_SECONDS = 45
DIALOGS_PARSE_TIMEOUT_SECONDS = 30


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

    fresh_account = get_account_by_id(user_id, account_id)
    if not fresh_account:
        result["status"] = "skipped_deleted_account"
        result["error"] = f"account_id={account_id} already deleted"
        print(
            f"[dialogs_checker] skipped_deleted_account "
            f"user_id={user_id} account_id={account_id}"
        )
        return result

    page = None
    runtime_entry = None

    try:
        print(
            f"[dialogs_checker] open_runtime_start "
            f"user_id={user_id} account_id={account_id}"
        )
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
        print(
            f"[dialogs_checker] open_runtime_ok "
            f"user_id={user_id} account_id={account_id} "
            f"url={getattr(page, 'url', None)}"
        )
    except AccountRuntimeBlockedError as exc:
        result["status"] = "skipped_runtime_blocked"
        result["error"] = str(exc)
        print(
            f"[dialogs_checker] skipped_runtime_blocked "
            f"user_id={user_id} account_id={account_id} error={exc!r}"
        )
        return result
    except Exception as exc:
        result["status"] = "failed_open_runtime"
        result["error"] = str(exc)
        print(
            f"[dialogs_checker] failed_open_runtime "
            f"user_id={user_id} account_id={account_id} error={exc!r}"
        )
        return result

    try:
        result["browser_engine"] = runtime_entry.runtime.get("browser_engine", "gologin")
        result["gologin_profile_id"] = runtime_entry.runtime.get("gologin_profile_id")
        result["gologin_profile_name"] = runtime_entry.runtime.get("gologin_profile_name")
        result["debugger_address"] = runtime_entry.runtime.get("debugger_address")

        try:
            await page.set_viewport_size({"width": 1440, "height": 1100})
            await page.wait_for_timeout(600)
        except Exception as exc:
            print(
                f"[dialogs_checker] viewport_warning "
                f"user_id={user_id} account_id={account_id} error={exc!r}"
            )

        print(
            f"[dialogs_checker] before_open_dialogs "
            f"user_id={user_id} account_id={account_id} current_url={page.url}"
        )

        try:
            page_info = await asyncio.wait_for(
                open_dialogs_page(
                    page,
                    timeout=45000,
                    wait_after_ms=2500,
                ),
                timeout=DIALOGS_OPEN_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            result["status"] = "dialogs_open_timeout"
            result["final_url"] = getattr(page, "url", None)
            result["error"] = (
                f"open_dialogs_page timeout after {DIALOGS_OPEN_TIMEOUT_SECONDS}s"
            )
            print(
                f"[dialogs_checker] dialogs_open_timeout "
                f"user_id={user_id} account_id={account_id} final_url={result['final_url']}"
            )
            return result

        result.update(page_info or {})
        result["final_url"] = getattr(page, "url", None)

        try:
            result["page_title"] = await page.title()
        except Exception:
            result["page_title"] = None

        print(
            f"[dialogs_checker] after_open_dialogs "
            f"user_id={user_id} account_id={account_id} "
            f"final_url={result['final_url']} page_info={page_info}"
        )

        if await is_cloudfront_block_page(page):
            result["status"] = "cloudfront_blocked"
            result["cloudfront_blocked"] = True
            result["error"] = "OLX/CloudFront вернул block page при открытии диалогов"
            print(
                f"[dialogs_checker] cloudfront_blocked "
                f"user_id={user_id} account_id={account_id} final_url={result['final_url']}"
            )
            return result

        if await has_login_hint(page):
            result["status"] = "not_logged_in"
            result["login_hint_found"] = True
            result["error"] = "OLX показывает логин вместо списка диалогов"
            print(
                f"[dialogs_checker] not_logged_in "
                f"user_id={user_id} account_id={account_id} final_url={result['final_url']}"
            )
            return result

        print(
            f"[dialogs_checker] before_parse_dialogs "
            f"user_id={user_id} account_id={account_id} final_url={result['final_url']}"
        )

        try:
            parsed_dialogs = await asyncio.wait_for(
                parse_dialogs_page(page),
                timeout=DIALOGS_PARSE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            result["status"] = "dialogs_parse_timeout"
            result["error"] = (
                f"parse_dialogs_page timeout after {DIALOGS_PARSE_TIMEOUT_SECONDS}s"
            )
            print(
                f"[dialogs_checker] dialogs_parse_timeout "
                f"user_id={user_id} account_id={account_id} final_url={result['final_url']}"
            )
            return result

        result["parsed_dialogs_count"] = len(parsed_dialogs)
        result["parsed_dialogs"] = parsed_dialogs

        print(
            f"[dialogs_checker] after_parse_dialogs "
            f"user_id={user_id} account_id={account_id} parsed={len(parsed_dialogs)}"
        )

        conversations_upserted = 0
        new_incoming_events: list[dict[str, Any]] = []

        for item in parsed_dialogs:
            conversation_key = item["conversation_key"]
            existing_conversation = get_conversation_by_key(
                user_id=user_id,
                account_id=account_id,
                conversation_key=conversation_key,
            )

            is_incoming_candidate = _is_incoming_candidate(item)

            print(
                f"[dialogs_checker] dialog_candidate "
                f"user_id={user_id} account_id={account_id} "
                f"conversation_key={conversation_key!r} "
                f"seller={item.get('seller_name')!r} "
                f"ad_title={item.get('ad_title')!r} "
                f"text={item.get('last_message_text')!r} "
                f"updated_hint={item.get('updated_hint')!r} "
                f"direction={item.get('last_message_direction_guess')!r} "
                f"is_unread={bool(item.get('is_unread'))!r} "
                f"incoming_candidate={is_incoming_candidate!r}"
            )

            incoming_message_key = None
            if is_incoming_candidate:
                incoming_message_key = build_incoming_message_key(
                    conversation_key=conversation_key,
                    seller_name=item.get("seller_name"),
                    last_message_text=item.get("last_message_text"),
                    updated_hint=item.get("updated_hint"),
                )
                print(
                    f"[dialogs_checker] incoming_key_built "
                    f"user_id={user_id} account_id={account_id} "
                    f"conversation_key={conversation_key!r} "
                    f"incoming_message_key={incoming_message_key!r}"
                )
            else:
                print(
                    f"[dialogs_checker] incoming_skipped "
                    f"user_id={user_id} account_id={account_id} "
                    f"conversation_key={conversation_key!r}"
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
                print(
                    f"[dialogs_checker] message_duplicate "
                    f"user_id={user_id} account_id={account_id} "
                    f"conversation_key={conversation_key!r}"
                )
                continue

            print(
                f"[dialogs_checker] new_incoming_created "
                f"user_id={user_id} account_id={account_id} "
                f"conversation_key={conversation_key!r} "
                f"message_id={message_id!r}"
            )

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

        print(
            f"[dialogs_checker] done "
            f"user_id={user_id} account_id={account_id} "
            f"parsed={result['parsed_dialogs_count']} "
            f"upserted={result['conversations_upserted']} "
            f"new_incoming={result['new_incoming_count']}"
        )
        return result

    except Exception as exc:
        result["status"] = "failed"
        result["final_url"] = getattr(page, "url", None) if page is not None else None
        result["error"] = str(exc)
        print(
            f"[dialogs_checker] failed "
            f"user_id={user_id} account_id={account_id} "
            f"final_url={result['final_url']} error={exc!r}"
        )
        return result
    finally:
        if runtime_entry is not None:
            print(
                f"[dialogs_checker] close_runtime "
                f"user_id={user_id} account_id={account_id}"
            )
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
        account_id = account["id"]

        fresh_account = get_account_by_id(user_id, account_id)
        if not fresh_account:
            summary["accounts_skipped"] += 1
            skipped = {
                "ok": False,
                "status": "skipped_deleted_account",
                "account_id": account_id,
            }
            summary["account_results"].append(skipped)
            print(
                f"[dialogs_checker] account_summary "
                f"user_id={user_id} account_id={account_id} "
                f"status={skipped['status']}"
            )
            continue

        cookies_json = fresh_account.get("cookies_json")
        proxy_id = fresh_account.get("proxy_id")
        proxy = proxies_by_id.get(proxy_id) if proxy_id else None
        proxy_text = proxy.get("proxy_text") if proxy else None

        if not cookies_json or not proxy_text:
            summary["accounts_skipped"] += 1
            skipped = {
                "ok": False,
                "status": "skipped_missing_credentials",
                "account_id": account_id,
            }
            summary["account_results"].append(skipped)
            print(
                f"[dialogs_checker] account_summary "
                f"user_id={user_id} account_id={account_id} "
                f"status={skipped['status']}"
            )
            continue

        account_result = await check_account_dialogs(
            user_id=user_id,
            account_id=account_id,
            cookies_json=cookies_json,
            proxy_text=proxy_text,
            headless=headless,
            olx_profile_name=fresh_account.get("olx_profile_name"),
        )

        summary["accounts_checked"] += 1
        summary["account_results"].append(account_result)
        summary["total_new_incoming_count"] += account_result.get("new_incoming_count", 0)
        summary["new_incoming_events"].extend(account_result.get("new_incoming_events", []))

        print(
            f"[dialogs_checker] account_summary "
            f"user_id={user_id} account_id={account_id} "
            f"status={account_result.get('status')} "
            f"parsed={account_result.get('parsed_dialogs_count')} "
            f"new_incoming={account_result.get('new_incoming_count')} "
            f"final_url={account_result.get('final_url')} "
            f"error={account_result.get('error')}"
        )

    return summary