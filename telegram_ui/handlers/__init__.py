from telegram import Update
from telegram.ext import ContextTypes

from telegram_ui.handlers.account_handlers import (
    handle_account_callback,
    handle_accounts_file,
    handle_check_all_accounts,
    handle_delete_all_accounts,
)
from telegram_ui.handlers.ad_handlers import (
    handle_ad_callback,
    handle_editing_ad_text,
    handle_links_text,
)
from telegram_ui.handlers.dialog_handlers import (
    handle_dialog_callback,
    handle_dialog_reply_text,
)
from telegram_ui.handlers.proxy_handlers import (
    handle_check_all_proxies,
    handle_delete_all_proxies,
    handle_proxies_file,
    handle_proxy_callback,
)
from telegram_ui.handlers.template_handlers import (
    handle_template_callback,
    handle_template_edit_text,
)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data.startswith("proxy:"):
        await handle_proxy_callback(update, context, data)
        return

    if data.startswith("account:"):
        await handle_account_callback(update, context, data)
        return

    if data.startswith("approve:") or data.startswith("edit:") or data.startswith("reject:") \
            or data.startswith("back_to_actions:") or data.startswith("approve_account:"):
        await handle_ad_callback(update, context, data)
        return

    if data.startswith("dialog_reply:"):
        await handle_dialog_callback(update, context, data)
        return

    if data.startswith("template:"):
        await handle_template_callback(update, context, data)
        return

    if data == "check_all_proxies":
        await handle_check_all_proxies(update, context)
        return

    if data == "delete_all_proxies":
        await handle_delete_all_proxies(update, context)
        return

    if data == "check_all_accounts":
        await handle_check_all_accounts(update, context)
        return

    if data == "delete_all_accounts":
        await handle_delete_all_accounts(update, context)
        return

    await query.edit_message_text("Неизвестное действие.")


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    if context.user_data.get("editing_template"):
        await handle_template_edit_text(update, context, text)
        return

    if context.user_data.get("editing_ad_id") and context.user_data.get("editing_action_id"):
        await handle_editing_ad_text(update, context, text)
        return

    if context.user_data.get("reply_conversation_id") and context.user_data.get("reply_account_id"):
        await handle_dialog_reply_text(update, context, text)
        return

    await handle_links_text(update, context, text)


async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_proxies_file"):
        await handle_proxies_file(update, context)
        return

    if context.user_data.get("awaiting_accounts_file"):
        await handle_accounts_file(update, context)
        return

    await update.message.reply_text("Сейчас этот файл не ожидается.")