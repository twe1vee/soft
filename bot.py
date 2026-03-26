import logging
import os
from olx.dialogs_jobs import start_dialogs_jobs

from dotenv import load_dotenv
from telegram import BotCommand, MenuButtonCommands
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from telegram_ui.handlers import (
    start_handler,
    menu_handler,
    text_handler,
    button_handler,
    pending_handler,
    last_handler,
    document_handler,
)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
start_dialogs_jobs(application)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.WARNING,
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)

async def post_init(application: Application):
    await application.bot.set_my_commands([
        BotCommand("menu", "Открыть главное меню"),
        BotCommand("start", "Запустить бота"),
        BotCommand("account", "Аккаунт"),
        BotCommand("templates", "Шаблоны"),
        BotCommand("settings", "Настройка софта"),
    ])
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в переменных окружения")

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("menu", menu_handler))
    app.add_handler(CommandHandler("pending", pending_handler))
    app.add_handler(CommandHandler("last", last_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))

    print("Bot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()