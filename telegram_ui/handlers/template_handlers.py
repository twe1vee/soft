from telegram import Update
from telegram.ext import ContextTypes

from db import get_active_template, update_active_template
from telegram_ui.handlers.common import get_current_user
from telegram_ui.menu import get_templates_menu_keyboard


async def show_templates_screen(query, user_id: int):
    template = get_active_template(user_id)
    template_text = template["template_text"] if template else "Шаблон не найден."

    await query.edit_message_text(
        "🧩 Шаблон\n\n"
        "Здесь настраивается текущий шаблон ответа.\n\n"
        "Текущий шаблон:\n\n"
        f"{template_text}",
        reply_markup=get_templates_menu_keyboard(),
    )


async def handle_template_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    current_user = get_current_user(update)
    user_id = current_user["id"]

    query = update.callback_query

    if data == "templates:edit":
        context.user_data.clear()
        context.user_data["editing_template"] = True

        template = get_active_template(user_id)
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


async def handle_editing_template_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    current_user = get_current_user(update)
    user_id = current_user["id"]

    update_active_template(user_id, text)
    context.user_data.clear()

    template = get_active_template(user_id)
    template_text = template["template_text"] if template else "Шаблон не найден."

    await update.message.reply_text("✅ Шаблон обновлен.")
    await update.message.reply_text(
        "🧩 Шаблон\n\n"
        "Здесь настраивается текущий шаблон ответа.\n\n"
        "Текущий шаблон:\n\n"
        f"{template_text}",
        reply_markup=get_templates_menu_keyboard(),
    )