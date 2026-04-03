from __future__ import annotations

from html import escape as html_escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from db import mark_conversation_message_notified
from olx.services.translation_service import translate_to_russian


def _escape(value) -> str:
    return html_escape(str(value or ""))


def _normalize_message_text(value: str | None) -> str:
    return (value or "").strip()


def _should_translate(text: str) -> bool:
    clean = _normalize_message_text(text)
    if not clean:
        return False

    # Совсем короткие ответы можно не гонять через переводчик
    if len(clean) < 2:
        return False

    return True


def _translate_event_text(event: dict) -> dict:
    original_text = _normalize_message_text(event.get("text"))

    if not _should_translate(original_text):
        return {
            "ok": False,
            "translated_text": None,
            "error": "translation_skipped",
            "skipped": True,
        }

    return translate_to_russian(original_text, from_code="pt", to_code="ru")


def build_incoming_dialog_text(
    event: dict,
    account: dict | None = None,
    translated_text: str | None = None,
) -> str:
    seller_name = _escape(event.get("seller_name") or "—")
    account_id = _escape(event.get("account_id") or "—")
    profile_name = _escape((account or {}).get("olx_profile_name") or "без имени")
    ad_title = _escape(event.get("ad_title") or "—")
    ad_external_id = _escape(event.get("ad_external_id") or "—")
    updated_hint = _escape(event.get("updated_hint") or "—")

    original_text = _escape(_normalize_message_text(event.get("text")) or "—")
    ad_url = (event.get("ad_url") or "").strip()

    lines = [
        "📩 <b>Новое сообщение от продавца</b>",
        f"Продавец: {seller_name}",
        f"Аккаунт ID: {account_id}",
        f"Имя профиля: {profile_name}",
        f"Объявление: {ad_title}",
        f"OLX ID: {ad_external_id}",
        f"Время: {updated_hint}",
        "",
        "Оригинал:",
        f"<blockquote>{original_text}</blockquote>",
    ]

    translated_clean = (translated_text or "").strip()
    if translated_clean:
        lines.extend(
            [
                "",
                "Перевод:",
                f"<blockquote>{_escape(translated_clean)}</blockquote>",
            ]
        )

    if ad_url:
        lines.extend(
            [
                "",
                f'Ссылка на объявление: <a href="{_escape(ad_url)}">Открыть объявление</a>',
            ]
        )

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

    print(
        f"[dialogs_notifier] start chat_id={chat_id} "
        f"events={len(events)}"
    )

    for event in events:
        account_id = event.get("account_id")
        conversation_id = event.get("conversation_id")
        message_id = event.get("message_id")

        try:
            translation_result = _translate_event_text(event)
            translated_text = (
                translation_result.get("translated_text")
                if translation_result.get("ok")
                else None
            )

            if translation_result.get("ok"):
                print(
                    f"[dialogs_notifier] translation_ok "
                    f"chat_id={chat_id} "
                    f"account_id={account_id} "
                    f"conversation_id={conversation_id} "
                    f"message_id={message_id}"
                )
            else:
                print(
                    f"[dialogs_notifier] translation_skip_or_fail "
                    f"chat_id={chat_id} "
                    f"account_id={account_id} "
                    f"conversation_id={conversation_id} "
                    f"message_id={message_id} "
                    f"error={translation_result.get('error')}"
                )

            text = build_incoming_dialog_text(
                event,
                account=accounts_by_id.get(account_id),
                translated_text=translated_text,
            )
            keyboard = build_incoming_dialog_keyboard(event)

            print(
                f"[dialogs_notifier] send "
                f"chat_id={chat_id} "
                f"account_id={account_id} "
                f"conversation_id={conversation_id} "
                f"message_id={message_id}"
            )

            await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )

            mark_conversation_message_notified(message_id)
            sent_count += 1

            print(
                f"[dialogs_notifier] sent "
                f"chat_id={chat_id} "
                f"account_id={account_id} "
                f"conversation_id={conversation_id} "
                f"message_id={message_id}"
            )

        except Exception as exc:
            print(
                f"[dialogs_notifier] failed "
                f"chat_id={chat_id} "
                f"account_id={account_id} "
                f"conversation_id={conversation_id} "
                f"message_id={message_id} "
                f"error={exc}"
            )

    print(f"[dialogs_notifier] done chat_id={chat_id} sent_count={sent_count}")
    return sent_count