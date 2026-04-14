from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import Application

from db import (
    get_account_by_id,
    get_proxy_by_id,
    update_account_last_check,
    update_account_profile_name,
    update_account_status,
    update_proxy_last_check,
    update_proxy_status,
)
from olx.account_session import check_account_alive
from olx.proxy_check import check_proxy_alive

BOT_DATA_KEY = "check_jobs_manager"


def _proxy_short(proxy_text: str, max_len: int = 45) -> str:
    value = (proxy_text or "").strip()
    if not value:
        return ""

    lower = value.lower()
    if "://" in lower:
        value = value.split("://", 1)[1]

    if "@" in value:
        right = value.rsplit("@", 1)[1].strip()
        if right:
            return right[:max_len] if len(right) > max_len else right

    parts = [p.strip() for p in value.split(":")]

    if len(parts) >= 2:
        host = parts[0]
        port = parts[1]
        host_port = f"{host}:{port}"
        return host_port[:max_len] if len(host_port) > max_len else host_port

    return value[:max_len] if len(value) > max_len else value


def _humanize_proxy_status(status: str | None) -> str:
    value = (status or "").strip().lower()

    if value in {"working", "connected", "checked"}:
        return "живой"
    if value in {"timeout"}:
        return "timeout"
    if value in {"unstable"}:
        return "нестабильный"
    if value in {"cloudfront_blocked"}:
        return "заблокирован olx"
    if value in {"proxy_failed"}:
        return "ошибка прокси"
    if value in {"failed", "dead", "invalid_type"}:
        return "ошибка проверки"

    return "не проверен"


def _normalize_proxy_status_for_db(raw_status: str | None) -> str:
    value = (raw_status or "").strip().lower()

    allowed_statuses = {
        "working",
        "timeout",
        "unstable",
        "cloudfront_blocked",
        "proxy_failed",
        "failed",
        "invalid_type",
    }

    if value in allowed_statuses:
        return value

    return "failed"


def _normalize_account_status_for_db(raw_status: str | None) -> str:
    value = (raw_status or "").strip().lower()

    allowed = {
        "connected",
        "working",
        "not_logged_in",
        "cloudfront_blocked",
        "proxy_failed",
        "timeout",
        "unstable",
        "failed",
        "missing_proxy",
        "proxy_not_found",
        "missing_cookies",
        "dead",
        "write_blocked",
        "write_limited",
        "loading_retry",
    }
    if value in allowed:
        return value

    return "failed"


def _normalize_proxy_status_from_account_check(account_status: str | None) -> str:
    value = (account_status or "").strip().lower()

    if value in {"connected", "working"}:
        return "working"
    if value in {"timeout"}:
        return "timeout"
    if value in {"unstable"}:
        return "unstable"
    if value in {"cloudfront_blocked"}:
        return "cloudfront_blocked"
    if value in {"proxy_failed", "proxy_not_found", "missing_proxy"}:
        return "proxy_failed"

    return "failed"


def _humanize_account_market(market: str | None) -> str:
    value = (market or "").strip().lower()
    mapping = {
        "olx_pt": "OLX PT",
        "olx_pl": "OLX PL",
    }
    return mapping.get(value, value or "OLX PT")


def _humanize_account_status(status: str | None) -> str:
    value = (status or "").strip().lower()
    mapping = {
        "connected": "живой",
        "working": "живой",
        "not_logged_in": "не авторизован",
        "cloudfront_blocked": "заблокирован olx",
        "proxy_failed": "ошибка прокси",
        "timeout": "timeout",
        "unstable": "нестабильный",
        "failed": "ошибка проверки",
        "missing_proxy": "нет прокси",
        "proxy_not_found": "прокси не найден",
        "missing_cookies": "нет cookies",
        "dead": "мёртвый",
        "write_blocked": "не может отправлять сообщения",
        "write_limited": "лимит на новые сообщения",
        "loading_retry": "не прогрузился, был повтор",
        "gologin_storage_unavailable": "ошибка gologin",
    }
    return mapping.get(value, value or "неизвестно")


def _account_display_name(account: dict) -> str:
    return (
        (account.get("olx_profile_name") or "").strip()
        or (account.get("gologin_profile_name") or "").strip()
        or f"Аккаунт #{account.get('id')}"
    )


def _build_proxy_result_keyboard(proxy_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⬅️ Назад к прокси", callback_data=f"proxy:open:{proxy_id}")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
        ]
    )


def _build_account_result_keyboard(account_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⬅️ Назад к аккаунту", callback_data=f"account:open:{account_id}")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
        ]
    )


def _build_account_check_result_text(account: dict, proxy: dict, result: dict) -> str:
    profile_name = _account_display_name(account)
    status_text = _humanize_account_status(account.get("status"))
    market_text = _humanize_account_market(account.get("market"))
    proxy_text = _proxy_short(proxy.get("proxy_text", ""), max_len=60)
    error = (result.get("error") or "").strip()

    lines = [
        "🔎 Проверка аккаунта завершена",
        "",
        f"Аккаунт: {profile_name}",
        f"Рынок: {market_text}",
        f"Статус: {status_text}",
        f"Прокси: {proxy_text}",
    ]

    if error and status_text != "живой":
        lines.extend(["", f"Причина: {error}"])

    return "\n".join(lines)


@dataclass(slots=True)
class CheckJob:
    job_id: str
    job_type: str
    user_id: int
    chat_id: int
    source_message_id: int | None = None
    proxy_id: int | None = None
    account_id: int | None = None
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class CheckJobsManager:
    def __init__(self, application: Application, worker_count: int = 2):
        self.application = application
        self.worker_count = max(1, int(worker_count))
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.jobs: dict[str, CheckJob] = {}
        self.worker_tasks: list[asyncio.Task] = []
        self.proxy_locks: dict[int, asyncio.Lock] = {}
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
                    name=f"check-worker-{index + 1}",
                )
                self.worker_tasks.append(task)

            self.started = True
            print(f"[check_jobs] started workers={self.worker_count}")

    async def stop(self) -> None:
        if not self.worker_tasks:
            self.started = False
            return

        for task in self.worker_tasks:
            task.cancel()

        await asyncio.gather(*self.worker_tasks, return_exceptions=True)
        self.worker_tasks.clear()
        self.started = False
        print("[check_jobs] stopped")

    def get_proxy_lock(self, proxy_id: int) -> asyncio.Lock:
        lock = self.proxy_locks.get(proxy_id)
        if lock is None:
            lock = asyncio.Lock()
            self.proxy_locks[proxy_id] = lock
        return lock

    def get_account_lock(self, account_id: int) -> asyncio.Lock:
        lock = self.account_locks.get(account_id)
        if lock is None:
            lock = asyncio.Lock()
            self.account_locks[account_id] = lock
        return lock

    async def enqueue_proxy_check(
        self,
        *,
        user_id: int,
        proxy_id: int,
        chat_id: int,
        source_message_id: int | None,
    ) -> CheckJob:
        job = CheckJob(
            job_id=uuid4().hex[:12],
            job_type="proxy_check",
            user_id=user_id,
            proxy_id=proxy_id,
            chat_id=chat_id,
            source_message_id=source_message_id,
        )
        self.jobs[job.job_id] = job
        await self.queue.put(job.job_id)
        print(
            f"[check_jobs] queued type=proxy_check job_id={job.job_id} "
            f"user_id={user_id} proxy_id={proxy_id}"
        )
        return job

    async def enqueue_account_check(
        self,
        *,
        user_id: int,
        account_id: int,
        chat_id: int,
        source_message_id: int | None,
    ) -> CheckJob:
        job = CheckJob(
            job_id=uuid4().hex[:12],
            job_type="account_check",
            user_id=user_id,
            account_id=account_id,
            chat_id=chat_id,
            source_message_id=source_message_id,
        )
        self.jobs[job.job_id] = job
        await self.queue.put(job.job_id)
        print(
            f"[check_jobs] queued type=account_check job_id={job.job_id} "
            f"user_id={user_id} account_id={account_id}"
        )
        return job

    async def _worker_loop(self, worker_no: int) -> None:
        print(f"[check_jobs] worker_started worker={worker_no}")
        try:
            while True:
                job_id = await self.queue.get()
                job = self.jobs.get(job_id)
                if job is None:
                    self.queue.task_done()
                    continue

                try:
                    if job.job_type == "proxy_check":
                        await self._run_proxy_check(worker_no, job)
                    elif job.job_type == "account_check":
                        await self._run_account_check(worker_no, job)
                except Exception as exc:
                    job.status = "failed"
                    job.error = str(exc)
                    job.finished_at = time.time()
                    await self._notify_text(
                        chat_id=job.chat_id,
                        text=f"Ошибка проверки\n{exc}",
                        reply_to_message_id=job.source_message_id,
                    )
                    print(
                        f"[check_jobs] worker_crash worker={worker_no} "
                        f"job_id={job.job_id} error={exc}"
                    )
                finally:
                    self.queue.task_done()
        except asyncio.CancelledError:
            print(f"[check_jobs] worker_stopped worker={worker_no}")
            raise

    async def _run_proxy_check(self, worker_no: int, job: CheckJob) -> None:
        proxy_id = int(job.proxy_id or 0)
        if proxy_id <= 0:
            raise RuntimeError("Некорректный proxy_id")

        async with self.get_proxy_lock(proxy_id):
            job.status = "running"
            job.started_at = time.time()

            proxy = get_proxy_by_id(job.user_id, proxy_id)
            if not proxy:
                await self._notify_text(
                    chat_id=job.chat_id,
                    text="Прокси не найден.",
                    reply_to_message_id=job.source_message_id,
                )
                job.status = "failed"
                job.finished_at = time.time()
                return

            result = await check_proxy_alive(
                proxy_text=proxy["proxy_text"],
                headless=True,
            )

            update_proxy_last_check(job.user_id, proxy_id)
            result_status = _normalize_proxy_status_for_db(result.get("status"))
            update_proxy_status(job.user_id, proxy_id, result_status)

            updated_proxy = get_proxy_by_id(job.user_id, proxy_id) or proxy
            ui_status = _humanize_proxy_status(updated_proxy.get("status"))

            raw_error = (result.get("error") or "").strip()
            human_error = None
            if raw_error:
                lower_error = raw_error.lower()
                if "only socks5" in lower_error or "поддерживается только socks5" in lower_error:
                    human_error = "Поддерживается только SOCKS5."
                elif "timeout" in lower_error:
                    human_error = "Прокси не ответил вовремя."
                elif "407" in lower_error or "proxy authentication" in lower_error or "auth" in lower_error:
                    human_error = "Неверный логин или пароль прокси."
                elif "403" in lower_error:
                    human_error = "Доступ через этот прокси был отклонён."
                elif "tunnel" in lower_error:
                    human_error = "Не удалось установить соединение через прокси."
                elif "dns" in lower_error or "name resolution" in lower_error:
                    human_error = "Не удалось определить адрес прокси."
                elif "connection refused" in lower_error:
                    human_error = "Прокси отклонил подключение."
                elif "connection reset" in lower_error:
                    human_error = "Соединение через прокси было сброшено."
                elif "network" in lower_error:
                    human_error = "Ошибка сети при проверке прокси."
                else:
                    human_error = "Прокси не прошёл проверку."

            text_lines = [
                "🔎 Проверка прокси завершена",
                "",
                f"Прокси: {_proxy_short(updated_proxy.get('proxy_text', ''), max_len=70)}",
                f"Статус: {ui_status}",
            ]
            if human_error and ui_status != "живой":
                text_lines.extend(["", f"Причина: {human_error}"])

            await self._notify_or_edit(
                chat_id=job.chat_id,
                text="\n".join(text_lines),
                reply_to_message_id=job.source_message_id,
                edit_message_id=job.source_message_id,
                reply_markup=_build_proxy_result_keyboard(proxy_id),
            )

            job.result = result
            job.status = "done"
            job.finished_at = time.time()
            print(
                f"[check_jobs] worker_done worker={worker_no} "
                f"type=proxy_check job_id={job.job_id} proxy_id={proxy_id} "
                f"status={result.get('status')}"
            )

    async def _run_account_check(self, worker_no: int, job: CheckJob) -> None:
        account_id = int(job.account_id or 0)
        if account_id <= 0:
            raise RuntimeError("Некорректный account_id")

        async with self.get_account_lock(account_id):
            job.status = "running"
            job.started_at = time.time()

            account = get_account_by_id(job.user_id, account_id)
            if not account:
                await self._notify_text(
                    chat_id=job.chat_id,
                    text="Аккаунт не найден.",
                    reply_to_message_id=job.source_message_id,
                )
                job.status = "failed"
                job.finished_at = time.time()
                return

            proxy_id = account.get("proxy_id")
            if not proxy_id:
                update_account_status(job.user_id, account_id, "missing_proxy")
                update_account_last_check(job.user_id, account_id)
                await self._notify_or_edit(
                    chat_id=job.chat_id,
                    text="❌ У аккаунта не привязан прокси.\n\nСначала привяжи 1 прокси к этому аккаунту.",
                    reply_to_message_id=job.source_message_id,
                    edit_message_id=job.source_message_id,
                    reply_markup=_build_account_result_keyboard(account_id),
                )
                job.status = "failed"
                job.finished_at = time.time()
                return

            proxy = get_proxy_by_id(job.user_id, proxy_id)
            if not proxy:
                update_account_status(job.user_id, account_id, "proxy_not_found")
                update_account_last_check(job.user_id, account_id)
                await self._notify_or_edit(
                    chat_id=job.chat_id,
                    text="❌ Привязанный прокси не найден.\n\nПривяжи другой прокси.",
                    reply_to_message_id=job.source_message_id,
                    edit_message_id=job.source_message_id,
                    reply_markup=_build_account_result_keyboard(account_id),
                )
                job.status = "failed"
                job.finished_at = time.time()
                return

            cookies_json = account.get("cookies_json")
            proxy_text = proxy.get("proxy_text")
            if not cookies_json:
                update_account_status(job.user_id, account_id, "missing_cookies")
                update_account_last_check(job.user_id, account_id)
                await self._notify_or_edit(
                    chat_id=job.chat_id,
                    text="❌ У аккаунта отсутствуют cookies_json.",
                    reply_to_message_id=job.source_message_id,
                    edit_message_id=job.source_message_id,
                    reply_markup=_build_account_result_keyboard(account_id),
                )
                job.status = "failed"
                job.finished_at = time.time()
                return

            market_code = ((account.get("market") or "olx_pt").strip().lower()) or "olx_pt"

            result = await check_account_alive(
                cookies_json=cookies_json,
                proxy_text=proxy_text,
                headless=True,
                user_id=job.user_id,
                account_id=account_id,
                olx_profile_name=account.get("olx_profile_name"),
                market_code=market_code,
            )

            profile_name = (result.get("profile_name") or "").strip()
            if profile_name:
                update_account_profile_name(job.user_id, account_id, profile_name)

            result_status = _normalize_account_status_for_db(result.get("status"))
            update_account_status(job.user_id, account_id, result_status)
            update_account_last_check(job.user_id, account_id)
            update_proxy_last_check(job.user_id, proxy["id"])

            normalized_proxy_status = _normalize_proxy_status_from_account_check(result_status)
            update_proxy_status(job.user_id, proxy["id"], normalized_proxy_status)

            updated_account = get_account_by_id(job.user_id, account_id) or account

            text = _build_account_check_result_text(updated_account, proxy, result)
            await self._notify_or_edit(
                chat_id=job.chat_id,
                text=text,
                reply_to_message_id=job.source_message_id,
                edit_message_id=job.source_message_id,
                reply_markup=_build_account_result_keyboard(account_id),
            )

            job.result = result
            job.status = "done"
            job.finished_at = time.time()
            print(
                f"[check_jobs] worker_done worker={worker_no} "
                f"type=account_check job_id={job.job_id} account_id={account_id} "
                f"status={result.get('status')}"
            )

    async def _notify_or_edit(
        self,
        *,
        chat_id: int,
        text: str,
        reply_to_message_id: int | None,
        edit_message_id: int | None,
        reply_markup=None,
    ) -> None:
        if edit_message_id:
            try:
                await self.application.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=edit_message_id,
                    text=text,
                    reply_markup=reply_markup,
                )
                return
            except BadRequest as exc:
                lowered = str(exc).lower()
                if "message is not modified" in lowered:
                    try:
                        await self.application.bot.edit_message_reply_markup(
                            chat_id=chat_id,
                            message_id=edit_message_id,
                            reply_markup=reply_markup,
                        )
                        return
                    except Exception:
                        pass
                fallback_markers = [
                    "message to edit not found",
                    "message can't be edited",
                    "there is no text in the message to edit",
                ]
                if not any(marker in lowered for marker in fallback_markers):
                    raise

        await self._notify_text(
            chat_id=chat_id,
            text=text,
            reply_to_message_id=reply_to_message_id,
            reply_markup=reply_markup,
        )

    async def _notify_text(
        self,
        *,
        chat_id: int,
        text: str,
        reply_to_message_id: int | None,
        reply_markup=None,
    ) -> None:
        await self.application.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            reply_to_message_id=reply_to_message_id,
        )


async def ensure_check_jobs_started(
    application: Application,
    worker_count: int = 2,
) -> "CheckJobsManager":
    manager = application.bot_data.get(BOT_DATA_KEY)
    if manager is None:
        manager = CheckJobsManager(application=application, worker_count=worker_count)
        application.bot_data[BOT_DATA_KEY] = manager
    await manager.start()
    return manager


def get_check_jobs_manager(application: Application) -> CheckJobsManager | None:
    value = application.bot_data.get(BOT_DATA_KEY)
    if isinstance(value, CheckJobsManager):
        return value
    return None