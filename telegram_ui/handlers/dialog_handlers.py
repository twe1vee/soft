from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes


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

        await query.message.reply_text(
            "Пришли текст ответа следующим сообщением."
        )
        await query.answer()
        return

    await query.answer()