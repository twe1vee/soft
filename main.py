import asyncio

from olx.parser import parse_olx_ad
from olx.draft import generate_draft
from db.db import (
    init_db,
    ad_exists,
    save_ad,
    create_pending_action,
    get_next_pending_action,
)


async def async_main():
    init_db()

    url = input("Вставь ссылку OLX: ").strip()
    ad_data = await parse_olx_ad(url)

    if not ad_data["ad_id"]:
        print("\n=== RESULT ===")
        print("Не удалось извлечь ID объявления.")
        print("Объявление не сохраняю.")
        return

    if ad_exists(ad_data["ad_id"]):
        print("\n=== RESULT ===")
        print("Объявление уже есть в базе. Повторно не сохраняю.")
        print(f"AD ID: {ad_data['ad_id']}")
        return

    ad_data["status"] = "draft_ready"
    ad_data["draft_text"] = generate_draft(ad_data)

    ad_row_id = save_ad(ad_data)

    create_pending_action(
        ad_db_id=ad_row_id,
        action_type="review_draft",
        payload_text=ad_data["draft_text"],
    )

    print("\n=== NEXT PENDING ACTION ===")

    action = get_next_pending_action()

    if not action:
        print("Нет задач, ожидающих подтверждения.")
    else:
        print(f"Action ID: {action['action_id']}")
        print(f"Seller: {action['seller_name']}")
        print(f"Price: {action['price']}")
        print(f"Text: {action['payload_text']}")
        print(f"Status: {action['action_status']}")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()