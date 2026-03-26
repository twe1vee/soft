from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from db import mark_conversation_message_notified


def build_incoming_dialog_text(event: dict, account: dict | None = None) -> str:
    lines = [
        "📩 Новое сообщение от продавца",
        f"Продавец: {event.get('seller_name') or '—'}",
        f"Аккаунт ID: {event.get('account_id') or '—'}",
    ]

    if account:
        lines.append(f"Имя профиля: {account.get('olx_profile_name') or 'без имени'}")

    lines.extend(
        [
            f"Объявление: {event.get('ad_title') or '—'}",
            f"OLX ID: {event.get('ad_external_id') or '—'}",
            f"Время: {event.get('updated_hint') or '—'}",
            "",
            event.get("text") or "",
        ]
    )

    ad_url = event.get("ad_url")
    conversation_url = event.get("conversation_url")

    if ad_url:
        lines.extend(["", f"Ссылка на объявление: {ad_url}"])
    if conversation_url:
        lines.extend(["", f"Ссылка на диалог: {conversation_url}"])

    return "\n".join(lines).strip()


def build_incoming_dialog_keyboard(event: dict) -> InlineKeyboardMarkup:
    conversation_id = event["conversation_id"]
    account_id = event["account_id"]

    keyboard = [
        [
            InlineKeyboardButton(
                "Ответить",
                callback_data=f"dialog_reply:{conversation_id}:{account_id}",
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


async def send_incoming_dialog_notifications(
    *,
    bot,
    chat_id: int,
    events: list[dict],
    accounts_by_id: dict[int, dict] | None = None,
) -> int:
    sent_count = 0
    accounts_by_id = accounts_by_id or {}

    for event in events:
        text = build_incoming_dialog_text(
            event,
            account=accounts_by_id.get(event.get("account_id")),
        )
        keyboard = build_incoming_dialog_keyboard(event)

        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
        )

        mark_conversation_message_notified(event["message_id"])
        sent_count += 1

    return sent_count