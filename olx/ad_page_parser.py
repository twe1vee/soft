from __future__ import annotations

import re
from typing import Any

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from olx.message_sender_page import is_cloudfront_block_page

DEFAULT_AD_PARSE_MARKET = "olx_pt"

PT_READY_SELECTORS = [
    '[data-testid="main"]',
    '[data-testid="offer_title"]',
    '[data-testid="ad-price-container"]',
    '[data-testid="image-galery-container"]',
]

PT_TITLE_SELECTORS = [
    '[data-testid="offer_title"] h4',
    '[data-testid="offer_title"]',
]

PT_PRICE_SELECTORS = [
    '[data-testid="ad-price-container"] h3',
    '[data-testid="ad-price-container"]',
    '[data-testid="prices-wrapper"] h3',
]

PT_IMAGE_SELECTORS = [
    'img[data-testid="swiper-image"]',
    'img[data-testid="swiper-image-lazy"]',
    '[data-testid="image-galery-container"] img',
]

COOKIE_BANNER_SELECTORS = [
    'button#onetrust-accept-btn-handler',
    'button:has-text("Aceitar")',
    'button:has-text("Aceitar tudo")',
    'button:has-text("Accept")',
]


def _normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


async def _safe_inner_text(page, selector: str) -> str:
    try:
        locator = page.locator(selector).first
        if await locator.count() == 0:
            return ""
        return _normalize_text(await locator.inner_text(timeout=2500))
    except Exception:
        return ""


async def _safe_attr(page, selector: str, attr_name: str) -> str | None:
    try:
        locator = page.locator(selector).first
        if await locator.count() == 0:
            return None
        value = await locator.get_attribute(attr_name, timeout=2500)
        return (value or "").strip() or None
    except Exception:
        return None


async def _dismiss_cookie_banner_if_present(page) -> None:
    for selector in COOKIE_BANNER_SELECTORS:
        try:
            locator = page.locator(selector).first
            if await locator.count() == 0:
                continue
            if not await locator.is_visible():
                continue
            try:
                await locator.click(timeout=2000)
            except Exception:
                await locator.click(force=True, timeout=2000)
            await page.wait_for_timeout(500)
            return
        except Exception:
            continue


async def _wait_for_ready(page, market_code: str = DEFAULT_AD_PARSE_MARKET) -> bool:
    selectors = PT_READY_SELECTORS if market_code == "olx_pt" else PT_READY_SELECTORS

    for _ in range(16):
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible():
                    return True
            except Exception:
                continue
        await page.wait_for_timeout(500)

    return False


def _normalize_amount_text(raw_price: str) -> str:
    text = _normalize_text(raw_price)
    if not text:
        return ""

    text = text.replace("€", " EUR")
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def parse_ad_page(
    *,
    ad_url: str,
    headless: bool = True,
    market_code: str = DEFAULT_AD_PARSE_MARKET,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "status": "failed",
        "error": None,
        "final_url": None,
        "page_title": None,
        "title": None,
        "amount": None,
        "image": None,
        "market_code": market_code,
        "browser_engine": "playwright_public",
    }

    if not (ad_url or "").strip():
        result["status"] = "invalid_input"
        result["error"] = "Пустой ad_url"
        return result

    playwright = None
    browser = None
    context = None
    page = None

    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto(ad_url, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(1500)

        result["final_url"] = page.url
        try:
            result["page_title"] = await page.title()
        except Exception:
            pass

        if await is_cloudfront_block_page(page):
            result["status"] = "cloudfront_blocked"
            result["error"] = "OLX/CloudFront заблокировал страницу объявления"
            return result

        await _dismiss_cookie_banner_if_present(page)

        ready = await _wait_for_ready(page, market_code=market_code)
        if not ready:
            result["status"] = "parse_not_ready"
            result["error"] = "Страница объявления не прогрузилась до нужных блоков"
            return result

        title = ""
        for selector in PT_TITLE_SELECTORS:
            title = await _safe_inner_text(page, selector)
            if title:
                break

        amount = ""
        for selector in PT_PRICE_SELECTORS:
            amount = await _safe_inner_text(page, selector)
            if amount:
                break

        image = None
        for selector in PT_IMAGE_SELECTORS:
            image = await _safe_attr(page, selector, "src")
            if image:
                break

        if not title:
            result["status"] = "title_not_found"
            result["error"] = "Не найден заголовок объявления"
            return result

        if not amount:
            result["status"] = "price_not_found"
            result["error"] = "Не найдена цена объявления"
            return result

        result["title"] = title
        result["amount"] = _normalize_amount_text(amount)
        result["image"] = image
        result["ok"] = True
        result["status"] = "ok"
        return result

    except PlaywrightTimeoutError as exc:
        result["status"] = "timeout"
        result["error"] = str(exc)
        return result
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        return result
    finally:
        try:
            if page is not None and not page.is_closed():
                await page.close()
        except Exception:
            pass

        try:
            if context is not None:
                await context.close()
        except Exception:
            pass

        try:
            if browser is not None:
                await browser.close()
        except Exception:
            pass

        try:
            if playwright is not None:
                await playwright.stop()
        except Exception:
            pass