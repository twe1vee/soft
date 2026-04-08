from __future__ import annotations

import os
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from db import (
    get_active_template,
    update_active_template,
    update_active_template_image,
    clear_active_template_image,
)
from telegram_ui.handlers.common import get_current_user
from telegram_ui.menu import (
    get_templates_menu_keyboard,
    get_template_preview_back_keyboard,
)

TEMPLATE_IMAGES_DIR = Path("storage/template_images")


def _build_templates_screen_text(template: dict | None) -> str:
    template_text = (template.get("template_text") if template else "") or "Шаблон не найден."
    image_path = (template.get("image_path") if template else "") or ""
    has_image = bool(image_path)

    image_status = "прикреплено" if has_image else "не прикреплено"

    return (
        "🧩 Шаблон сообщения\n\n"
        "Здесь настраивается сообщение, которое софт отправляет продавцу.\n\n"
        f"Фото: {image_status}\n\n"
        "Текущий текст:\n\n"
        f"{template_text}"
    )


def _safe_remove_file(path_value: str | None) -> None:
    path_text = (path_value or "").strip()
    if not path_text:
        return

    try:
        path = Path(path_text)
        if path.exists() and path.is_file():
            path.unlink()
    except OSError:
        pass


def _build_template_action_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад", callback_data="templates:close_temp_message")]
    ])


async def show_templates_screen(query, user_id: int):
    template = get_active_template(user_id)
    has_image = bool((template or {}).get("image_path"))

    await query.edit_message_text(
        _build_templates_screen_text(template),
        reply_markup=get_templates_menu_keyboard(has_image=has_image),
    )


async def _send_template_preview(query, user_id: int):
    template = get_active_template(user_id)
    template_text = (template.get("template_text") if template else "") or "Шаблон не найден."
    image_path = (template.get("image_path") if template else "") or ""

    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as photo_file:
            await query.message.reply_photo(
                photo=photo_file,
                caption=template_text[:1024] if template_text else "🧩 Текущий шаблон",
                reply_markup=get_template_preview_back_keyboard(),
            )
        return

    await query.message.reply_text(
        "👁 Текущий шаблон\n\n"
        f"{template_text}",
        reply_markup=get_template_preview_back_keyboard(),
    )


async def handle_template_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    current_user = get_current_user(update)
    user_id = current_user["id"]

    query = update.callback_query

    if data in {"templates:back", "templates:close_temp_message"}:
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    if data == "menu:templates":
        context.user_data.pop("editing_template", None)
        context.user_data.pop("awaiting_template_image", None)
        await show_templates_screen(query, user_id)
        return

    if data == "templates:preview":
        await _send_template_preview(query, user_id)
        return

    if data == "templates:edit_text":
        context.user_data.clear()
        context.user_data["editing_template"] = True

        template = get_active_template(user_id)
        template_text = template["template_text"] if template else "Шаблон не найден."

        await query.message.reply_text(
            "✏️ Изменение текста сообщения\n\n"
            "Отправь следующим сообщением новый текст шаблона целиком.\n\n"
            "Доступные переменные:\n"
            "{seller_name}\n"
            "{price}\n"
            "{url}\n\n"
            "Текущий текст:\n\n"
            f"{template_text}",
            reply_markup=_build_template_action_back_keyboard(),
        )
        return

    if data == "templates:upload_image":
        context.user_data.clear()
        context.user_data["awaiting_template_image"] = True

        await query.message.reply_text(
            "🖼 Загрузка фото для шаблона\n\n"
            "Пришли следующим сообщением фотографию для шаблона.\n\n"
            "Поддерживаются JPG и PNG.\n"
            "Если фото уже есть, оно будет заменено.",
            reply_markup=_build_template_action_back_keyboard(),
        )
        return

    if data == "templates:remove_image":
        template = get_active_template(user_id)
        old_image_path = (template.get("image_path") if template else "") or ""

        _safe_remove_file(old_image_path)
        clear_active_template_image(user_id)

        await show_templates_screen(query, user_id)
        return


async def handle_editing_template_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    current_user = get_current_user(update)
    user_id = current_user["id"]

    update_active_template(user_id, text)
    context.user_data.clear()

    template = get_active_template(user_id)
    has_image = bool((template or {}).get("image_path"))

    await update.message.reply_text("✅ Текст шаблона обновлен.")
    await update.message.reply_text(
        _build_templates_screen_text(template),
        reply_markup=get_templates_menu_keyboard(has_image=has_image),
    )


async def handle_template_image_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_user = get_current_user(update)
    user_id = current_user["id"]

    message = update.message
    if not message:
        return

    file_obj = None
    extension = ".jpg"

    if message.photo:
        photo = message.photo[-1]
        file_obj = await photo.get_file()
        extension = ".jpg"
    elif message.document:
        document = message.document
        mime_type = (document.mime_type or "").lower()
        file_name = (document.file_name or "").lower()

        if mime_type == "image/png" or file_name.endswith(".png"):
            extension = ".png"
        elif mime_type in {"image/jpeg", "image/jpg"} or file_name.endswith(".jpg") or file_name.endswith(".jpeg"):
            extension = ".jpg"
        else:
            await message.reply_text("❌ Пришли фото в формате JPG или PNG.")
            return

        file_obj = await document.get_file()
    else:
        await message.reply_text("❌ Сейчас ожидается только фотография.")
        return

    TEMPLATE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    user_dir = TEMPLATE_IMAGES_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    template = get_active_template(user_id)
    old_image_path = (template.get("image_path") if template else "") or ""

    new_path = user_dir / f"active_template{extension}"

    try:
        await file_obj.download_to_drive(custom_path=str(new_path))
    except Exception as exc:
        await message.reply_text(f"❌ Не удалось сохранить фото: {exc}")
        return

    if old_image_path and Path(old_image_path).resolve() != new_path.resolve():
        _safe_remove_file(old_image_path)

    update_active_template_image(user_id, str(new_path))
    context.user_data.clear()

    template = get_active_template(user_id)
    has_image = bool((template or {}).get("image_path"))

    await message.reply_text("✅ Фото шаблона обновлено.")
    await message.reply_text(
        _build_templates_screen_text(template),
        reply_markup=get_templates_menu_keyboard(has_image=has_image),
    )