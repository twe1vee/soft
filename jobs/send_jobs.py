from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from telegram.ext import Application

from db import (
    create_message,
    get_account_by_id,
    get_ad_by_id,
    get_proxy_by_id,
    update_account_last_check,
    update_account_status,
    update_ad_status,
    update_pending_action_status,
    update_proxy_last_check,
    update_proxy_status,
)
from olx.message_sender import send_message_to_ad

BOT_DATA_KEY = "send_jobs_manager"
SEND_JITTER_MIN_SECONDS = 8
SEND_JITTER_MAX_SECONDS = 18

TRANSIENT_SEND_STATUSES = {
    "message_input_not_found",
    "send_button_not_found",
    "send_clicked_unverified",
    "timeout",
}

DEAD_SEND_STATUSES = {
    "cloudfront_blocked",
    "login_required_or_chat_blocked",
    "browser_failed",
}

WRITE_LIMITED_SEND_STATUSES = {
    "daily_limit_reached",
}


@dataclass(slots=True)
class SendMessageJob:
    job_id: str
    user_id: int
    ad_row_id: int
    pending_action_id: int
    account_id: int
    proxy_id: int
    chat_id: int
    source_message_id: int | None = None

    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None

    error: str | None = None
    result: dict[str, Any] | None = None


def _build_send_result_text(
    ad: dict | None,
    account: dict | None,
    proxy: dict | None,
    result: dict[str, Any],
    *,
    job_id: str,
) -> str:
    status = result.get("status") or "unknown"
    error = result.get("error")
    account_status = result.get("account_status")

    account_status_map = {
        "working": "живой",
        "loading_retry": "не прогрузился, был повтор",
        "write_limited": "лимит на новые сообщения",
        "dead": "мёртвый",
    }

    account_status_text = account_status_map.get(account_status, account_status)

    if result.get("ok") or result.get("sent") or status == "sent":
        if account_status_text:
            return f"📤 Доставлено\nСтатус аккаунта: {account_status_text}"
        return "📤 Доставлено"

    if error:
        if account_status_text:
            return f"📤 Ошибка\n{error}\nСтатус аккаунта: {account_status_text}"
        return f"📤 Ошибка\n{error}"

    if account_status_text:
        return f"📤 Ошибка\nСтатус: {status}\nСтатус аккаунта: {account_status_text}"

    return f"📤 Ошибка\nСтатус: {status}"


def _build_failure_result(
    *,
    status: str,
    error: str,
    ad: dict | None = None,
    account: dict | None = None,
    proxy: dict | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "sent": False,
        "status": status,
        "error": error,
        "ad_url": (ad or {}).get("url"),
        "account_id": (account or {}).get("id"),
        "proxy_id": (proxy or {}).get("id"),
        "final_url": (ad or {}).get("url"),
    }


def _map_send_status_to_account_status(send_status: str, *, retry_used: bool) -> str | None:
    if send_status == "sent":
        return "working"

    if send_status in WRITE_LIMITED_SEND_STATUSES:
        return "write_limited"

    if send_status in TRANSIENT_SEND_STATUSES:
        return "dead" if retry_used else "loading_retry"

    if send_status in DEAD_SEND_STATUSES:
        return "dead"

    return None

async def _sleep_before_send(account_id: int) -> None:
    delay = random.uniform(SEND_JITTER_MIN_SECONDS, SEND_JITTER_MAX_SECONDS)
    print(f"[send_jobs] pre_send_delay account_id={account_id} sleep={delay:.2f}s")
    await asyncio.sleep(delay)

class SendJobsManager:
    def __init__(self, application: Application, worker_count: int = 2):
        self.application = application
        self.worker_count = max(1, int(worker_count))
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.jobs: dict[str, SendMessageJob] = {}
        self.worker_tasks: list[asyncio.Task] = []
        self.account_locks: dict[int, asyncio.Lock] = {}
        self._start_lock = asyncio.Lock()
        self.started = False

    async def start(self) -> None:
        async with self._start_lock:
            if self.started:
                return

            for index in range(self.worker_count):
                task = asyncio.create_task(
                    self._worker_loop(index + 1),
                    name=f"send-worker-{index + 1}",
                )
                self.worker_tasks.append(task)

            self.started = True
            print(f"[send_jobs] started workers={self.worker_count}")

    async def stop(self) -> None:
        if not self.worker_tasks:
            self.started = False
            return

        for task in self.worker_tasks:
            task.cancel()

        await asyncio.gather(*self.worker_tasks, return_exceptions=True)
        self.worker_tasks.clear()
        self.started = False
        print("[send_jobs] stopped")

    async def enqueue(
        self,
        *,
        user_id: int,
        ad_row_id: int,
        pending_action_id: int,
        account_id: int,
        proxy_id: int,
        chat_id: int,
        source_message_id: int | None,
    ) -> SendMessageJob:
        job = SendMessageJob(
            job_id=uuid4().hex[:12],
            user_id=user_id,
            ad_row_id=ad_row_id,
            pending_action_id=pending_action_id,
            account_id=account_id,
            proxy_id=proxy_id,
            chat_id=chat_id,
            source_message_id=source_message_id,
        )
        self.jobs[job.job_id] = job
        await self.queue.put(job.job_id)
        print(
            f"[send_jobs] queued job_id={job.job_id} "
            f"user_id={user_id} ad_row_id={ad_row_id} account_id={account_id}"
        )
        return job

    def get_queue_size(self) -> int:
        return self.queue.qsize()

    def get_account_lock(self, account_id: int) -> asyncio.Lock:
        lock = self.account_locks.get(account_id)
        if lock is None:
            lock = asyncio.Lock()
            self.account_locks[account_id] = lock
        return lock

    async def _worker_loop(self, worker_no: int) -> None:
        print(f"[send_jobs] worker_started worker={worker_no}")
        try:
            while True:
                job_id = await self.queue.get()
                job = self.jobs.get(job_id)
                if job is None:
                    self.queue.task_done()
                    continue

                try:
                    await self._run_send_job(worker_no, job)
                except Exception as exc:
                    job.status = "failed"
                    job.error = str(exc)
                    job.finished_at = time.time()
                    print(
                        f"[send_jobs] worker_crash worker={worker_no} "
                        f"job_id={job.job_id} error={exc}"
                    )
                    await self._notify_result(
                        job=job,
                        result={
                            "ok": False,
                            "sent": False,
                            "status": "worker_failed",
                            "error": str(exc),
                        },
                        ad=None,
                        account=None,
                        proxy=None,
                    )
                finally:
                    self.queue.task_done()
        except asyncio.CancelledError:
            print(f"[send_jobs] worker_stopped worker={worker_no}")
            raise

    async def _run_send_job(self, worker_no: int, job: SendMessageJob) -> None:
        account_lock = self.get_account_lock(job.account_id)

        async with account_lock:
            job.status = "running"
            job.started_at = time.time()

            print(
                f"[send_jobs] worker_pick worker={worker_no} "
                f"job_id={job.job_id} account_id={job.account_id}"
            )

            ad = get_ad_by_id(job.user_id, job.ad_row_id)
            if not ad:
                result = _build_failure_result(
                    status="ad_not_found",
                    error="Объявление не найдено или не принадлежит пользователю",
                )
                job.result = result
                job.status = "failed"
                job.finished_at = time.time()
                await self._notify_result(job=job, result=result, ad=None, account=None, proxy=None)
                return

            account = get_account_by_id(job.user_id, job.account_id)
            if not account:
                update_ad_status(job.user_id, job.ad_row_id, "send_blocked_account_not_found")
                update_pending_action_status(job.pending_action_id, "failed")
                result = _build_failure_result(
                    status="account_not_found",
                    error="Аккаунт не найден",
                    ad=ad,
                )
                job.result = result
                job.status = "failed"
                job.finished_at = time.time()
                await self._notify_result(job=job, result=result, ad=ad, account=None, proxy=None)
                return

            cookies_json = account.get("cookies_json")
            if not cookies_json:
                update_ad_status(job.user_id, job.ad_row_id, "send_blocked_missing_cookies")
                update_pending_action_status(job.pending_action_id, "failed")
                result = _build_failure_result(
                    status="missing_cookies",
                    error="У аккаунта отсутствуют cookies_json",
                    ad=ad,
                    account=account,
                )
                job.result = result
                job.status = "failed"
                job.finished_at = time.time()
                await self._notify_result(job=job, result=result, ad=ad, account=account, proxy=None)
                return

            proxy = get_proxy_by_id(job.user_id, job.proxy_id)
            if not proxy or not proxy.get("proxy_text"):
                update_ad_status(job.user_id, job.ad_row_id, "send_blocked_proxy_not_found")
                update_pending_action_status(job.pending_action_id, "failed")
                result = _build_failure_result(
                    status="proxy_not_found",
                    error="Proxy не найден или пустой",
                    ad=ad,
                    account=account,
                    proxy=proxy,
                )
                job.result = result
                job.status = "failed"
                job.finished_at = time.time()
                await self._notify_result(job=job, result=result, ad=ad, account=account, proxy=proxy)
                return

            ad_url = ad.get("url")
            draft_text = (ad.get("draft_text") or "").strip()

            if not ad_url:
                update_ad_status(job.user_id, job.ad_row_id, "send_blocked_missing_url")
                update_pending_action_status(job.pending_action_id, "failed")
                result = _build_failure_result(
                    status="missing_url",
                    error="У объявления отсутствует URL",
                    ad=ad,
                    account=account,
                    proxy=proxy,
                )
                job.result = result
                job.status = "failed"
                job.finished_at = time.time()
                await self._notify_result(job=job, result=result, ad=ad, account=account, proxy=proxy)
                return

            if not draft_text:
                update_ad_status(job.user_id, job.ad_row_id, "send_blocked_empty_draft")
                update_pending_action_status(job.pending_action_id, "failed")
                result = _build_failure_result(
                    status="empty_draft",
                    error="У объявления пустой draft_text",
                    ad=ad,
                    account=account,
                    proxy=proxy,
                )
                job.result = result
                job.status = "failed"
                job.finished_at = time.time()
                await self._notify_result(job=job, result=result, ad=ad, account=account, proxy=proxy)
                return

            update_ad_status(job.user_id, job.ad_row_id, "sending")
            update_pending_action_status(job.pending_action_id, "running")
            update_account_last_check(job.user_id, job.account_id)

            await _sleep_before_send(job.account_id)

            result = await send_message_to_ad(
                cookies_json=cookies_json,
                proxy_text=proxy["proxy_text"],
                ad_url=ad_url,
                message_text=draft_text,
                headless=True,
                user_id=job.user_id,
                account_id=job.account_id,
                olx_profile_name=account.get("olx_profile_name"),
            )

            send_status = result.get("status") or "unknown_error"
            retry_used = False

            if send_status in TRANSIENT_SEND_STATUSES:
                update_account_status(job.user_id, job.account_id, "loading_retry")
                await asyncio.sleep(random.uniform(2.5, 5.5))

                retry_used = True
                retry_result = await send_message_to_ad(
                    cookies_json=cookies_json,
                    proxy_text=proxy["proxy_text"],
                    ad_url=ad_url,
                    message_text=draft_text,
                    headless=True,
                    user_id=job.user_id,
                    account_id=job.account_id,
                    olx_profile_name=account.get("olx_profile_name"),
                )

                retry_status = retry_result.get("status") or "unknown_error"
                retry_result["first_try_status"] = send_status
                retry_result["retry_used"] = True

                result = retry_result
                send_status = retry_status

            update_proxy_last_check(job.user_id, proxy["id"])

            account_status = _map_send_status_to_account_status(send_status, retry_used=retry_used)
            if account_status:
                update_account_status(job.user_id, job.account_id, account_status)
                result["account_status"] = account_status

            if send_status == "sent":
                update_proxy_status(job.user_id, proxy["id"], "working")
                update_ad_status(job.user_id, job.ad_row_id, "sent")
                update_pending_action_status(job.pending_action_id, "done")
                create_message(
                    ad_db_id=job.ad_row_id,
                    direction="outgoing",
                    text=draft_text,
                    status="sent",
                )
                job.status = "done"
            else:
                if send_status == "proxy_failed":
                    update_proxy_status(job.user_id, proxy["id"], "failed")

                update_ad_status(job.user_id, job.ad_row_id, f"send_failed:{send_status}")
                update_pending_action_status(job.pending_action_id, "failed")
                create_message(
                    ad_db_id=job.ad_row_id,
                    direction="outgoing",
                    text=draft_text,
                    status=f"send_failed:{send_status}",
                )
                job.status = "failed"

            job.result = result
            job.finished_at = time.time()

            updated_ad = get_ad_by_id(job.user_id, job.ad_row_id) or ad
            await self._notify_result(
                job=job,
                result=result,
                ad=updated_ad,
                account=account,
                proxy=proxy,
            )

            print(
                f"[send_jobs] worker_done worker={worker_no} "
                f"job_id={job.job_id} status={job.status} "
                f"send_status={send_status} account_status={result.get('account_status')}"
            )

    async def _notify_result(
        self,
        *,
        job: SendMessageJob,
        result: dict[str, Any],
        ad: dict | None,
        account: dict | None,
        proxy: dict | None,
    ) -> None:
        text = _build_send_result_text(
            ad=ad,
            account=account,
            proxy=proxy,
            result=result,
            job_id=job.job_id,
        )

        try:
            await self.application.bot.send_message(
                chat_id=job.chat_id,
                text=text,
                reply_to_message_id=job.source_message_id,
            )
        except Exception as exc:
            print(f"[send_jobs] notify_failed job_id={job.job_id} error={exc}")


async def ensure_send_jobs_started(
    application: Application,
    worker_count: int = 2,
) -> "SendJobsManager":
    manager = application.bot_data.get(BOT_DATA_KEY)
    if manager is None:
        manager = SendJobsManager(application=application, worker_count=worker_count)
        application.bot_data[BOT_DATA_KEY] = manager

    await manager.start()
    return manager


def get_send_jobs_manager(application: Application) -> SendJobsManager | None:
    value = application.bot_data.get(BOT_DATA_KEY)
    if isinstance(value, SendJobsManager):
        return value
    return None