from __future__ import annotations

from db import (
    get_account_by_id,
    get_active_users,
    get_proxy_by_id,
    get_user_accounts,
)
from olx.account_runtime import close_idle_account_runtimes
from olx.dialogs_checker import check_user_dialogs
from olx.dialogs_notifier import send_incoming_dialog_notifications
from olx.profile_manager_gologin import AccountRuntimeBlockedError

DIALOGS_POLL_INTERVAL_SECONDS = 180
RUNTIME_CLEANUP_INTERVAL_SECONDS = 60


async def run_dialogs_polling_for_user(
    *,
    application,
    user_id: int,
    telegram_chat_id: int,
) -> dict:
    accounts = get_user_accounts(user_id)

    alive_accounts: list[dict] = []
    proxies_by_id: dict[int, dict] = {}

    for account in accounts:
        account_id = account.get("id")
        if not account_id:
            continue

        fresh_account = get_account_by_id(user_id, account_id)
        if not fresh_account:
            print(f"[dialogs_jobs] skip deleted account_id={account_id}")
            continue

        alive_accounts.append(fresh_account)

        proxy_id = fresh_account.get("proxy_id")
        if proxy_id and proxy_id not in proxies_by_id:
            proxy = get_proxy_by_id(user_id, proxy_id)
            if proxy:
                proxies_by_id[proxy_id] = proxy

    result = await check_user_dialogs(
        user_id=user_id,
        accounts=alive_accounts,
        proxies_by_id=proxies_by_id,
        headless=True,
    )

    accounts_by_id = {a["id"]: a for a in alive_accounts}
    await send_incoming_dialog_notifications(
        bot=application.bot,
        chat_id=telegram_chat_id,
        events=result.get("new_incoming_events", []),
        accounts_by_id=accounts_by_id,
    )

    return result


async def run_dialogs_polling_iteration(application) -> None:
    users = get_active_users()

    for user in users:
        telegram_id = user.get("telegram_id")
        user_id = user.get("id")

        if not telegram_id or not user_id:
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


async def _dialogs_poll_job_callback(context) -> None:
    try:
        await run_dialogs_polling_iteration(context.application)
    except AccountRuntimeBlockedError as exc:
        print(f"[dialogs_jobs] poll job runtime blocked: {exc}")
    except Exception as exc:
        print(f"[dialogs_jobs] poll job failed: {exc}")


async def _runtime_cleanup_job_callback(context) -> None:
    closed = await close_idle_account_runtimes()
    if closed:
        print(f"[account_runtime] closed idle runtimes: {closed}")


def start_dialogs_jobs(application) -> None:
    if application.job_queue is None:
        print("[dialogs_jobs] JobQueue is not available. Install python-telegram-bot[job-queue].")
        return

    application.job_queue.run_repeating(
        _dialogs_poll_job_callback,
        interval=DIALOGS_POLL_INTERVAL_SECONDS,
        first=30,
        name="dialogs_poll_job",
    )
    application.job_queue.run_repeating(
        _runtime_cleanup_job_callback,
        interval=RUNTIME_CLEANUP_INTERVAL_SECONDS,
        first=60,
        name="account_runtime_cleanup_job",
    )