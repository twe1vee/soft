from telegram import Update
from telegram.ext import ContextTypes

from db import get_pending_actions, get_last_ad
from telegram_ui.handlers.common import build_ad_caption, get_current_user


async def pending_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_user = get_current_user(update)
    user_id = current_user["id"]

    items = get_pending_actions(user_id, "pending")

    if not items:
        await update.message.reply_text("Нет pending-задач.")
        return

    lines = ["Pending tasks:\n"]

    for item in items[:10]:
        seller = item.get("seller_name") or "?"
        price = item.get("price") or "?"
        lines.append(
            f"- action_id={item['action_id']}, ad_id={item['ad_id']}, "
            f"type={item['action_type']}, seller={seller}, price={price}"
        )

    await update.message.reply_text("\n".join(lines))


async def last_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_user = get_current_user(update)
    user_id = current_user["id"]

    ad = get_last_ad(user_id)

    if not ad:
        await update.message.reply_text("В базе пока нет объявлений.")
        return

    await update.message.reply_text(build_ad_caption(ad))