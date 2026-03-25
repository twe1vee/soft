from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from playwright.async_api import Browser, BrowserContext, async_playwright

from olx.profile_manager_gologin import (
    build_gologin_client,
    ensure_gologin_profile,
)


def _to_cdp_endpoint(debugger_address: str) -> str:
    raw = (debugger_address or "").strip()
    if not raw:
        raise RuntimeError("GoLogin вернул пустой debugger address")

    if raw.startswith(("http://", "https://", "ws://", "wss://")):
        return raw

    return f"http://{raw}"


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

    playwright = None
    browser: Browser | None = None
    context: BrowserContext | None = None
    created_context = False
    debugger_address: str | None = None

    try:
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
            await asyncio.to_thread(gl.stop)
        except Exception:
            pass