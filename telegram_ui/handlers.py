from olx.draft import generate_draft

import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes


from olx.parser import parse_olx_ad
from telegram_ui.menu import get_main_menu_inline_keyboard, get_templates_menu_keyboard
from db.db import (
    init_db,
    ad_exists,
    save_ad,
    create_pending_action,
    update_ad_status,
    update_ad_draft,
    update_pending_action_status,
    get_pending_actions,
    get_last_ad,
    get_ad_by_id,
    get_ad_by_ad_id,
    create_message,
    get_active_template,
    update_active_template,
)

OLX_URL_PATTERN = r"https?://[^\s]*olx[^\s]*"
MAX_URLS_PER_MESSAGE = 5


def build_ad_caption(ad_data: dict) -> str:
    seller = ad_data.get("seller_name") or "не найден"
    price = ad_data.get("price") or "не найдена"
    ad_id = ad_data.get("ad_id") or "не найден"
    status = ad_data.get("status") or "unknown"
    draft_text = ad_data.get("draft_text") or ""

    return (
        f"📦 Объявление\n\n"
        f"👤 Seller: {seller}\n"
        f"💰 Price: {price}\n"
        f"🆔 Ad ID: {ad_id}\n"
        f"📌 Status: {status}\n\n"
        f"✉️ Draft:\n{draft_text}"
    )


def build_action_keyboard(ad_row_id: int, action_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Approve", callback_data=f"approve:{ad_row_id}:{action_id}"),
            InlineKeyboardButton("Edit", callback_data=f"edit:{ad_row_id}:{action_id}"),
            InlineKeyboardButton("Reject", callback_data=f"reject:{ad_row_id}:{action_id}"),
        ]
    ])


def build_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Вернуться в главное меню", callback_data="menu:main")]
    ])


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

async def show_templates_screen(query, template_text: str):
    await query.edit_message_text(
        "📝 Шаблоны\n\n"
        "Здесь настраивается быстрый шаблон ответа.\n\n"
        "Текущий шаблон:\n\n"
        f"{template_text}",
        reply_markup=get_templates_menu_keyboard(),
    )


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_db()
    context.user_data.clear()
    await show_main_menu(update, context)


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_db()
    context.user_data.clear()
    await show_main_menu(update, context)


async def pending_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_db()
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
    init_db()
    ad = get_last_ad()

    if not ad:
        await update.message.reply_text("В базе пока нет объявлений.")
        return

    await update.message.reply_text(build_ad_caption(ad))


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_db()

    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    editing_template = context.user_data.get("editing_template")
    editing_ad_id = context.user_data.get("editing_ad_id")
    editing_action_id = context.user_data.get("editing_action_id")
    awaiting_links = context.user_data.get("awaiting_links")

    if editing_template:
        update_active_template(text)
        context.user_data.clear()

        template = get_active_template()
        template_text = template["template_text"] if template else "Шаблон не найден."

        await update.message.reply_text("✅ Шаблон обновлен.")

        await update.message.reply_text(
            "📝 Шаблоны\n\n"
            "Здесь настраивается быстрый шаблон ответа.\n\n"
            "Текущий шаблон:\n\n"
            f"{template_text}",
            reply_markup=get_templates_menu_keyboard(),
        )
        return

    if editing_ad_id:
        new_text = text

        update_ad_draft(editing_ad_id, new_text, new_status="draft_ready")
        create_message(
            ad_db_id=editing_ad_id,
            direction="outgoing",
            text=new_text,
            status="edited_draft",
        )

        ad = get_ad_by_id(editing_ad_id)

        context.user_data.pop("editing_ad_id", None)
        context.user_data.pop("editing_action_id", None)

        keyboard = build_action_keyboard(editing_ad_id, editing_action_id)

        await update.message.reply_text(
            "✏️ Черновик обновлен.\n\n" + build_ad_caption(ad),
            reply_markup=keyboard,
        )
        return

    if awaiting_links:
        urls = re.findall(OLX_URL_PATTERN, text, re.IGNORECASE)

        if not urls:
            await update.message.reply_text(
                "Пришли до 5 ссылок OLX одним сообщением.",
                reply_markup=build_back_to_menu_keyboard(),
            )
            return

        urls = urls[:MAX_URLS_PER_MESSAGE]
        summary = []

        for url in urls:
            try:
                ad_data = await parse_olx_ad(url)
            except Exception as e:
                summary.append(f"Ошибка парсинга: {url}\n{e}")
                continue

            if not ad_data.get("ad_id"):
                summary.append(f"Не удалось извлечь ad_id: {url}")
                continue

            if ad_exists(ad_data["ad_id"]):
                existing_ad = get_ad_by_ad_id(ad_data["ad_id"])
                summary.append(
                    f"Дубликат: AD ID {ad_data['ad_id']}, "
                    f"status={existing_ad.get('status')}, "
                    f"seller={existing_ad.get('seller_name') or '?'}"
                )
                continue

            ad_data["status"] = "draft_ready"
            ad_data["draft_text"] = generate_draft(ad_data)

            ad_row_id = save_ad(ad_data)

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

            await update.message.reply_text(
                build_ad_caption(ad_data),
                reply_markup=keyboard,
            )

            summary.append(f"Сохранено: AD ID {ad_data['ad_id']}")

        context.user_data.clear()

        await update.message.reply_text(
            "Результат:\n" + "\n".join(summary),
            reply_markup=build_back_to_menu_keyboard(),
        )
        return

    await update.message.reply_text(
        "Используй /menu чтобы открыть панель управления."
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    await query.answer()

    data = query.data or ""

    if data == "menu:main":
        context.user_data.clear()
        await query.edit_message_text(
            "⚙️ Панель управления\n\nВыберите действие:",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        return

    if data == "menu:account":
        context.user_data.clear()
        await query.edit_message_text(
            "👤 Аккаунт\n\n"
            "Раздел пока в разработке.\n\n"
            "Позже здесь будет:\n"
            "- загрузка cookies\n"
            "- проверка авторизации\n"
            "- работа с аккаунтом OLX",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return

    if data == "menu:templates":
        context.user_data.clear()

        template = get_active_template()
        template_text = template["template_text"] if template else "Шаблон не найден."

        await show_templates_screen(query, template_text)
        return

    if data == "templates:edit":
        context.user_data.clear()
        context.user_data["editing_template"] = True

        template = get_active_template()
        template_text = template["template_text"] if template else "Шаблон не найден."

        await query.message.reply_text(
            "✏️ Редактирование шаблона\n\n"
            "Текущий шаблон:\n\n"
            f"{template_text}\n\n"
            "Отправь следующим сообщением новый шаблон целиком.\n\n"
            "Доступные переменные:\n"
            "{seller_name}\n"
            "{price}\n"
            "{url}"
        )
        return

    if data == "menu:process_links":
        context.user_data.clear()
        context.user_data["awaiting_links"] = True

        await query.edit_message_text(
            "🔗 Обработка ссылок\n\n"
            "Пришли до 5 ссылок OLX одним сообщением.",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return

    if data == "menu:settings":
        context.user_data.clear()
        await query.edit_message_text(
            "⚙️ Настройка софта\n\n"
            "Здесь будут пользовательские настройки работы софта.\n\n"
            "Позже здесь будет:\n"
            "- задержка между действиями\n"
            "- лимиты обработки\n"
            "- паузы\n"
            "- дополнительные параметры поведения",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return

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

    if action == "approve":
        update_ad_status(ad_row_id, "approved")
        update_pending_action_status(pending_action_id, "done")

        ad = get_ad_by_id(ad_row_id)
        create_message(
            ad_db_id=ad_row_id,
            direction="outgoing",
            text=ad.get("draft_text") or "",
            status="approved",
        )

        await query.edit_message_text(
            build_ad_caption(ad) + "\n\n✅ Статус: APPROVED"
        )

    elif action == "reject":
        update_ad_status(ad_row_id, "rejected")
        update_pending_action_status(pending_action_id, "cancelled")

        ad = get_ad_by_id(ad_row_id)

        await query.edit_message_text(
            build_ad_caption(ad) + "\n\n❌ Статус: REJECTED"
        )

    elif action == "edit":
        context.user_data["editing_ad_id"] = ad_row_id
        context.user_data["editing_action_id"] = pending_action_id

        await query.message.reply_text(
            "Пришли новый текст сообщения одним следующим сообщением."
        )

    else:
        await query.edit_message_text("Неизвестное действие.")