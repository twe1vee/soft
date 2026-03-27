from __future__ import annotations
from db.accounts import touch_account_last_used
import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import BrowserContext, Page

from olx.browser_session import open_olx_browser_context

ACCOUNT_RUNTIME_TTL_SECONDS = 600


def _runtime_debug(message: str) -> None:
    print(f"[account_runtime] {message}")


@dataclass
class AccountRuntimeEntry:
    user_id: int | None
    account_id: int
    proxy_text: str
    cookies_json: str
    headless: bool
    olx_profile_name: str | None
    manager: Any | None = None
    browser: Any | None = None
    context: BrowserContext | None = None
    runtime: dict[str, Any] = field(default_factory=dict)
    created_monotonic: float = field(default_factory=time.monotonic)
    last_used_monotonic: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    opening_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    busy_reason: str | None = None
    closing: bool = False
    deleted: bool = False

    def touch(self) -> None:
        self.last_used_monotonic = time.monotonic()
        try:
            touch_account_last_used(self.account_id)
        except Exception as exc:
            _runtime_debug(f"touch_db_failed account_id={self.account_id} error={exc}")
        runtime = self.runtime or {}
        _runtime_debug(
            f"touch account_id={self.account_id} "
            f"engine={runtime.get('browser_engine')} "
            f"profile_id={runtime.get('gologin_profile_id')} "
            f"busy_reason={self.busy_reason}"
        )

    def is_expired(self, ttl_seconds: int = ACCOUNT_RUNTIME_TTL_SECONDS) -> bool:
        return (time.monotonic() - self.last_used_monotonic) > ttl_seconds

    def is_ready(self) -> bool:
        return self.context is not None and not self.closing and not self.deleted


_RUNTIME_BY_ACCOUNT_ID: dict[int, AccountRuntimeEntry] = {}
_RUNTIME_REGISTRY_LOCK = asyncio.Lock()


async def get_account_runtime(
    *,
    user_id: int | None,
    account_id: int,
    cookies_json: str,
    proxy_text: str,
    headless: bool = True,
    olx_profile_name: str | None = None,
) -> AccountRuntimeEntry:
    if not account_id or int(account_id) <= 0:
        raise ValueError(f"invalid account_id for runtime: {account_id}")

    account_id = int(account_id)

    async with _RUNTIME_REGISTRY_LOCK:
        entry = _RUNTIME_BY_ACCOUNT_ID.get(account_id)
        if entry is None:
            entry = AccountRuntimeEntry(
                user_id=user_id,
                account_id=account_id,
                proxy_text=proxy_text,
                cookies_json=cookies_json,
                headless=headless,
                olx_profile_name=olx_profile_name,
            )
            _RUNTIME_BY_ACCOUNT_ID[account_id] = entry
            _runtime_debug(f"registry_created account_id={account_id}")

    async with entry.opening_lock:
        if entry.deleted:
            raise RuntimeError(f"account runtime deleted: {account_id}")

        if entry.is_ready():
            runtime = entry.runtime or {}
            _runtime_debug(
                f"reuse account_id={account_id} "
                f"engine={runtime.get('browser_engine')} "
                f"profile_id={runtime.get('gologin_profile_id')}"
            )
            entry.touch()
            return entry

        if entry.manager is not None:
            _runtime_debug(f"stale_before_reopen account_id={account_id}")
            await _close_entry(entry, reason="stale_before_reopen", remove_from_registry=False)

        manager = open_olx_browser_context(
            cookies_json=cookies_json,
            proxy_text=proxy_text,
            headless=headless,
            user_id=user_id,
            account_id=account_id,
            olx_profile_name=olx_profile_name,
        )

        browser, context, runtime = await manager.__aenter__()

        entry.manager = manager
        entry.browser = browser
        entry.context = context
        entry.runtime = runtime or {}
        entry.cookies_json = cookies_json
        entry.proxy_text = proxy_text
        entry.headless = headless
        entry.user_id = user_id
        entry.olx_profile_name = olx_profile_name
        entry.created_monotonic = time.monotonic()
        entry.closing = False

        _runtime_debug(
            f"created account_id={account_id} "
            f"engine={entry.runtime.get('browser_engine')} "
            f"profile_id={entry.runtime.get('gologin_profile_id')} "
            f"profile_name={entry.runtime.get('gologin_profile_name')}"
        )

        entry.touch()
        return entry


async def open_account_runtime_page(
    *,
    user_id: int | None,
    account_id: int,
    cookies_json: str,
    proxy_text: str,
    url: str | None = None,
    headless: bool = True,
    olx_profile_name: str | None = None,
    timeout: int = 90000,
    wait_after_ms: int = 3000,
    busy_reason: str | None = None,
) -> tuple[Page, AccountRuntimeEntry]:
    if not account_id or int(account_id) <= 0:
        raise ValueError(f"invalid account_id for runtime page: {account_id}")

    account_id = int(account_id)

    _runtime_debug(
        f"open_page_request account_id={account_id} "
        f"user_id={user_id} busy_reason={busy_reason} url={url}"
    )

    entry = await get_account_runtime(
        user_id=user_id,
        account_id=account_id,
        cookies_json=cookies_json,
        proxy_text=proxy_text,
        headless=headless,
        olx_profile_name=olx_profile_name,
    )

    async with entry.lock:
        if entry.deleted or entry.closing or entry.context is None:
            raise RuntimeError(f"account runtime unavailable: {account_id}")

        entry.busy_reason = busy_reason
        entry.touch()

        page = await entry.context.new_page()
        try:
            if url:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            if wait_after_ms > 0:
                await page.wait_for_timeout(wait_after_ms)

            entry.touch()

            runtime = entry.runtime or {}
            _runtime_debug(
                f"page_opened account_id={account_id} "
                f"engine={runtime.get('browser_engine')} "
                f"profile_id={runtime.get('gologin_profile_id')} "
                f"url={page.url} "
                f"busy_reason={busy_reason}"
            )

            return page, entry
        except Exception:
            with contextlib.suppress(Exception):
                await page.close()
            entry.busy_reason = None
            entry.touch()
            raise


async def close_runtime_page(entry: AccountRuntimeEntry, page: Page | None) -> None:
    try:
        if page is not None and not page.is_closed():
            await page.close()
    except Exception as exc:
        _runtime_debug(f"page_close_failed account_id={entry.account_id} error={exc}")
    finally:
        runtime = entry.runtime or {}
        _runtime_debug(
            f"page_closed account_id={entry.account_id} "
            f"engine={runtime.get('browser_engine')} "
            f"profile_id={runtime.get('gologin_profile_id')}"
        )
        entry.busy_reason = None
        entry.touch()


async def close_account_runtime(account_id: int, *, reason: str = "manual_close") -> bool:
    async with _RUNTIME_REGISTRY_LOCK:
        entry = _RUNTIME_BY_ACCOUNT_ID.get(account_id)
        if entry is None:
            return False

    await _close_entry(entry, reason=reason, remove_from_registry=True)
    return True


async def mark_account_runtime_deleted(account_id: int) -> None:
    async with _RUNTIME_REGISTRY_LOCK:
        entry = _RUNTIME_BY_ACCOUNT_ID.get(account_id)
        if entry is not None:
            entry.deleted = True
            entry.closing = True
            _runtime_debug(f"marked_deleted account_id={account_id}")


async def close_idle_account_runtimes(
    *,
    idle_seconds: int = ACCOUNT_RUNTIME_TTL_SECONDS,
) -> list[int]:
    async with _RUNTIME_REGISTRY_LOCK:
        candidates = list(_RUNTIME_BY_ACCOUNT_ID.items())

    closed_account_ids: list[int] = []

    for account_id, entry in candidates:
        if entry.deleted:
            _runtime_debug(f"deleted_close account_id={account_id}")
            await _close_entry(entry, reason="deleted", remove_from_registry=True)
            closed_account_ids.append(account_id)
            continue

        if entry.lock.locked():
            _runtime_debug(f"skip_locked account_id={account_id} busy_reason={entry.busy_reason}")
            continue

        if entry.is_expired(idle_seconds):
            runtime = entry.runtime or {}
            _runtime_debug(
                f"idle_close account_id={account_id} "
                f"engine={runtime.get('browser_engine')} "
                f"profile_id={runtime.get('gologin_profile_id')} "
                f"idle_seconds={int(time.monotonic() - entry.last_used_monotonic)}"
            )
            await _close_entry(entry, reason="idle_ttl", remove_from_registry=True)
            _runtime_debug(f"idle_closed account_id={account_id}")
            closed_account_ids.append(account_id)

    return closed_account_ids


async def get_runtime_snapshot() -> list[dict[str, Any]]:
    async with _RUNTIME_REGISTRY_LOCK:
        entries = list(_RUNTIME_BY_ACCOUNT_ID.values())

    snapshot: list[dict[str, Any]] = []
    now = time.monotonic()

    for entry in entries:
        snapshot.append(
            {
                "account_id": entry.account_id,
                "user_id": entry.user_id,
                "busy_reason": entry.busy_reason,
                "closing": entry.closing,
                "deleted": entry.deleted,
                "ready": entry.is_ready(),
                "idle_seconds": round(now - entry.last_used_monotonic, 2),
                "gologin_profile_id": entry.runtime.get("gologin_profile_id"),
                "gologin_profile_name": entry.runtime.get("gologin_profile_name"),
                "debugger_address": entry.runtime.get("debugger_address"),
            }
        )

    return snapshot


async def _close_entry(
    entry: AccountRuntimeEntry,
    *,
    reason: str,
    remove_from_registry: bool,
) -> None:
    async with entry.opening_lock:
        if entry.closing and entry.manager is None and entry.context is None:
            if remove_from_registry:
                async with _RUNTIME_REGISTRY_LOCK:
                    existing = _RUNTIME_BY_ACCOUNT_ID.get(entry.account_id)
                    if existing is entry:
                        _RUNTIME_BY_ACCOUNT_ID.pop(entry.account_id, None)
            return

        entry.closing = True
        entry.busy_reason = f"closing:{reason}"

        _runtime_debug(
            f"closing account_id={entry.account_id} "
            f"reason={reason} "
            f"profile_id={entry.runtime.get('gologin_profile_id')}"
        )

        try:
            if entry.context is not None:
                pages = list(entry.context.pages)
                for page in pages:
                    with contextlib.suppress(Exception):
                        if not page.is_closed():
                            await page.close()
        except Exception as exc:
            _runtime_debug(f"close_pages_failed account_id={entry.account_id} error={exc}")

        try:
            if entry.manager is not None:
                await entry.manager.__aexit__(None, None, None)
        except Exception as exc:
            _runtime_debug(f"manager_exit_failed account_id={entry.account_id} error={exc}")

        entry.manager = None
        entry.browser = None
        entry.context = None
        entry.runtime = {}
        entry.busy_reason = None
        entry.closing = False

        if remove_from_registry:
            async with _RUNTIME_REGISTRY_LOCK:
                existing = _RUNTIME_BY_ACCOUNT_ID.get(entry.account_id)
                if existing is entry:
                    _RUNTIME_BY_ACCOUNT_ID.pop(entry.account_id, None)

        _runtime_debug(
            f"closed account_id={entry.account_id} "
            f"reason={reason} remove_from_registry={remove_from_registry}"
        )