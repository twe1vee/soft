from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from db import get_conversation_by_id
from olx.dialogs_reply import send_reply_to_conversation
from telegram_ui.menu import build_back_to_menu_keyboard
from telegram_ui.handlers.common import get_current_user


def build_dialog_reply_result_text(conversation: dict | None, result: dict) -> str:
    profile_name = (
        result.get("gologin_profile_name")
        or result.get("olx_profile_name")
        or "без имени"
    )

    lines = [
        "📤 Результат ответа в диалог",
        f"Имя профиля: {profile_name}",
    ]

    if conversation:
        lines.insert(1, f"Продавец: {conversation.get('seller_name') or '—'}")
        lines.insert(2, f"Объявление: {conversation.get('ad_title') or '—'}")

        ad_url = (conversation.get("ad_url") or "").strip()
        if ad_url:
            lines.append(f"Ссылка на объявление: {ad_url}")

    if result.get("error"):
        lines.append(f"Ошибка: {result['error']}")

    if result.get("ok") or result.get("sent") or result.get("status") == "sent":
        lines.append("✅ Ответ отправлен продавцу")

    return "\n".join(lines)


def _get_reply_bindings(context: ContextTypes.DEFAULT_TYPE) -> dict:
    bindings = context.user_data.get("dialog_reply_bindings")
    if isinstance(bindings, dict):
        return bindings

    bindings = {}
    context.user_data["dialog_reply_bindings"] = bindings
    return bindings


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

        try:
            conversation_id = int(conversation_id_str)
            account_id = int(account_id_str)
        except ValueError:
            await query.answer("Некорректные данные", show_alert=True)
            return

        context.user_data.pop("awaiting_links", None)

        prompt = await query.message.reply_text(
            "Пришли текст ответа следующим сообщением.\n\n"
            "Важно: ответь именно на это сообщение."
        )

        bindings = _get_reply_bindings(context)
        bindings[str(prompt.message_id)] = {
            "conversation_id": conversation_id,
            "account_id": account_id,
        }

        await query.answer()
        return

    await query.answer()


async def handle_dialog_reply_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
):
    reply_to = update.message.reply_to_message if update.message else None
    reply_to_message_id = reply_to.message_id if reply_to else None

    bindings = _get_reply_bindings(context)
    binding = bindings.get(str(reply_to_message_id)) if reply_to_message_id else None

    if not binding:
        await update.message.reply_text(
            "Нет активного диалога для ответа.\n\n"
            "Нажми «Ответить» под нужным уведомлением и ответь именно на служебное сообщение.",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return

    conversation_id = binding.get("conversation_id")
    account_id = binding.get("account_id")

    if not conversation_id or not account_id:
        await update.message.reply_text(
            "Нет активного диалога для ответа.",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return

    if not text.strip():
        await update.message.reply_text(
            "Текст ответа пустой. Пришли нормальный текст одним сообщением.",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return

    current_user = get_current_user(update)
    context.user_data["current_user"] = current_user
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

    if reply_to_message_id is not None:
        bindings.pop(str(reply_to_message_id), None)

    await update.message.reply_text(
        build_dialog_reply_result_text(conversation, result),
        reply_markup=build_back_to_menu_keyboard(),
    )