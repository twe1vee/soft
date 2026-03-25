from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from playwright.async_api import Browser, BrowserContext, Page

from olx.browser_session_gologin import open_gologin_browser_context


PT_HOME_URL = "https://www.olx.pt/"
PT_ACCOUNT_URL = "https://www.olx.pt/myaccount/"


@asynccontextmanager
async def open_olx_browser_context(
    cookies_json: str,
    proxy_text: str,
    *,
    headless: bool = True,
    user_id: int | None = None,
    account_id: int | None = None,
    olx_profile_name: str | None = None,
) -> AsyncIterator[tuple[Browser, BrowserContext, dict]]:
    async with open_gologin_browser_context(
        cookies_json=cookies_json,
        proxy_text=proxy_text,
        headless=headless,
        user_id=user_id,
        account_id=account_id,
        olx_profile_name=olx_profile_name,
    ) as session:
        yield session


async def open_olx_page(
    context: BrowserContext,
    url: str,
    *,
    timeout: int = 90000,
    wait_after_ms: int = 3000,
) -> Page:
    page = await context.new_page()
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    if wait_after_ms > 0:
        await page.wait_for_timeout(wait_after_ms)
    return page


async def dismiss_cookie_banner_if_present(page: Page) -> None:
    candidates = [
        page.get_by_role("button", name="Aceitar"),
        page.get_by_role("button", name="Aceitar tudo"),
        page.get_by_role("button", name="Accept"),
        page.locator("button#onetrust-accept-btn-handler"),
    ]

    for locator in candidates:
        try:
            if await locator.count() > 0 and await locator.first.is_visible():
                await locator.first.click(timeout=3000)
                await page.wait_for_timeout(1000)
                return
        except Exception:
            continue


async def get_current_context_cookies(context: BrowserContext):
    return await context.cookies()