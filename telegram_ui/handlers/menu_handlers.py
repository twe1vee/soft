from telegram import Update
from telegram.ext import ContextTypes

from db import init_db
from telegram_ui.handlers.proxy_handlers import show_proxies_screen
from telegram_ui.handlers.account_handlers import show_accounts_screen
from telegram_ui.handlers.common import show_main_menu, get_current_user
from telegram_ui.handlers.template_handlers import show_templates_screen
from telegram_ui.menu import build_back_to_menu_keyboard


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_db()
    current_user = get_current_user(update)
    context.user_data.clear()
    context.user_data["current_user"] = current_user
    await show_main_menu(update, context)


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_db()
    current_user = get_current_user(update)
    context.user_data.clear()
    context.user_data["current_user"] = current_user
    await show_main_menu(update, context)


async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    current_user = get_current_user(update)
    context.user_data["current_user"] = current_user
    user_id = current_user["id"]

    query = update.callback_query

    if data == "menu:main":
        context.user_data.clear()
        context.user_data["current_user"] = current_user
        await show_main_menu(update, context)
        return

    if data == "menu:account":
        context.user_data.clear()
        context.user_data["current_user"] = current_user
        await show_accounts_screen(update, context)
        return

    if data == "menu:proxies":
        context.user_data.clear()
        context.user_data["current_user"] = current_user
        await show_proxies_screen(update, context)
        return

    if data == "menu:templates":
        context.user_data.clear()
        context.user_data["current_user"] = current_user
        await show_templates_screen(query, user_id)
        return

    if data == "menu:process_links":
        context.user_data.clear()
        context.user_data["current_user"] = current_user
        context.user_data["awaiting_links"] = True
        await query.edit_message_text(
            "🔗 Обработка ссылок\n\n"
            "Пришли до 5 ссылок OLX одним сообщением.",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return

    if data == "menu:settings":
        context.user_data.clear()
        context.user_data["current_user"] = current_user
        await query.edit_message_text(
            "⚙️ Настройка софта\n\n"
            "Раздел пока в разработке.\n\n"
            "Позже здесь будет:\n"
            "- задержка между действиями\n"
            "- лимиты обработки\n"
            "- паузы\n"
            "- дополнительные параметры поведения",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return