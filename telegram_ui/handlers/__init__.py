import re

from telegram import Update
from telegram.ext import ContextTypes
from telegram_ui.handlers.proxy_handlers import (
    handle_proxy_callback,
    handle_proxies_text,
    handle_proxies_document,
)

from db import init_db
from telegram_ui.handlers.account_handlers import (
    handle_account_callback,
    handle_account_cookies_text,
    handle_account_cookies_document,
)
from telegram_ui.handlers.ad_handlers import (
    handle_editing_ad_text,
    handle_links_text,
    handle_ad_callback,
)
from telegram_ui.handlers.debug_handlers import pending_handler, last_handler
from telegram_ui.handlers.menu_handlers import (
    start_handler,
    menu_handler,
    handle_menu_callback,
)
from telegram_ui.handlers.template_handlers import (
    handle_editing_template_text,
    handle_template_callback,
)

OLX_URL_PATTERN = r"https?://[^\s]*olx[^\s]*"


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_db()

    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    if context.user_data.get("editing_template"):
        await handle_editing_template_text(update, context, text)
        return

    if context.user_data.get("editing_ad_id"):
        await handle_editing_ad_text(update, context, text)
        return

    if (
        context.user_data.get("awaiting_account_cookies")
        or context.user_data.get("awaiting_account_cookies_update")
    ):
        await handle_account_cookies_text(update, context, text)
        return

    if context.user_data.get("awaiting_links"):
        await handle_links_text(update, context, text)
        return

    if context.user_data.get("awaiting_proxies"):
        await handle_proxies_text(update, context, text)
        return

    await update.message.reply_text("Используй /menu чтобы открыть панель управления.")


async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_db()

    if not update.message or not update.message.document:
        return

    if (
        context.user_data.get("awaiting_account_cookies")
        or context.user_data.get("awaiting_account_cookies_update")
    ):
        await handle_account_cookies_document(update, context)
        return

    if context.user_data.get("awaiting_proxies"):
        await handle_proxies_document(update, context)
        return

    await update.message.reply_text(
        "Сейчас я не жду файл.\nИспользуй /menu чтобы открыть панель управления."
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_db()

    query = update.callback_query
    if not query:
        return

    await query.answer()
    data = query.data or ""

    if data.startswith("menu:"):
        await handle_menu_callback(update, context, data)
        return

    if data.startswith("account:"):
        await handle_account_callback(update, context, data)
        return

    if data.startswith("templates:"):
        await handle_template_callback(update, context, data)
        return

    if (
        data.startswith("approve:")
        or data.startswith("reject:")
        or data.startswith("edit:")
    ):
        await handle_ad_callback(update, context, data)
        return

    if data.startswith("proxy:"):
        await handle_proxy_callback(update, context, data)
        return

    await query.edit_message_text("Неизвестное действие.")