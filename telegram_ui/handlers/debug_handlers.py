from telegram import Update
from telegram.ext import ContextTypes

from db import get_pending_actions, get_last_ad
from telegram_ui.handlers.common import build_ad_caption


async def pending_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = get_pending_actions("pending")

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
    ad = get_last_ad()

    if not ad:
        await update.message.reply_text("В базе пока нет объявлений.")
        return

    await update.message.reply_text(build_ad_caption(ad))