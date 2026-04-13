from __future__ import annotations

import re

from telegram import Update
from telegram.ext import ContextTypes

from db import (
    get_user_by_id,
    update_user_redscript_defaults,
    update_user_redscript_token,
)
from olx.ad_page_parser import parse_ad_page
from services.redscript_client import RedScriptApiError, check_token, send_mail
from telegram_ui.menu import build_back_to_menu_keyboard

DEFAULT_COUNTRY = "Румыния"
DEFAULT_TYPE = "services"
DEFAULT_SERVICE = "OLX"
DEFAULT_VERSION = "2.0"
DEFAULT_MAIL_SERVICE = "hype"


def _mask_token(token: str | None) -> str:
    text = (token or "").strip()
    if not text:
        return "не подключён"
    if len(text) <= 8:
        return "••••••••"
    return f"{'•' * 8}{text[-4:]}"


def _sanitize_redscript_name(value: str | None) -> str:
    text = str(value or "")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) > 250:
        text = text[:250].strip()

    return text


def _clear_redscript_flow(context: ContextTypes.DEFAULT_TYPE) -> None:
    keys = [
        "awaiting_redscript_api_token",
        "awaiting_redscript_initials",
        "awaiting_redscript_address",
        "awaiting_redscript_mail_service",
        "awaiting_redscript_country",
        "awaiting_redscript_type",
        "awaiting_redscript_service",
        "awaiting_redscript_version",
        "awaiting_redscript_ad_url",
        "awaiting_redscript_send_email",
        "redscript_send_payload",
    ]
    for key in keys:
        context.user_data.pop(key, None)


def _build_redscript_menu_keyboard(has_token: bool) -> object:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    rows = []

    if has_token:
        rows.append([InlineKeyboardButton("✉️ Отправить письмо", callback_data="redscript:send")])
        rows.append([InlineKeyboardButton("🔎 Проверить API", callback_data="redscript:check")])
        rows.append([InlineKeyboardButton("🧑 Настроить отправителя", callback_data="redscript:settings")])
        rows.append([InlineKeyboardButton("🔑 Изменить API", callback_data="redscript:set_token")])
    else:
        rows.append([InlineKeyboardButton("🔑 Подключить API", callback_data="redscript:set_token")])

    rows.append([InlineKeyboardButton("⬅️ Вернуться в главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)


def _get_user_settings(user: dict) -> dict:
    return {
        "access_token": (user.get("redscript_access_token") or "").strip(),
        "initials": (user.get("redscript_initials") or "").strip(),
        "address": (user.get("redscript_address") or "").strip(),
        "mail_service": (user.get("redscript_mail_service") or DEFAULT_MAIL_SERVICE).strip(),
        "country": (user.get("redscript_country") or DEFAULT_COUNTRY).strip(),
        "type": (user.get("redscript_type") or DEFAULT_TYPE).strip(),
        "service": (user.get("redscript_service") or DEFAULT_SERVICE).strip(),
        "version": (user.get("redscript_version") or DEFAULT_VERSION).strip(),
    }


async def show_redscript_screen(update_or_query, user_id: int):
    user = get_user_by_id(user_id)
    settings = _get_user_settings(user or {})
    has_token = bool(settings["access_token"])

    text = (
        "📨 Отправка письма\n\n"
        f"API: {_mask_token(settings['access_token'])}\n"
        f"Отправитель: {settings['initials'] or 'не задан'}\n"
        f"Адрес: {settings['address'] or 'не задан'}\n"
        f"Провайдер: {settings['mail_service'] or 'не задан'}\n"
        f"Страна: {settings['country'] or 'не задана'}\n"
        f"Тип: {settings['type'] or 'не задан'}\n"
        f"Сервис: {settings['service'] or 'не задан'}\n"
        f"Версия: {settings['version'] or 'не задана'}"
    )

    keyboard = _build_redscript_menu_keyboard(has_token)

    if hasattr(update_or_query, "edit_message_text"):
        await update_or_query.edit_message_text(text, reply_markup=keyboard)
    else:
        await update_or_query.message.reply_text(text, reply_markup=keyboard)


async def handle_redscript_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    query = update.callback_query
    current_user = context.user_data.get("current_user") or {}
    user_id = current_user.get("id")
    if not user_id:
        await query.edit_message_text("Пользователь не найден.")
        return

    if data == "redscript:menu":
        _clear_redscript_flow(context)
        await show_redscript_screen(query, user_id)
        return

    if data == "redscript:set_token":
        _clear_redscript_flow(context)
        context.user_data["awaiting_redscript_api_token"] = True
        await query.edit_message_text(
            "🔑 Подключение API\n\n"
            "Пришли свой access_token одним сообщением.\n\n"
            "После сохранения я сразу проверю его.",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return

    if data == "redscript:check":
        _clear_redscript_flow(context)
        user = get_user_by_id(user_id)
        settings = _get_user_settings(user or {})
        token = settings["access_token"]
        if not token:
            await query.edit_message_text(
                "API ключ ещё не подключён.",
                reply_markup=_build_redscript_menu_keyboard(False),
            )
            return

        try:
            check_token(token)
        except RedScriptApiError as exc:
            await query.edit_message_text(
                f"Ошибка проверки API:\n{exc}",
                reply_markup=_build_redscript_menu_keyboard(True),
            )
            return

        await query.edit_message_text(
            "✅ API ключ рабочий.",
            reply_markup=_build_redscript_menu_keyboard(True),
        )
        return

    if data == "redscript:settings":
        _clear_redscript_flow(context)
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Имя / инициалы", callback_data="redscript:set_initials")],
            [InlineKeyboardButton("Адрес", callback_data="redscript:set_address")],
            [InlineKeyboardButton("Провайдер", callback_data="redscript:set_mail_service")],
            [InlineKeyboardButton("Страна", callback_data="redscript:set_country")],
            [InlineKeyboardButton("Тип", callback_data="redscript:set_type")],
            [InlineKeyboardButton("Сервис", callback_data="redscript:set_service")],
            [InlineKeyboardButton("Версия", callback_data="redscript:set_version")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="redscript:menu")],
        ])
        await query.edit_message_text(
            "🧑 Настройки отправителя\n\nВыбери, что изменить.",
            reply_markup=keyboard,
        )
        return

    prompts = {
        "redscript:set_initials": ("awaiting_redscript_initials", "Пришли имя / инициалы отправителя."),
        "redscript:set_address": ("awaiting_redscript_address", "Пришли адрес отправителя."),
        "redscript:set_mail_service": ("awaiting_redscript_mail_service", "Пришли mail_service как есть. Например: Polya или polya."),
        "redscript:set_country": ("awaiting_redscript_country", "Пришли страну, например: Румыния."),
        "redscript:set_type": ("awaiting_redscript_type", "Пришли тип объявления, например: services."),
        "redscript:set_service": ("awaiting_redscript_service", "Пришли сервис, например: OLX."),
        "redscript:set_version": ("awaiting_redscript_version", "Пришли версию, например: 2.0."),
    }

    if data in prompts:
        _clear_redscript_flow(context)
        state_key, text = prompts[data]
        context.user_data[state_key] = True
        await query.edit_message_text(
            text,
            reply_markup=build_back_to_menu_keyboard(),
        )
        return

    if data == "redscript:send":
        _clear_redscript_flow(context)
        user = get_user_by_id(user_id)
        settings = _get_user_settings(user or {})
        if not settings["access_token"]:
            await query.edit_message_text(
                "Сначала подключи API ключ.",
                reply_markup=_build_redscript_menu_keyboard(False),
            )
            return

        context.user_data["redscript_send_payload"] = {}
        context.user_data["awaiting_redscript_ad_url"] = True
        await query.edit_message_text(
            "✉️ Отправка письма\n\n"
            "Пришли ссылку на объявление OLX PT.",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return


async def handle_redscript_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    current_user = context.user_data.get("current_user") or {}
    user_id = current_user.get("id")
    if not user_id:
        await update.message.reply_text("Пользователь не найден.")
        return

    if context.user_data.get("awaiting_redscript_api_token"):
        _clear_redscript_flow(context)
        token = text.strip()

        try:
            check_token(token)
        except RedScriptApiError as exc:
            await update.message.reply_text(
                f"Ошибка проверки API:\n{exc}",
                reply_markup=build_back_to_menu_keyboard(),
            )
            return

        update_user_redscript_token(user_id, token)
        await update.message.reply_text(
            "✅ API ключ сохранён и проверен.",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return

    settings_map = {
        "awaiting_redscript_initials": ("initials", "✅ Имя / инициалы сохранены."),
        "awaiting_redscript_address": ("address", "✅ Адрес сохранён."),
        "awaiting_redscript_mail_service": ("mail_service", "✅ Провайдер сохранён."),
        "awaiting_redscript_country": ("country", "✅ Страна по умолчанию сохранена."),
        "awaiting_redscript_type": ("type_value", "✅ Тип по умолчанию сохранён."),
        "awaiting_redscript_service": ("service", "✅ Сервис по умолчанию сохранён."),
        "awaiting_redscript_version": ("version", "✅ Версия по умолчанию сохранена."),
    }

    for state_key, (field_name, success_text) in settings_map.items():
        if context.user_data.get(state_key):
            _clear_redscript_flow(context)
            kwargs = {
                "initials": None,
                "address": None,
                "mail_service": None,
                "country": None,
                "type_value": None,
                "service": None,
                "version": None,
            }
            kwargs[field_name] = text.strip()
            update_user_redscript_defaults(user_id, **kwargs)
            await update.message.reply_text(
                success_text,
                reply_markup=build_back_to_menu_keyboard(),
            )
            return

    if context.user_data.get("awaiting_redscript_ad_url"):
        _clear_redscript_flow(context)

        ad_url = text.strip()
        parse_result = await parse_ad_page(
            ad_url=ad_url,
            headless=True,
            market_code="olx_pt",
        )

        if not parse_result.get("ok"):
            await update.message.reply_text(
                f"Ошибка парсинга объявления:\n{parse_result.get('error') or parse_result.get('status')}",
                reply_markup=build_back_to_menu_keyboard(),
            )
            return

        payload = {
            "ad_url": ad_url,
            "name": parse_result.get("title"),
            "amount": parse_result.get("amount"),
            "image": parse_result.get("image"),
        }
        context.user_data["redscript_send_payload"] = payload
        context.user_data["awaiting_redscript_send_email"] = True

        await update.message.reply_text(
            "Объявление распознано.\n\n"
            f"Название: {payload.get('name') or '—'}\n"
            f"Сумма: {payload.get('amount') or '—'}\n"
            f"Фото: {'найдено' if payload.get('image') else 'не найдено'}\n\n"
            "Теперь пришли почту продавца.",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return

    if context.user_data.get("awaiting_redscript_send_email"):
        payload = context.user_data.get("redscript_send_payload") or {}
        payload["email"] = text.strip()
        context.user_data["redscript_send_payload"] = payload

        context.user_data.pop("awaiting_redscript_send_email", None)

        await _send_redscript_mail_from_payload(update, context)
        return


async def _send_redscript_mail_from_payload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_user = context.user_data.get("current_user") or {}
    user_id = current_user.get("id")
    user = get_user_by_id(user_id)
    settings = _get_user_settings(user or {})
    payload = context.user_data.get("redscript_send_payload") or {}

    token = settings["access_token"]
    if not token:
        await update.message.reply_text(
            "Сначала подключи API ключ.",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return

    missing_fields = []
    if not settings["initials"]:
        missing_fields.append("имя / инициалы")
    if not settings["address"]:
        missing_fields.append("адрес")

    if missing_fields:
        _clear_redscript_flow(context)
        context.user_data.pop("redscript_send_payload", None)

        await update.message.reply_text(
            "Сначала заполни настройки отправителя:\n- " + "\n- ".join(missing_fields),
            reply_markup=build_back_to_menu_keyboard(),
        )
        return

    safe_name = _sanitize_redscript_name(payload.get("name"))
    if not safe_name:
        _clear_redscript_flow(context)
        context.user_data.pop("redscript_send_payload", None)

        await update.message.reply_text(
            "Не удалось подготовить название объявления для отправки.",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return

    debug_payload = {
        "email": payload.get("email") or "",
        "mail_service": settings["mail_service"] or DEFAULT_MAIL_SERVICE,
        "country": settings["country"] or DEFAULT_COUNTRY,
        "type": settings["type"] or DEFAULT_TYPE,
        "service": settings["service"] or DEFAULT_SERVICE,
        "version": settings["version"] or DEFAULT_VERSION,
        "name": safe_name,
        "amount": payload.get("amount") or "",
        "image": (payload.get("image") or "").strip() or None,
        "initials": settings["initials"] or None,
        "address": settings["address"] or None,
    }
    print(f"[redscript_handler] send_mail payload={debug_payload}")

    try:
        result = send_mail(
            token,
            email=payload.get("email") or "",
            mail_service=settings["mail_service"] or DEFAULT_MAIL_SERVICE,
            country=settings["country"] or DEFAULT_COUNTRY,
            type_value=settings["type"] or DEFAULT_TYPE,
            service=settings["service"] or DEFAULT_SERVICE,
            version=settings["version"] or DEFAULT_VERSION,
            name=safe_name,
            amount=payload.get("amount") or "",
            image=(payload.get("image") or "").strip() or None,
            initials=settings["initials"] or None,
            address=settings["address"] or None,
        )
    except RedScriptApiError as exc:
        _clear_redscript_flow(context)
        context.user_data.pop("redscript_send_payload", None)

        full_error = str(exc)
        if getattr(exc, "raw_text", ""):
            full_error += f"\n\nRAW: {exc.raw_text[:3000]}"

        await update.message.reply_text(
            f"Ошибка отправки письма:\n{full_error}",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return

    _clear_redscript_flow(context)
    context.user_data.pop("redscript_send_payload", None)

    result_data = result.get("result") or {}
    await update.message.reply_text(
        "✅ Письмо отправлено.\n\n"
        f"Link: {result_data.get('link') or '—'}\n"
        f"Short: {result_data.get('short') or '—'}",
        reply_markup=build_back_to_menu_keyboard(),
    )