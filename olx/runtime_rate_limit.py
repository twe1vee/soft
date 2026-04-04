from __future__ import annotations

import asyncio
import threading
import time
from collections import defaultdict


GLOBAL_RUNTIME_START_MIN_INTERVAL_SECONDS = 1.5
GLOBAL_GOLOGIN_STOP_MIN_INTERVAL_SECONDS = 0.75
GLOBAL_GOLOGIN_CREATE_MIN_INTERVAL_SECONDS = 1.25
GLOBAL_GOLOGIN_DELETE_MIN_INTERVAL_SECONDS = 1.25

PER_ACCOUNT_RUNTIME_REOPEN_MIN_INTERVAL_SECONDS = 8.0
PER_ACCOUNT_OPEN_FAILURE_COOLDOWN_SECONDS = 20.0


_global_start_lock = asyncio.Lock()
_global_stop_lock = asyncio.Lock()
_global_create_lock = asyncio.Lock()
_global_delete_lock = asyncio.Lock()

_global_create_sync_lock = threading.Lock()
_global_delete_sync_lock = threading.Lock()

_last_global_runtime_start_at = 0.0
_last_global_gologin_stop_at = 0.0
_last_global_gologin_create_at = 0.0
_last_global_gologin_delete_at = 0.0

_last_global_gologin_create_sync_at = 0.0
_last_global_gologin_delete_sync_at = 0.0

_last_account_open_started_at: dict[int, float] = defaultdict(float)
_account_open_failure_until: dict[int, float] = defaultdict(float)


def _now() -> float:
    return time.monotonic()


async def _sleep_remaining(remaining: float) -> None:
    if remaining > 0:
        await asyncio.sleep(remaining)


def _sleep_remaining_sync(remaining: float) -> None:
    if remaining > 0:
        time.sleep(remaining)


async def wait_runtime_start_slot(account_id: int) -> None:
    global _last_global_runtime_start_at

    account_id = int(account_id)
    now = _now()

    blocked_until = _account_open_failure_until.get(account_id, 0.0)
    if blocked_until > now:
        await _sleep_remaining(blocked_until - now)

    last_account_open = _last_account_open_started_at.get(account_id, 0.0)
    account_remaining = PER_ACCOUNT_RUNTIME_REOPEN_MIN_INTERVAL_SECONDS - (
        now - last_account_open
    )
    if account_remaining > 0:
        await _sleep_remaining(account_remaining)

    async with _global_start_lock:
        now = _now()
        global_remaining = GLOBAL_RUNTIME_START_MIN_INTERVAL_SECONDS - (
            now - _last_global_runtime_start_at
        )
        if global_remaining > 0:
            await _sleep_remaining(global_remaining)

        _last_global_runtime_start_at = _now()
        _last_account_open_started_at[account_id] = _last_global_runtime_start_at


def mark_runtime_open_failed(
    account_id: int,
    *,
    cooldown_seconds: float = PER_ACCOUNT_OPEN_FAILURE_COOLDOWN_SECONDS,
) -> None:
    account_id = int(account_id)
    _account_open_failure_until[account_id] = max(
        _account_open_failure_until.get(account_id, 0.0),
        _now() + max(0.0, float(cooldown_seconds)),
    )


def clear_runtime_open_failure(account_id: int) -> None:
    account_id = int(account_id)
    if account_id in _account_open_failure_until:
        _account_open_failure_until.pop(account_id, None)


async def wait_gologin_stop_slot() -> None:
    global _last_global_gologin_stop_at

    async with _global_stop_lock:
        now = _now()
        remaining = GLOBAL_GOLOGIN_STOP_MIN_INTERVAL_SECONDS - (
            now - _last_global_gologin_stop_at
        )
        if remaining > 0:
            await _sleep_remaining(remaining)

        _last_global_gologin_stop_at = _now()


async def wait_gologin_create_slot() -> None:
    global _last_global_gologin_create_at

    async with _global_create_lock:
        now = _now()
        remaining = GLOBAL_GOLOGIN_CREATE_MIN_INTERVAL_SECONDS - (
            now - _last_global_gologin_create_at
        )
        if remaining > 0:
            await _sleep_remaining(remaining)

        _last_global_gologin_create_at = _now()


async def wait_gologin_delete_slot() -> None:
    global _last_global_gologin_delete_at

    async with _global_delete_lock:
        now = _now()
        remaining = GLOBAL_GOLOGIN_DELETE_MIN_INTERVAL_SECONDS - (
            now - _last_global_gologin_delete_at
        )
        if remaining > 0:
            await _sleep_remaining(remaining)

        _last_global_gologin_delete_at = _now()


def wait_gologin_create_slot_sync() -> None:
    global _last_global_gologin_create_sync_at

    with _global_create_sync_lock:
        now = _now()
        remaining = GLOBAL_GOLOGIN_CREATE_MIN_INTERVAL_SECONDS - (
            now - _last_global_gologin_create_sync_at
        )
        if remaining > 0:
            _sleep_remaining_sync(remaining)

        _last_global_gologin_create_sync_at = _now()


def wait_gologin_delete_slot_sync() -> None:
    global _last_global_gologin_delete_sync_at

    with _global_delete_sync_lock:
        now = _now()
        remaining = GLOBAL_GOLOGIN_DELETE_MIN_INTERVAL_SECONDS - (
            now - _last_global_gologin_delete_sync_at
        )
        if remaining > 0:
            _sleep_remaining_sync(remaining)

        _last_global_gologin_delete_sync_at = _now()


def get_runtime_rate_limit_snapshot() -> dict:
    now = _now()
    return {
        "global_start_min_interval_seconds": GLOBAL_RUNTIME_START_MIN_INTERVAL_SECONDS,
        "global_stop_min_interval_seconds": GLOBAL_GOLOGIN_STOP_MIN_INTERVAL_SECONDS,
        "global_create_min_interval_seconds": GLOBAL_GOLOGIN_CREATE_MIN_INTERVAL_SECONDS,
        "global_delete_min_interval_seconds": GLOBAL_GOLOGIN_DELETE_MIN_INTERVAL_SECONDS,
        "per_account_reopen_min_interval_seconds": PER_ACCOUNT_RUNTIME_REOPEN_MIN_INTERVAL_SECONDS,
        "per_account_failure_cooldown_seconds": PER_ACCOUNT_OPEN_FAILURE_COOLDOWN_SECONDS,
        "accounts_with_failure_cooldown": {
            str(account_id): round(max(0.0, until - now), 2)
            for account_id, until in _account_open_failure_until.items()
            if until > now
        },
    }