from telegram import Update
from telegram.ext import ContextTypes

from telegram_ui.menu import get_main_menu_inline_keyboard


def build_ad_caption(ad_data: dict) -> str:
    seller = ad_data.get("seller_name") or "не найден"
    price = ad_data.get("price") or "не найдена"
    ad_id = ad_data.get("ad_id") or "не найден"
    status = ad_data.get("status") or "unknown"
    draft_text = ad_data.get("draft_text") or ""

    return (
        "📦 Объявление\n\n"
        f"👤 Seller: {seller}\n"
        f"💰 Price: {price}\n"
        f"🆔 Ad ID: {ad_id}\n"
        f"📌 Status: {status}\n\n"
        f"✉️ Draft:\n{draft_text}"
    )


async def show_main_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str = "⚙️ Панель управления\n\nВыберите действие:",
):
    if update.message:
        await update.message.reply_text(
            text,
            reply_markup=get_main_menu_inline_keyboard(),
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=get_main_menu_inline_keyboard(),
        )