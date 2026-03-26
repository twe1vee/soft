from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from db import get_conversation_by_id
from olx.dialogs_reply import send_reply_to_conversation
from telegram_ui.menu import build_back_to_menu_keyboard


def build_dialog_reply_result_text(conversation: dict | None, result: dict) -> str:
    lines = [
        "📤 Результат ответа в диалог",
        f"Диалог ID: {result.get('conversation_id') or '—'}",
        f"Аккаунт ID: {result.get('account_id') or '—'}",
        f"Статус: {result.get('status') or 'unknown'}",
        f"Final URL: {result.get('final_url') or result.get('target_url') or '—'}",
    ]

    if conversation:
        lines.insert(1, f"Продавец: {conversation.get('seller_name') or '—'}")
        lines.insert(2, f"Объявление: {conversation.get('ad_title') or '—'}")

    if result.get("error"):
        lines.append(f"Ошибка: {result['error']}")

    if result.get("ok") or result.get("sent") or result.get("status") == "sent":
        lines.append("✅ Ответ реально отправлен продавцу")

    return "\n".join(lines)


async def handle_dialog_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
):
    query = update.callback_query
    parts = data.split(":")

    if not parts:
        await query.answer()
        return

    action = parts[0]

    if action == "dialog_reply":
        if len(parts) != 3:
            await query.answer("Некорректные данные", show_alert=True)
            return

        _, conversation_id_str, account_id_str = parts
        context.user_data["reply_conversation_id"] = int(conversation_id_str)
        context.user_data["reply_account_id"] = int(account_id_str)

        await query.message.reply_text("Пришли текст ответа следующим сообщением.")
        await query.answer()
        return

    await query.answer()


async def handle_dialog_reply_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
):
    conversation_id = context.user_data.get("reply_conversation_id")
    account_id = context.user_data.get("reply_account_id")

    if not conversation_id or not account_id:
        await update.message.reply_text(
            "Нет активного диалога для ответа.",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return

    current_user = context.user_data.get("current_user")
    if not current_user:
        from telegram_ui.handlers.common import get_current_user
        current_user = get_current_user(update)

    user_id = current_user["id"]
    conversation = get_conversation_by_id(user_id, int(conversation_id))

    await update.message.reply_text("⏳ Отправляю ответ продавцу...")

    result = await send_reply_to_conversation(
        user_id=user_id,
        conversation_id=int(conversation_id),
        account_id=int(account_id),
        message_text=text,
        headless=True,
    )

    context.user_data.pop("reply_conversation_id", None)
    context.user_data.pop("reply_account_id", None)

    await update.message.reply_text(
        build_dialog_reply_result_text(conversation, result),
        reply_markup=build_back_to_menu_keyboard(),
    )