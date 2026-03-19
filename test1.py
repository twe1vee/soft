import asyncio
from db import get_account_by_id, get_user_proxies
from olx.account_session import check_account_with_proxy

async def main():
    user_id = 1
    account = get_account_by_id(user_id, 1)
    proxies = get_user_proxies(user_id)

    if not account:
        print("Аккаунт не найден")
        return

    if not proxies:
        print("Прокси не найдены")
        return

    result = await check_account_with_proxy(
        account["cookies_json"],
        proxies[0]["proxy_text"],
    )
    print(result)

asyncio.run(main())