import asyncio

from olx.proxy_check import check_proxy_alive

PROXIES = [
    "185.236.25.5:63334:f4OxVDPMZI:HKrUpvMcoy",
    "410248839:3290:90430:00450",
]

async def main():
    for i, proxy_text in enumerate(PROXIES, start=1):
        print(f"\n=== CHECK {i} ===")
        print("proxy_text:", proxy_text)

        result = await check_proxy_alive(
            proxy_text=proxy_text,
            headless=True,
        )

        print(result)

asyncio.run(main())