from __future__ import annotations

import asyncio
import random
import time

from db import (
    update_account_status,
    get_account_by_id,
    get_active_users,
    get_proxy_by_id,
    get_user_accounts,
)
from db.accounts import (
    get_expired_write_blocked_accounts_with_profiles,
    get_stale_accounts_with_profiles,
)
from olx.account_runtime import (
    close_account_runtime,
    close_idle_account_runtimes,
    get_account_runtime_busy_reason,
)
from olx.dialogs_checker import check_user_dialogs
from olx.dialogs_notifier import send_incoming_dialog_notifications
from olx.profile_manager_gologin import (
    AccountRuntimeBlockedError,
    GOLOGIN_PROFILE_IDLE_DELETE_SECONDS,
    cleanup_stale_gologin_profiles,
    WRITE_BLOCKED_DELETE_SECONDS,
    cleanup_expired_write_blocked_accounts,
)

DIALOGS_POLL_INTERVAL_MIN_SECONDS = 30
DIALOGS_POLL_INTERVAL_MAX_SECONDS = 45
GOLOGIN_PROFILE_CLEANUP_INTERVAL_SECONDS = 900
RUNTIME_CLEANUP_INTERVAL_SECONDS = 60

ALIVE_ACCOUNT_STATUSES = {
    "new",
    "connected",
    "checked",
    "working",
    "write_limited",
    "loading_retry",
    "write_blocked",
}

DIALOGS_SKIP_BUSY_REASONS = {
    "send_message",
    "check_account_alive",
    "proxy_check",
}


def _get_next_dialogs_poll_interval_seconds() -> int:
    return random.randint(
        DIALOGS_POLL_INTERVAL_MIN_SECONDS,
        DIALOGS_POLL_INTERVAL_MAX_SECONDS,
    )


def _schedule_next_dialogs_poll_job(application, *, first: int | None = None) -> None:
    if application.job_queue is None:
        return

    next_interval = first if first is not None else _get_next_dialogs_poll_interval_seconds()

    application.job_queue.run_once(
        _dialogs_poll_job_callback,
        when=next_interval,
        name="dialogs_poll_job",
        job_kwargs={
            "misfire_grace_time": 120,
        },
    )
    print(f"[dialogs_jobs] next dialogs poll scheduled after {next_interval}s")


def is_account_alive_for_dialogs(account: dict) -> bool:
    status = (account.get("status") or "").strip().lower()
    if status not in ALIVE_ACCOUNT_STATUSES:
        return False

    if not account.get("proxy_id"):
        return False

    if not account.get("cookies_json"):
        return False

    return True


def _build_empty_poll_result(total_accounts: int) -> dict:
    return {
        "ok": True,
        "status": "ok",
        "accounts_checked": 0,
        "accounts_skipped": total_accounts,
        "total_new_incoming_count": 0,
        "account_results": [],
        "new_incoming_events": [],
        "sent_notifications": 0,
    }


async def run_dialogs_polling_for_user(
    *,
    application,
    user_id: int,
    telegram_chat_id: int,
) -> dict:
    print(f"[dialogs_jobs] start user_id={user_id} telegram_chat_id={telegram_chat_id}")

    accounts = get_user_accounts(user_id)
    print(
        f"[dialogs_jobs] loaded_account_ids user_id={user_id} "
        f"ids={[a.get('id') for a in accounts]}"
    )

    alive_accounts: list[dict] = []
    proxies_by_id: dict[int, dict] = {}
    skipped_busy_accounts = 0

    print(f"[dialogs_jobs] loaded_accounts user_id={user_id} total={len(accounts)}")

    for account in accounts:
        account_id = account.get("id")
        if not account_id:
            print(f"[dialogs_jobs] skip account without id user_id={user_id}")
            continue

        fresh_account = get_account_by_id(user_id, account_id)
        if not fresh_account:
            print(f"[dialogs_jobs] skip deleted account_id={account_id}")
            continue

        if not is_account_alive_for_dialogs(fresh_account):
            print(
                f"[dialogs_jobs] skip_account user_id={user_id} "
                f"account_id={fresh_account.get('id')} "
                f"proxy_id={fresh_account.get('proxy_id')} "
                f"status={fresh_account.get('status')} "
                f"has_cookies={bool(fresh_account.get('cookies_json'))} "
                f"market={fresh_account.get('market')}"
            )
            continue

        busy_reason = get_account_runtime_busy_reason(int(account_id))
        if busy_reason in DIALOGS_SKIP_BUSY_REASONS:
            skipped_busy_accounts += 1
            print(
                f"[dialogs_jobs] skip_busy_account "
                f"user_id={user_id} account_id={account_id} "
                f"busy_reason={busy_reason} market={fresh_account.get('market')}"
            )
            continue

        proxy_id = fresh_account.get("proxy_id")
        proxy = get_proxy_by_id(user_id, proxy_id)
        if not proxy or not proxy.get("proxy_text"):
            print(
                f"[dialogs_jobs] skip account_id={account_id} "
                f"proxy_id={proxy_id} reason=proxy_not_found "
                f"market={fresh_account.get('market')}"
            )
            continue

        print(
            f"[dialogs_jobs] alive_account user_id={user_id} "
            f"account_id={fresh_account.get('id')} proxy_id={proxy_id} "
            f"status={fresh_account.get('status')} market={fresh_account.get('market')}"
        )

        alive_accounts.append(fresh_account)
        proxies_by_id[int(proxy_id)] = proxy
        print(
            f"[dialogs_jobs] proxy loaded "
            f"account_id={account_id} proxy_id={proxy_id} market={fresh_account.get('market')}"
        )

    print(
        f"[dialogs_jobs] polling user_id={user_id} "
        f"alive_accounts={len(alive_accounts)} proxies={len(proxies_by_id)}"
    )

    if not alive_accounts:
        print(f"[dialogs_jobs] no alive accounts user_id={user_id}")
        result = _build_empty_poll_result(len(accounts))
        result["accounts_skipped"] = len(accounts) + skipped_busy_accounts
        return result

    result = await check_user_dialogs(
        user_id=user_id,
        accounts=alive_accounts,
        proxies_by_id=proxies_by_id,
    )

    accounts_checked = int(result.get("accounts_checked") or 0)
    accounts_skipped = int(result.get("accounts_skipped") or 0) + skipped_busy_accounts
    total_new_incoming_count = int(result.get("total_new_incoming_count") or 0)
    account_results = result.get("account_results") or []
    new_incoming_events = result.get("new_incoming_events") or []

    result["accounts_skipped"] = accounts_skipped

    print(
        f"[dialogs_jobs] result user_id={user_id} "
        f"accounts_checked={accounts_checked} "
        f"accounts_skipped={accounts_skipped} "
        f"total_new_incoming_count={total_new_incoming_count} "
        f"events={len(new_incoming_events)}"
    )

    for item in account_results:
        account_id = item.get("account_id")
        status = (item.get("status") or "").strip().lower()

        print(
            f"[dialogs_jobs] account_result user_id={user_id} "
            f"account_id={account_id} "
            f"status={status} "
            f"parsed={item.get('parsed_dialogs_count')} "
            f"new_incoming={item.get('new_incoming_count')} "
            f"error={item.get('error')} "
            f"market={item.get('market_code')}"
        )

        if not account_id:
            continue

        try:
            if status in {"not_logged_in", "cloudfront_blocked"}:
                update_account_status(user_id, int(account_id), "dead")
                print(
                    f"[dialogs_jobs] account_marked_dead "
                    f"user_id={user_id} account_id={account_id} reason={status}"
                )
            elif status == "ok":
                update_account_status(user_id, int(account_id), "working")
                print(
                    f"[dialogs_jobs] account_marked_working "
                    f"user_id={user_id} account_id={account_id}"
                )
        except Exception as exc:
            print(
                f"[dialogs_jobs] account_status_update_failed "
                f"user_id={user_id} account_id={account_id} "
                f"status={status} error={exc}"
            )

    accounts_by_id = {int(a["id"]): a for a in alive_accounts if a.get("id") is not None}

    sent_notifications = await send_incoming_dialog_notifications(
        bot=application.bot,
        chat_id=telegram_chat_id,
        events=new_incoming_events,
        accounts_by_id=accounts_by_id,
    )

    print(
        f"[dialogs_jobs] notifier_done user_id={user_id} "
        f"events={len(new_incoming_events)} "
        f"sent_notifications={sent_notifications}"
    )

    result["sent_notifications"] = sent_notifications
    return result


async def run_dialogs_polling_iteration(application) -> None:
    users = get_active_users()
    print(f"[dialogs_jobs] iteration_start users={len(users)}")

    for user in users:
        user_id = user.get("id")
        telegram_id = user.get("telegram_id")
        if not user_id or not telegram_id:
            continue

        try:
            await run_dialogs_polling_for_user(
                application=application,
                user_id=user_id,
                telegram_chat_id=int(telegram_id),
            )
        except AccountRuntimeBlockedError as exc:
            print(f"[dialogs_jobs] user_id={user_id} runtime blocked: {exc}")
        except Exception as exc:
            print(f"[dialogs_jobs] user_id={user_id} polling failed: {exc}")

    print("[dialogs_jobs] iteration_done")


async def _dialogs_poll_job_callback(context) -> None:
    started = time.perf_counter()
    print("[dialogs_jobs] poll_job_tick")
    try:
        await run_dialogs_polling_iteration(context.application)
    except AccountRuntimeBlockedError as exc:
        print(f"[dialogs_jobs] poll job runtime blocked: {exc}")
    except Exception as exc:
        print(f"[dialogs_jobs] poll job failed: {exc}")
    finally:
        took = int((time.perf_counter() - started) * 1000)
        print(f"[dialogs_jobs] poll_job_done took_ms={took}")
        _schedule_next_dialogs_poll_job(context.application)


async def _runtime_cleanup_job_callback(context) -> None:
    closed = await close_idle_account_runtimes()
    if closed:
        print(f"[account_runtime] closed idle runtimes: {closed}")
    else:
        print("[account_runtime] cleanup tick no idle runtimes")


async def _gologin_profile_cleanup_job_callback(context) -> None:
    try:
        stale_accounts = get_stale_accounts_with_profiles(
            GOLOGIN_PROFILE_IDLE_DELETE_SECONDS
        )
        expired_write_blocked = get_expired_write_blocked_accounts_with_profiles(
            WRITE_BLOCKED_DELETE_SECONDS
        )

        if stale_accounts:
            print(
                f"[gologin_cleanup] stale_accounts_found={len(stale_accounts)} "
                f"idle_seconds={GOLOGIN_PROFILE_IDLE_DELETE_SECONDS}"
            )
        else:
            print(
                f"[gologin_cleanup] no stale accounts "
                f"idle_seconds={GOLOGIN_PROFILE_IDLE_DELETE_SECONDS}"
            )

        if expired_write_blocked:
            print(
                f"[gologin_cleanup] expired_write_blocked_found={len(expired_write_blocked)} "
                f"grace_seconds={WRITE_BLOCKED_DELETE_SECONDS}"
            )
        else:
            print(
                f"[gologin_cleanup] no expired write_blocked accounts "
                f"grace_seconds={WRITE_BLOCKED_DELETE_SECONDS}"
            )

        account_ids_to_preclose = {
            int(item["id"]) for item in stale_accounts
        } | {
            int(item["id"]) for item in expired_write_blocked
        }

        for account_id in sorted(account_ids_to_preclose):
            closed = await close_account_runtime(
                account_id,
                reason="stale_account_cleanup",
            )
            print(
                f"[gologin_cleanup] preclose account_id={account_id} "
                f"closed_runtime={closed}"
            )

        stale_result = await asyncio.to_thread(
            cleanup_stale_gologin_profiles,
            idle_seconds=GOLOGIN_PROFILE_IDLE_DELETE_SECONDS,
        )
        print(
            f"[gologin_cleanup] stale found={stale_result.get('found_count', 0)} "
            f"deleted={stale_result.get('deleted_count', 0)} "
            f"failed={stale_result.get('failed_count', 0)}"
        )

        write_blocked_result = await asyncio.to_thread(
            cleanup_expired_write_blocked_accounts,
            grace_seconds=WRITE_BLOCKED_DELETE_SECONDS,
        )
        print(
            f"[gologin_cleanup] write_blocked found={write_blocked_result.get('found_count', 0)} "
            f"deleted={write_blocked_result.get('deleted_count', 0)} "
            f"failed={write_blocked_result.get('failed_count', 0)}"
        )

    except Exception as exc:
        print(f"[gologin_cleanup] failed error={exc}")


def start_dialogs_jobs(application) -> None:
    if application.job_queue is None:
        print("[dialogs_jobs] JobQueue is not available. Install python-telegram-bot[job-queue].")
        return

    _schedule_next_dialogs_poll_job(application, first=15)
    print("[dialogs_jobs] dialogs_poll_job added dynamic interval first=15")

    application.job_queue.run_repeating(
        _runtime_cleanup_job_callback,
        interval=RUNTIME_CLEANUP_INTERVAL_SECONDS,
        first=60,
        name="account_runtime_cleanup_job",
    )
    print(
        f"[dialogs_jobs] account_runtime_cleanup_job added "
        f"interval={RUNTIME_CLEANUP_INTERVAL_SECONDS} first=60"
    )

    application.job_queue.run_repeating(
        _gologin_profile_cleanup_job_callback,
        interval=GOLOGIN_PROFILE_CLEANUP_INTERVAL_SECONDS,
        first=300,
        name="gologin_profile_cleanup_job",
    )
    print(
        f"[dialogs_jobs] gologin_profile_cleanup_job added "
        f"interval={GOLOGIN_PROFILE_CLEANUP_INTERVAL_SECONDS} first=300"
    )