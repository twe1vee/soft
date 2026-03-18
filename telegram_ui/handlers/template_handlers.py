from telegram.ext import ContextTypes

from db import get_active_template, update_active_template
from telegram_ui.menu import get_templates_menu_keyboard


async def show_templates_screen(query, template_text: str):
    await query.edit_message_text(
        "🙌 Шаблоны\n\n"
        "Здесь настраивается быстрый шаблон ответа.\n\n"
        "Текущий шаблон:\n\n"
        f"{template_text}",
        reply_markup=get_templates_menu_keyboard(),
    )


async def handle_template_callback(update, context: ContextTypes.DEFAULT_TYPE, data: str):
    query = update.callback_query

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


async def handle_editing_template_text(update, context: ContextTypes.DEFAULT_TYPE, text: str):
    update_active_template(text)
    context.user_data.clear()

    template = get_active_template()
    template_text = template["template_text"] if template else "Шаблон не найден."

    await update.message.reply_text("✅ Шаблон обновлен.")
    await update.message.reply_text(
        "🙌 Шаблоны\n\n"
        "Здесь настраивается быстрый шаблон ответа.\n\n"
        "Текущий шаблон:\n\n"
        f"{template_text}",
        reply_markup=get_templates_menu_keyboard(),
    )