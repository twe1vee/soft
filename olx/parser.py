import re
from playwright.async_api import async_playwright

async def extract_price(page) -> str | None:
    possible_price_selectors = [
        '[data-testid="ad-price-container"]',
        '[data-testid="price-value"]',
        "h3",
        "h2",
    ]

    for selector in possible_price_selectors:
        try:
            elements = page.locator(selector)
            count = await elements.count()

            for i in range(count):
                text = (await elements.nth(i).inner_text()).strip()
                if any(x in text.lower() for x in ["грн", "uah", "₴", "€", "$", "usd"]):
                    return text
        except Exception:
            pass

    return None


def extract_ad_id(full_text: str) -> str | None:
    patterns = [
        r"ID:\s*(\d+)",
        r"ID do anúncio:\s*(\d+)",
        r"Advert ID:\s*(\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def extract_seller_name(full_text: str) -> str | None:
    lines = [line.strip() for line in full_text.splitlines() if line.strip()]

    blocked_values = {
        "contactar anunciante",
        "utilizador",
        "todos os anúncios deste anunciante",
        "enviar mensagem",
        "reportar",
        "entrar ou criar conta",
    }

    for i, line in enumerate(lines):
        if line.lower() in {"contactar anunciante", "utilizador"}:
            for j in range(i + 1, min(i + 5, len(lines))):
                candidate = lines[j].strip()
                if (
                    candidate
                    and candidate.lower() not in blocked_values
                    and len(candidate) < 40
                    and "olx" not in candidate.lower()
                    and "conta" not in candidate.lower()
                    and "mensagem" not in candidate.lower()
                ):
                    return candidate

    return None


async def parse_olx_ad(url: str) -> dict:
    result = {
        "url": url,
        "price": None,
        "seller_name": None,
        "ad_id": None,
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(1500)

        full_text = await page.locator("body").inner_text()

        result["price"] = await extract_price(page)
        result["ad_id"] = extract_ad_id(full_text)
        result["seller_name"] = extract_seller_name(full_text)

        await browser.close()

    return result