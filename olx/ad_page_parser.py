from __future__ import annotations

import re
from typing import Any

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from olx.account_runtime import close_runtime_page, open_account_runtime_page
from olx.browser_session import dismiss_cookie_banner_if_present
from olx.markets.helpers import extract_url_domain, is_market_domain
from olx.message_sender_page import handle_olx_soft_error_page, is_cloudfront_block_page

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


async def _wait_for_ready(page, market_code: str = DEFAULT_AD_PARSE_MARKET) -> bool:
    selectors = PT_READY_SELECTORS if market_code == "olx_pt" else PT_READY_SELECTORS

    for _ in range(12):
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

    # Для RedScript можно оставить человекочитаемый формат, например "15 EUR"
    text = text.replace("€", " EUR")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _detect_market_mismatch(ad_url: str, market_code: str) -> str | None:
    domain = extract_url_domain(ad_url)
    if not domain:
        return None

    if is_market_domain(domain, market_code):
        return None

    return (
        f"Ссылка объявления относится к другому рынку: {domain}. "
        f"Парсер запущен для рынка {market_code}."
    )


async def parse_ad_page(
    *,
    cookies_json: str,
    proxy_text: str,
    ad_url: str,
    headless: bool = True,
    user_id: int | None = None,
    account_id: int | None = None,
    olx_profile_name: str | None = None,
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
        "browser_engine": "gologin",
        "gologin_profile_id": None,
        "gologin_profile_name": None,
        "debugger_address": None,
    }

    if not (ad_url or "").strip():
        result["status"] = "invalid_input"
        result["error"] = "Пустой ad_url"
        return result

    market_mismatch_error = _detect_market_mismatch(ad_url, market_code)
    if market_mismatch_error:
        result["status"] = "market_mismatch"
        result["error"] = market_mismatch_error
        return result

    page = None
    runtime_entry = None

    try:
        if not account_id or int(account_id) <= 0:
            result["status"] = "invalid_input"
            result["error"] = f"Некорректный account_id для parse_ad_page: {account_id}"
            return result

        page, runtime_entry = await open_account_runtime_page(
            user_id=user_id,
            account_id=int(account_id),
            cookies_json=cookies_json,
            proxy_text=proxy_text,
            url=ad_url,
            headless=headless,
            olx_profile_name=olx_profile_name,
            timeout=90000,
            wait_after_ms=1500,
            busy_reason="parse_ad_page",
        )

        result["browser_engine"] = runtime_entry.runtime.get("browser_engine", "gologin")
        result["gologin_profile_id"] = runtime_entry.runtime.get("gologin_profile_id")
        result["gologin_profile_name"] = runtime_entry.runtime.get("gologin_profile_name")
        result["debugger_address"] = runtime_entry.runtime.get("debugger_address")

        result["final_url"] = page.url
        try:
            result["page_title"] = await page.title()
        except Exception:
            pass

        if await is_cloudfront_block_page(page):
            result["status"] = "cloudfront_blocked"
            result["error"] = "OLX/CloudFront заблокировал страницу объявления"
            return result

        try:
            await dismiss_cookie_banner_if_present(page)
        except Exception:
            pass

        handled_soft_error = await handle_olx_soft_error_page(page, market_code=market_code)
        if handled_soft_error:
            result["final_url"] = page.url
            try:
                result["page_title"] = await page.title()
            except Exception:
                pass

        if await is_cloudfront_block_page(page):
            result["status"] = "cloudfront_blocked"
            result["error"] = "OLX/CloudFront заблокировал страницу объявления"
            return result

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
        if runtime_entry is not None:
            await close_runtime_page(runtime_entry, page)