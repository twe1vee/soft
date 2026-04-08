import logging
import os

from dotenv import load_dotenv
from telegram import BotCommand, MenuButtonCommands
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from jobs.send_jobs import ensure_send_jobs_started, get_send_jobs_manager
from olx.dialogs_jobs import start_dialogs_jobs
from telegram_ui.handlers import (
    button_handler,
    document_handler,
    last_handler,
    menu_handler,
    pending_handler,
    photo_handler,
    start_handler,
    text_handler,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


SEND_WORKERS = env_int("SEND_WORKERS", 2)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"[telegram_error] {context.error}")


async def post_init(application: Application):
    await application.bot.set_my_commands(
        [
            BotCommand("menu", "Открыть главное меню"),
            BotCommand("start", "Запустить бота"),
            BotCommand("account", "Аккаунт"),
            BotCommand("templates", "Шаблоны"),
            BotCommand("settings", "Настройка софта"),
        ]
    )
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    await ensure_send_jobs_started(application, worker_count=SEND_WORKERS)


async def post_shutdown(application: Application):
    manager = get_send_jobs_manager(application)
    if manager is not None:
        await manager.stop()


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в переменных окружения")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_error_handler(error_handler)

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("menu", menu_handler))
    app.add_handler(CommandHandler("pending", pending_handler))
    app.add_handler(CommandHandler("last", last_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))

    start_dialogs_jobs(app)

    print("Bot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()