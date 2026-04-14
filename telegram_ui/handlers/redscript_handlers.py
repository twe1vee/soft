from __future__ import annotations

import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from db import (
    get_user_by_id,
    update_user_redscript_defaults,
    update_user_redscript_token,
)
from olx.ad_page_parser import parse_ad_page
from services.redscript_client import RedScriptApiError, check_token, send_mail


DEFAULT_COUNTRY = "Португалия"
DEFAULT_TYPE = "services"
DEFAULT_SERVICE = "OLX"
DEFAULT_VERSION = "2.0"
DEFAULT_MAIL_SERVICE = "hype"

PROVIDER_OPTIONS = [
    ("Polya", "polya"),
    ("Grizzly", "grizzly"),
    ("Hype", "hype"),
    ("Your", "your"),
    ("Meow", "meow"),
    ("Gosu", "gosu"),
]

VERSION_OPTIONS = ["1.0", "2.0"]


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


def _normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def _clear_redscript_flow(context: ContextTypes.DEFAULT_TYPE) -> None:
    keys = [
        "awaiting_redscript_api_token",
        "awaiting_redscript_initials",
        "awaiting_redscript_address",
        "awaiting_redscript_ad_url",
        "awaiting_redscript_send_email",
        "redscript_send_payload",
        "redscript_prompt_message_id",
        "redscript_send_in_progress",
        "redscript_last_send_key",
    ]
    for key in keys:
        context.user_data.pop(key, None)


def _get_user_settings(user: dict) -> dict:
    return {
        "access_token": (user.get("redscript_access_token") or "").strip(),
        "initials": (user.get("redscript_initials") or "").strip(),
        "address": (user.get("redscript_address") or "").strip(),
        "mail_service": (user.get("redscript_mail_service") or DEFAULT_MAIL_SERVICE).strip(),
        "country": (user.get("redscript_country") or DEFAULT_COUNTRY).strip(),
        "type": DEFAULT_TYPE,
        "service": (user.get("redscript_service") or DEFAULT_SERVICE).strip(),
        "version": (user.get("redscript_version") or DEFAULT_VERSION).strip(),
    }


def _status_mark(value: str) -> str:
    return "✅" if (value or "").strip() else "▫️"


def _provider_label(settings: dict) -> str:
    value = (settings.get("mail_service") or "").strip()
    for title, slug in PROVIDER_OPTIONS:
        if value.lower() == slug.lower():
            return title
    return value or "не выбран"


def _build_redscript_menu_keyboard(has_token: bool) -> InlineKeyboardMarkup:
    rows = []

    if has_token:
        rows.append([InlineKeyboardButton("✉️ Отправить письмо", callback_data="redscript:send")])
        rows.append([InlineKeyboardButton("🔎 Проверить API", callback_data="redscript:check")])
        rows.append([InlineKeyboardButton("🧑 Настройки покупателя", callback_data="redscript:settings")])
        rows.append([InlineKeyboardButton("🔑 Изменить API", callback_data="redscript:set_token")])
    else:
        rows.append([InlineKeyboardButton("🔑 Подключить API", callback_data="redscript:set_token")])

    rows.append([InlineKeyboardButton("⬅️ Вернуться в главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)


def _build_sender_settings_keyboard(settings: dict) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"Имя/инициалы {_status_mark(settings['initials'])}",
                callback_data="redscript:set_initials",
            ),
            InlineKeyboardButton(
                f"Адрес {_status_mark(settings['address'])}",
                callback_data="redscript:set_address",
            ),
        ],
        [
            InlineKeyboardButton(
                f"Провайдер {_status_mark(settings['mail_service'])}",
                callback_data="redscript:set_mail_service",
            ),
            InlineKeyboardButton(
                f"Сервис {_status_mark(settings['service'])}",
                callback_data="redscript:set_service",
            ),
        ],
        [
            InlineKeyboardButton(
                f"Версия {_status_mark(settings['version'])}",
                callback_data="redscript:set_version",
            ),
        ],
        [
            InlineKeyboardButton("⬅️ Назад", callback_data="redscript:menu"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def _build_provider_keyboard(current_value: str) -> InlineKeyboardMarkup:
    rows = []
    pair = []
    for title, slug in PROVIDER_OPTIONS:
        label = f"{'✅ ' if current_value.lower() == slug.lower() else ''}{title}"
        pair.append(InlineKeyboardButton(label, callback_data=f"redscript:provider:{slug}"))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="redscript:settings")])
    return InlineKeyboardMarkup(rows)


def _build_version_keyboard(current_value: str) -> InlineKeyboardMarkup:
    pair = []
    for version in VERSION_OPTIONS:
        label = f"{'✅ ' if current_value == version else ''}{version}"
        pair.append(InlineKeyboardButton(label, callback_data=f"redscript:version:{version}"))
    return InlineKeyboardMarkup([
        pair,
        [InlineKeyboardButton("⬅️ Назад", callback_data="redscript:settings")],
    ])


def _build_service_keyboard(current_value: str) -> InlineKeyboardMarkup:
    label = f"{'✅ ' if (current_value or '').lower() == 'olx' else ''}OLX"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data="redscript:service:OLX")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="redscript:settings")],
    ])


async def _safe_delete_message(bot, chat_id: int, message_id: int | None) -> None:
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def _store_prompt_message_id(context: ContextTypes.DEFAULT_TYPE, message_id: int | None) -> None:
    context.user_data["redscript_prompt_message_id"] = message_id


async def _delete_prompt_and_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await _safe_delete_message(context.bot, update.effective_chat.id, update.message.message_id)
    await _safe_delete_message(
        context.bot,
        update.effective_chat.id,
        context.user_data.get("redscript_prompt_message_id"),
    )
    context.user_data.pop("redscript_prompt_message_id", None)


async def show_redscript_screen(update_or_query, user_id: int):
    user = get_user_by_id(user_id)
    settings = _get_user_settings(user or {})
    has_token = bool(settings["access_token"])

    text = (
        "📨 Отправка письма\n\n"
        f"API: {_mask_token(settings['access_token'])}\n"
        f"Покупатель: {settings['initials'] or 'не задан'}\n"
        f"Провайдер: {_provider_label(settings)}"
    )

    keyboard = _build_redscript_menu_keyboard(has_token)

    if hasattr(update_or_query, "edit_message_text"):
        await update_or_query.edit_message_text(text, reply_markup=keyboard)
    else:
        await update_or_query.message.reply_text(text, reply_markup=keyboard)


async def show_sender_settings_screen(query, user_id: int):
    user = get_user_by_id(user_id)
    settings = _get_user_settings(user or {})
    await query.edit_message_text(
        "🧑 Настройки покупателя",
        reply_markup=_build_sender_settings_keyboard(settings),
    )


async def _send_sender_settings_screen_to_chat(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    user = get_user_by_id(user_id)
    settings = _get_user_settings(user or {})
    await update.message.reply_text(
        "🧑 Настройки покупателя",
        reply_markup=_build_sender_settings_keyboard(settings),
    )


async def _send_redscript_screen_to_chat(update: Update, user_id: int):
    user = get_user_by_id(user_id)
    settings = _get_user_settings(user or {})
    has_token = bool(settings["access_token"])

    text = (
        "📨 Отправка письма\n\n"
        f"API: {_mask_token(settings['access_token'])}\n"
        f"Покупатель: {settings['initials'] or 'не задан'}\n"
        f"Провайдер: {_provider_label(settings)}"
    )

    await update.message.reply_text(
        text,
        reply_markup=_build_redscript_menu_keyboard(has_token),
    )


def _build_send_dedupe_key(payload: dict, settings: dict) -> str:
    return "|".join(
        [
            _normalize_email(payload.get("email")),
            str(payload.get("ad_url") or "").strip(),
            str(payload.get("name") or "").strip(),
            str(payload.get("amount") or "").strip(),
            str(settings.get("mail_service") or "").strip().lower(),
            str(settings.get("service") or "").strip().lower(),
            str(settings.get("version") or "").strip(),
            str(payload.get("country") or settings.get("country") or "").strip(),
        ]
    )


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
        msg = await query.edit_message_text(
            "🔑 Подключение API\n\n"
            "Пришли свой access_token одним сообщением.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="redscript:menu")]
            ]),
        )
        await _store_prompt_message_id(context, getattr(msg, "message_id", None) or query.message.message_id)
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
            await check_token(token)
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
        await show_sender_settings_screen(query, user_id)
        return

    if data == "redscript:set_initials":
        _clear_redscript_flow(context)
        context.user_data["awaiting_redscript_initials"] = True

        user = get_user_by_id(user_id)
        settings = _get_user_settings(user or {})
        current_value = settings["initials"] or "не указано"

        msg = await query.edit_message_text(
            "✍️ Введи имя / инициалы покупателя.\n\n"
            f"Сейчас стоит: {current_value}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="redscript:settings")]
            ]),
        )
        await _store_prompt_message_id(context, getattr(msg, "message_id", None) or query.message.message_id)
        return

    if data == "redscript:set_address":
        _clear_redscript_flow(context)
        context.user_data["awaiting_redscript_address"] = True

        user = get_user_by_id(user_id)
        settings = _get_user_settings(user or {})
        current_value = settings["address"] or "не указано"

        msg = await query.edit_message_text(
            "📍 Введи адрес покупателя.\n\n"
            f"Сейчас стоит: {current_value}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="redscript:settings")]
            ]),
        )
        await _store_prompt_message_id(context, getattr(msg, "message_id", None) or query.message.message_id)
        return

    if data == "redscript:set_mail_service":
        _clear_redscript_flow(context)
        user = get_user_by_id(user_id)
        settings = _get_user_settings(user or {})
        await query.edit_message_text(
            "📨 Выбери сервис для отправки.",
            reply_markup=_build_provider_keyboard(settings["mail_service"]),
        )
        return

    if data.startswith("redscript:provider:"):
        provider = data.split(":", 2)[2].strip()
        update_user_redscript_defaults(user_id, mail_service=provider)
        await show_sender_settings_screen(query, user_id)
        return

    if data == "redscript:set_version":
        _clear_redscript_flow(context)
        user = get_user_by_id(user_id)
        settings = _get_user_settings(user or {})
        await query.edit_message_text(
            "🧩 Выбери версию.",
            reply_markup=_build_version_keyboard(settings["version"]),
        )
        return

    if data.startswith("redscript:version:"):
        version = data.split(":", 2)[2].strip()
        update_user_redscript_defaults(user_id, version=version)
        await show_sender_settings_screen(query, user_id)
        return

    if data == "redscript:set_service":
        _clear_redscript_flow(context)
        user = get_user_by_id(user_id)
        settings = _get_user_settings(user or {})
        await query.edit_message_text(
            "🛍 Выбери сервис.",
            reply_markup=_build_service_keyboard(settings["service"]),
        )
        return

    if data.startswith("redscript:service:"):
        service_value = data.split(":", 2)[2].strip()
        update_user_redscript_defaults(user_id, service=service_value)
        await show_sender_settings_screen(query, user_id)
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
        msg = await query.edit_message_text(
            "✉️ Отправка письма\n\n"
            "Пришли ссылку на объявление OLX PT.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="redscript:menu")]
            ]),
        )
        await _store_prompt_message_id(context, getattr(msg, "message_id", None) or query.message.message_id)
        return


async def handle_redscript_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    current_user = context.user_data.get("current_user") or {}
    user_id = current_user.get("id")
    if not user_id:
        await update.message.reply_text("Пользователь не найден.")
        return

    if context.user_data.get("awaiting_redscript_api_token"):
        token = text.strip()

        try:
            await check_token(token)
        except RedScriptApiError as exc:
            await update.message.reply_text(
                f"Ошибка проверки API:\n{exc}"
            )
            return

        update_user_redscript_token(user_id, token)
        _clear_redscript_flow(context)
        await _delete_prompt_and_user_message(update, context)
        await _send_redscript_screen_to_chat(update, user_id)
        return

    if context.user_data.get("awaiting_redscript_initials"):
        update_user_redscript_defaults(user_id, initials=text.strip())
        _clear_redscript_flow(context)
        await _delete_prompt_and_user_message(update, context)
        await _send_sender_settings_screen_to_chat(update, context, user_id)
        return

    if context.user_data.get("awaiting_redscript_address"):
        update_user_redscript_defaults(user_id, address=text.strip())
        _clear_redscript_flow(context)
        await _delete_prompt_and_user_message(update, context)
        await _send_sender_settings_screen_to_chat(update, context, user_id)
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
                f"Ошибка парсинга объявления:\n{parse_result.get('error') or parse_result.get('status')}"
            )
            return

        payload = {
            "ad_url": ad_url,
            "name": parse_result.get("title"),
            "amount": parse_result.get("amount"),
            "image": parse_result.get("image"),
            "country": "Португалия",
        }
        context.user_data["redscript_send_payload"] = payload
        context.user_data["awaiting_redscript_send_email"] = True

        await update.message.reply_text(
            "📦 Объявление найдено\n\n"
            f"Название: {payload.get('name') or '—'}\n"
            f"Сумма: {payload.get('amount') or '—'}\n"
            f"Фото: {'есть' if payload.get('image') else 'нет'}\n\n"
            "Теперь пришли почту продавца.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="redscript:menu")]
            ]),
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
        await update.message.reply_text("Сначала подключи API ключ.")
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
            "Сначала заполни данные покупателя:\n- " + "\n- ".join(missing_fields)
        )
        return

    safe_name = _sanitize_redscript_name(payload.get("name"))
    if not safe_name:
        _clear_redscript_flow(context)
        context.user_data.pop("redscript_send_payload", None)
        await update.message.reply_text(
            "Не удалось подготовить название объявления для отправки."
        )
        return

    actual_country = (payload.get("country") or settings["country"] or DEFAULT_COUNTRY).strip()
    actual_type = DEFAULT_TYPE

    dedupe_key = _build_send_dedupe_key(payload, settings)

    if context.user_data.get("redscript_send_in_progress"):
        await update.message.reply_text(
            "⏳ Отправка уже выполняется.\n\n"
            "Дождись результата текущего запроса и не отправляй письмо повторно."
        )
        return

    if context.user_data.get("redscript_last_send_key") == dedupe_key:
        await update.message.reply_text(
            "⏳ Такой запрос уже был отправлен недавно.\n\n"
            "Не запускай повторно тот же кейс подряд."
        )
        return

    debug_payload = {
        "email": payload.get("email") or "",
        "mail_service": settings["mail_service"] or DEFAULT_MAIL_SERVICE,
        "country": actual_country,
        "type": actual_type,
        "service": settings["service"] or DEFAULT_SERVICE,
        "version": settings["version"] or DEFAULT_VERSION,
        "name": safe_name,
        "amount": payload.get("amount") or "",
        "image": (payload.get("image") or "").strip() or None,
        "initials": settings["initials"] or None,
        "address": settings["address"] or None,
    }
    print(f"[redscript_handler] send_mail payload={debug_payload}")

    context.user_data["redscript_send_in_progress"] = True
    context.user_data["redscript_last_send_key"] = dedupe_key

    try:
        result = await send_mail(
            token,
            email=payload.get("email") or "",
            mail_service=settings["mail_service"] or DEFAULT_MAIL_SERVICE,
            country=actual_country,
            type_value=actual_type,
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

        if exc.is_ambiguous_success:
            await update.message.reply_text(
                "⏳ Отправка не подтверждена\n\n"
                "Сообщение, вероятно, уже отправлено, но сервис не успел вернуть итоговый ответ.\n\n"
                "Не отправляйте повторно сразу."
            )
            return

        full_error = str(exc)
        if getattr(exc, "raw_text", ""):
            full_error += f"\n\nRAW: {exc.raw_text[:3000]}"

        await update.message.reply_text(
            f"Ошибка отправки письма:\n{full_error}"
        )
        return

    _clear_redscript_flow(context)
    context.user_data.pop("redscript_send_payload", None)

    await update.message.reply_text("✅ Письмо отправлено.")