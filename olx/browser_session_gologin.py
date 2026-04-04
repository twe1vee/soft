from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from playwright.async_api import Browser, BrowserContext, async_playwright

from db import clear_account_gologin_profile
from olx.profile_manager_gologin import (
    build_gologin_client,
    ensure_gologin_profile,
)
from olx.runtime_rate_limit import wait_gologin_stop_slot


def _to_cdp_endpoint(debugger_address: str) -> str:
    raw = (debugger_address or "").strip()
    if not raw:
        raise RuntimeError("GoLogin вернул пустой debugger address")

    if raw.startswith(("http://", "https://", "ws://", "wss://")):
        return raw

    return f"http://{raw}"


def _is_profile_not_found_error(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return (
        "profile deleted or not found" in text
        or "profile not found" in text
        or "not found" in text
        or "404" in text
    )


async def _prepare_runtime(
    *,
    cookies_json: str,
    proxy_text: str,
    headless: bool,
    user_id: int | None,
    account_id: int | None,
    olx_profile_name: str | None,
) -> tuple[dict, object]:
    runtime = await asyncio.to_thread(
        ensure_gologin_profile,
        cookies_json=cookies_json,
        proxy_text=proxy_text,
        user_id=user_id,
        account_id=account_id,
        olx_profile_name=olx_profile_name,
    )

    profile_id = runtime["gologin_profile_id"]
    gl = build_gologin_client(
        profile_id=profile_id,
        headless=headless,
    )
    return runtime, gl


@asynccontextmanager
async def open_gologin_browser_context(
    cookies_json: str,
    proxy_text: str,
    *,
    headless: bool = True,
    user_id: int | None = None,
    account_id: int | None = None,
    olx_profile_name: str | None = None,
) -> AsyncIterator[tuple[Browser, BrowserContext, dict]]:
    runtime, gl = await _prepare_runtime(
        cookies_json=cookies_json,
        proxy_text=proxy_text,
        headless=headless,
        user_id=user_id,
        account_id=account_id,
        olx_profile_name=olx_profile_name,
    )

    playwright = None
    browser: Browser | None = None
    context: BrowserContext | None = None
    created_context = False
    debugger_address: str | None = None

    try:
        try:
            debugger_address = await asyncio.to_thread(gl.start)
        except Exception as exc:
            if not _is_profile_not_found_error(exc):
                raise

            if user_id is None or account_id is None:
                raise

            print(
                f"[gologin] stale profile on start for account_id={account_id}, "
                f"clearing profile id and recreating"
            )

            await asyncio.to_thread(clear_account_gologin_profile, user_id, account_id)

            runtime, gl = await _prepare_runtime(
                cookies_json=cookies_json,
                proxy_text=proxy_text,
                headless=headless,
                user_id=user_id,
                account_id=account_id,
                olx_profile_name=olx_profile_name,
            )

            debugger_address = await asyncio.to_thread(gl.start)

        runtime["debugger_address"] = debugger_address

        playwright = await async_playwright().start()
        browser = await playwright.chromium.connect_over_cdp(
            _to_cdp_endpoint(debugger_address)
        )

        if browser.contexts:
            context = browser.contexts[0]
        else:
            context = await browser.new_context()
            created_context = True

        yield browser, context, runtime

    finally:
        try:
            if created_context and context:
                await context.close()
        except Exception:
            pass

        try:
            if browser:
                await browser.close()
        except Exception:
            pass

        try:
            if playwright:
                await playwright.stop()
        except Exception:
            pass

        try:
            await wait_gologin_stop_slot()
            await asyncio.to_thread(gl.stop)
        except Exception:
            pass