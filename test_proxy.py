import asyncio

from playwright.async_api import async_playwright


TEST_URLS = [
    "https://httpbin.org/ip",
    "https://example.com/",
    "https://www.olx.pt/",
]


async def main():
    async with async_playwright() as p:
        browser = None
        context = None

        try:
            browser = await p.chromium.launch(
                headless=False,
                proxy={"server": "http://127.0.0.1:8118"},
                timeout=90000,
            )

            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                locale="pt-PT",
                viewport={"width": 1366, "height": 768},
                ignore_https_errors=True,
            )

            page = await context.new_page()

            for url in TEST_URLS:
                print(f"\n=== OPEN {url} ===")

                try:
                    response = await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=90000,
                    )
                    await page.wait_for_timeout(3000)

                    status = response.status if response else "no_response"
                    title = await page.title()
                    final_url = page.url
                    body_text = await page.locator("body").inner_text()

                    print("STATUS:", status)
                    print("FINAL URL:", final_url)
                    print("TITLE:", title[:120])
                    print("BODY PREVIEW:", body_text[:300].replace("\n", " "))

                except Exception as exc:
                    print("OPEN FAILED:", str(exc))

            print("\nГотово.")

        finally:
            try:
                if context:
                    await context.close()
            except Exception:
                pass

            try:
                if browser:
                    await browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())