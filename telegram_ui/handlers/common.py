from telegram import Update
from telegram.ext import ContextTypes

from db import get_or_create_user, ensure_default_template
from telegram_ui.menu import get_main_menu_inline_keyboard


def get_current_user(update: Update) -> dict:
    tg_user = update.effective_user
    user = get_or_create_user(
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
    )
    ensure_default_template(user["id"])
    return user


def build_ad_caption(ad_data: dict) -> str:
    seller = ad_data.get("seller_name") or "не найден"
    price = ad_data.get("price") or "не найдена"
    ad_id = ad_data.get("ad_id") or "не найден"
    status = ad_data.get("status") or "unknown"
    draft_text = ad_data.get("draft_text") or ""
    url = ad_data.get("url") or "—"

    return (
        "📦 Объявление\n\n"
        f"🔗 {url}\n"
        f"👤 Seller: {seller}\n"
        f"💰 Price: {price}\n"
        f"🆔 #{ad_id}\n"
        f"📌 Status: {status}\n\n"
        f"✉️ Draft:\n{draft_text}"
    )


async def show_main_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str = "⚙️ Панель управления\n\nВыберите действие из списка ниже:",
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