import re

from telegram import Update
from telegram.ext import ContextTypes

from db import (
    ad_exists,
    ad_seen_globally,
    count_global_ad_views,
    save_ad,
    create_pending_action,
    update_ad_status,
    update_ad_draft,
    update_pending_action_status,
    get_ad_by_id,
    get_ad_by_ad_id,
    create_message,
)
from olx.draft import generate_draft
from olx.parser import parse_olx_ad
from telegram_ui.handlers.common import build_ad_caption, get_current_user
from telegram_ui.menu import build_action_keyboard, build_back_to_menu_keyboard

OLX_URL_PATTERN = r"https?://[^\s]*olx[^\s]*"
MAX_URLS_PER_MESSAGE = 5


async def handle_links_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    current_user = get_current_user(update)
    user_id = current_user["id"]

    urls = re.findall(OLX_URL_PATTERN, text, re.IGNORECASE)

    if not urls:
        await update.message.reply_text(
            "Пришли до 5 ссылок OLX одним сообщением.",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return

    urls = urls[:MAX_URLS_PER_MESSAGE]

    for url in urls:
        try:
            ad_data = await parse_olx_ad(url)
        except Exception as e:
            await update.message.reply_text(
                f"Ошибка парсинга:\n{url}\n\n{e}",
                reply_markup=build_back_to_menu_keyboard(),
            )
            continue

        if not ad_data.get("ad_id"):
            await update.message.reply_text(
                f"Не удалось извлечь ad_id:\n{url}",
                reply_markup=build_back_to_menu_keyboard(),
            )
            continue

        ad_id = ad_data["ad_id"]

        if ad_exists(user_id, ad_id):
            existing_ad = get_ad_by_ad_id(user_id, ad_id)
            await update.message.reply_text(
                f"🔁 Это объявление уже смотрели ранее",
                reply_markup=build_back_to_menu_keyboard(),
            )
            continue

        globally_seen = ad_seen_globally(ad_id)
        global_views_before_save = count_global_ad_views(ad_id)

        ad_data["status"] = "draft_ready"
        ad_data["draft_text"] = generate_draft(user_id, ad_data)

        ad_row_id = save_ad(user_id, ad_data)

        create_message(
            ad_db_id=ad_row_id,
            direction="outgoing",
            text=ad_data["draft_text"],
            status="auto_draft",
        )

        action_id = create_pending_action(
            ad_db_id=ad_row_id,
            action_type="review_draft",
            payload_text=ad_data["draft_text"],
        )

        keyboard = build_action_keyboard(ad_row_id, action_id)
        saved_ad = get_ad_by_id(user_id, ad_row_id)

        extra_note = ""
        if globally_seen:
            extra_note = (
                f"\n\n👁️ Это объявление уже встречалось в системе ранее "
                f"({global_views_before_save} раз).\n"

            )

        await update.message.reply_text(
            build_ad_caption(saved_ad) + extra_note,
            reply_markup=keyboard,
        )

    context.user_data.clear()


async def handle_editing_ad_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    current_user = get_current_user(update)
    user_id = current_user["id"]

    editing_ad_id = context.user_data.get("editing_ad_id")
    editing_action_id = context.user_data.get("editing_action_id")

    if not editing_ad_id or not editing_action_id:
        await update.message.reply_text(
            "Нет объявления для редактирования.",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return

    ad = get_ad_by_id(user_id, editing_ad_id)
    if not ad:
        await update.message.reply_text(
            "Объявление не найдено или не принадлежит вам.",
            reply_markup=build_back_to_menu_keyboard(),
        )
        context.user_data.pop("editing_ad_id", None)
        context.user_data.pop("editing_action_id", None)
        return

    new_text = text

    update_ad_draft(user_id, editing_ad_id, new_text, new_status="draft_ready")
    ad = get_ad_by_id(user_id, editing_ad_id)

    create_message(
        ad_db_id=editing_ad_id,
        direction="outgoing",
        text=new_text,
        status="edited_draft",
    )

    context.user_data.pop("editing_ad_id", None)
    context.user_data.pop("editing_action_id", None)

    keyboard = build_action_keyboard(editing_ad_id, editing_action_id)

    await update.message.reply_text(
        "✏️ Черновик обновлен.\n\n" + build_ad_caption(ad),
        reply_markup=keyboard,
    )


async def handle_ad_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    current_user = get_current_user(update)
    user_id = current_user["id"]

    query = update.callback_query
    parts = data.split(":")

    if len(parts) != 3:
        await query.edit_message_reply_markup(reply_markup=None)
        return

    action, ad_row_id_str, pending_action_id_str = parts

    try:
        ad_row_id = int(ad_row_id_str)
        pending_action_id = int(pending_action_id_str)
    except ValueError:
        await query.edit_message_text("Некорректные данные кнопки.")
        return

    ad = get_ad_by_id(user_id, ad_row_id)
    if not ad:
        await query.edit_message_text("Объявление не найдено или не принадлежит вам.")
        return

    if action == "approve":
        update_ad_status(user_id, ad_row_id, "approved")
        update_pending_action_status(pending_action_id, "done")

        ad = get_ad_by_id(user_id, ad_row_id)

        create_message(
            ad_db_id=ad_row_id,
            direction="outgoing",
            text=ad.get("draft_text") or "",
            status="approved",
        )

        await query.edit_message_text(
            build_ad_caption(ad) + "\n\n✅ Статус: APPROVED"
        )
        return

    if action == "reject":
        update_ad_status(user_id, ad_row_id, "rejected")
        update_pending_action_status(pending_action_id, "cancelled")

        ad = get_ad_by_id(user_id, ad_row_id)

        await query.edit_message_text(
            build_ad_caption(ad) + "\n\n❌ Статус: REJECTED"
        )
        return

    if action == "edit":
        context.user_data["editing_ad_id"] = ad_row_id
        context.user_data["editing_action_id"] = pending_action_id

        await query.message.reply_text(
            "Пришли новый текст сообщения одним следующим сообщением."
        )
        return

    await query.edit_message_text("Неизвестное действие.")