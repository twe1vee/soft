import asyncio
import json
from pathlib import Path

from olx.message_sender import send_message_to_ad


ACCOUNT_COOKIES_PATH = "tmp/account_cookies.txt"
PROXY_TEXT_PATH = "tmp/proxy.txt"

AD_URL = "https://www.olx.pt/d/anuncio/vendo-mquinas-de-serralharia-e-alumnios-IDJibwB.html?search_reason=search%7Corganic"
MESSAGE_TEXT = "Dzień dobry, czy ogłoszenie jest nadal aktualne?"


def read_text_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8").strip()


async def main():
    cookies_json = read_text_file(ACCOUNT_COOKIES_PATH)
    proxy_text = read_text_file(PROXY_TEXT_PATH)

    result = await send_message_to_ad(
        cookies_json=cookies_json,
        proxy_text=proxy_text,
        ad_url=AD_URL,
        message_text=MESSAGE_TEXT,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
print("TEST_SEND_MESSAGE STARTED")