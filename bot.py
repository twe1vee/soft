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

from jobs import ensure_check_jobs_started, ensure_send_jobs_started
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
CHECK_WORKERS = env_int("CHECK_WORKERS", 2)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)


async def post_init(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Запустить бота"),
            BotCommand("menu", "Открыть меню"),
        ]
    )
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())


async def post_shutdown(application: Application) -> None:
    send_manager = application.bot_data.get("send_jobs_manager")
    if send_manager is not None:
        try:
            await send_manager.stop()
        except Exception as exc:
            print(f"[bot] send_jobs stop failed: {exc}")

    check_manager = application.bot_data.get("check_jobs_manager")
    if check_manager is not None:
        try:
            await check_manager.stop()
        except Exception as exc:
            print(f"[bot] check_jobs stop failed: {exc}")


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Не найден BOT_TOKEN в .env")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("menu", menu_handler))

    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    application.add_handler(
        MessageHandler(
            filters.Document.ALL & ~filters.COMMAND,
            document_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_handler,
        )
    )

    application.add_error_handler(last_handler)

    async def startup(app: Application) -> None:
        await ensure_send_jobs_started(app, worker_count=SEND_WORKERS)
        await ensure_check_jobs_started(app, worker_count=CHECK_WORKERS)
        start_dialogs_jobs(app)
        print("Bot is running...")

    application.post_init = startup

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    from telegram import Update

    main()