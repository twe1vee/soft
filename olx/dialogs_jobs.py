from __future__ import annotations

import time

from db import (
    get_account_by_id,
    get_active_users,
    get_proxy_by_id,
    get_user_accounts,
)
from olx.account_runtime import close_idle_account_runtimes
from olx.dialogs_checker import check_user_dialogs
from olx.dialogs_notifier import send_incoming_dialog_notifications
from olx.profile_manager_gologin import (
    AccountRuntimeBlockedError,
    GOLOGIN_PROFILE_IDLE_DELETE_SECONDS,
    cleanup_stale_gologin_profiles,
)

DIALOGS_POLL_INTERVAL_SECONDS = 60
GOLOGIN_PROFILE_CLEANUP_INTERVAL_SECONDS = 900
RUNTIME_CLEANUP_INTERVAL_SECONDS = 60


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

        alive_accounts.append(fresh_account)
        print(
            f"[dialogs_jobs] alive_account user_id={user_id} "
            f"account_id={fresh_account.get('id')} "
            f"proxy_id={fresh_account.get('proxy_id')} "
            f"status={fresh_account.get('status')}"
        )

        proxy_id = fresh_account.get("proxy_id")
        if proxy_id and proxy_id not in proxies_by_id:
            proxy = get_proxy_by_id(user_id, proxy_id)
            if proxy:
                proxies_by_id[proxy_id] = proxy
                print(f"[dialogs_jobs] proxy loaded account_id={account_id} proxy_id={proxy_id}")
            else:
                print(f"[dialogs_jobs] proxy missing account_id={account_id} proxy_id={proxy_id}")

    print(
        f"[dialogs_jobs] polling user_id={user_id} "
        f"alive_accounts={len(alive_accounts)} proxies={len(proxies_by_id)}"
    )

    result = await check_user_dialogs(
        user_id=user_id,
        accounts=alive_accounts,
        proxies_by_id=proxies_by_id,
        headless=True,
    )

    print(
        f"[dialogs_jobs] result user_id={user_id} "
        f"checked={result.get('accounts_checked', 0)} "
        f"skipped={result.get('accounts_skipped', 0)} "
        f"new_incoming={result.get('total_new_incoming_count', 0)} "
        f"events={len(result.get('new_incoming_events', []))}"
    )

    for account_result in result.get("account_results", []):
        print(
            f"[dialogs_jobs] account_result "
            f"user_id={user_id} "
            f"account_id={account_result.get('account_id')} "
            f"status={account_result.get('status')} "
            f"parsed={account_result.get('parsed_dialogs_count', 0)} "
            f"new_incoming={account_result.get('new_incoming_count', 0)} "
            f"error={account_result.get('error')}"
        )

    accounts_by_id = {a["id"]: a for a in alive_accounts}

    sent_notifications = await send_incoming_dialog_notifications(
        bot=application.bot,
        chat_id=telegram_chat_id,
        events=result.get("new_incoming_events", []),
        accounts_by_id=accounts_by_id,
    )

    result["sent_notifications"] = sent_notifications

    print(
        f"[dialogs_jobs] notifier_done "
        f"user_id={user_id} "
        f"events={len(result.get('new_incoming_events', []))} "
        f"sent_notifications={sent_notifications}"
    )

    return result


async def run_dialogs_polling_iteration(application) -> None:
    users = get_active_users()
    print(f"[dialogs_jobs] iteration_start users={len(users)}")

    for user in users:
        telegram_id = user.get("telegram_id")
        user_id = user.get("id")

        if not telegram_id or not user_id:
            print(
                f"[dialogs_jobs] skip invalid user "
                f"user_id={user_id} telegram_id={telegram_id}"
            )
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


async def _runtime_cleanup_job_callback(context) -> None:
    closed = await close_idle_account_runtimes()
    if closed:
        print(f"[account_runtime] closed idle runtimes: {closed}")
    else:
        print("[account_runtime] cleanup tick no idle runtimes")


async def _gologin_profile_cleanup_job_callback(context) -> None:
    try:
        result = cleanup_stale_gologin_profiles(
            idle_seconds=GOLOGIN_PROFILE_IDLE_DELETE_SECONDS
        )
        print(
            f"[gologin_cleanup] found={result.get('found_count', 0)} "
            f"deleted={result.get('deleted_count', 0)} "
            f"failed={result.get('failed_count', 0)}"
        )
    except Exception as exc:
        print(f"[gologin_cleanup] failed error={exc}")


def start_dialogs_jobs(application) -> None:
    if application.job_queue is None:
        print("[dialogs_jobs] JobQueue is not available. Install python-telegram-bot[job-queue].")
        return

    application.job_queue.run_repeating(
        _dialogs_poll_job_callback,
        interval=DIALOGS_POLL_INTERVAL_SECONDS,
        first=15,
        name="dialogs_poll_job",
        job_kwargs={
            "max_instances": 1,
            "coalesce": True,
            "misfire_grace_time": 120,
        },
    )
    print(
        f"[dialogs_jobs] dialogs_poll_job added "
        f"interval={DIALOGS_POLL_INTERVAL_SECONDS} first=15"
    )

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