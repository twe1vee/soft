from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from db import (
    create_proxies_bulk,
    delete_proxy,
    get_proxy_by_id,
    get_user_proxies,
    update_proxy_last_check,
    update_proxy_status,
)
from olx.proxy_check import check_proxy_alive
from telegram_ui.handlers.common import get_current_user


def proxy_short(proxy_text: str, max_len: int = 45) -> str:
    value = (proxy_text or "").strip()
    if not value:
        return ""

    lower = value.lower()
    if "://" in lower:
        value = value.split("://", 1)[1]

    if "@" in value:
        right = value.rsplit("@", 1)[1].strip()
        if right:
            return right[:max_len] if len(right) > max_len else right

    parts = [p.strip() for p in value.split(":")]

    # host:port:user:pass -> host:port
    if len(parts) >= 2:
        host = parts[0]
        port = parts[1]
        host_port = f"{host}:{port}"
        return host_port[:max_len] if len(host_port) > max_len else host_port

    return value[:max_len] if len(value) > max_len else value


def humanize_proxy_status(status: str | None) -> str:
    value = (status or "").strip().lower()

    if value in {"working", "connected", "checked"}:
        return "живой"

    if value in {"timeout"}:
        return "timeout"

    if value in {"unstable"}:
        return "нестабильный"

    if value in {"cloudfront_blocked"}:
        return "заблокирован olx"

    if value in {"proxy_failed"}:
        return "ошибка прокси"

    if value in {"failed", "dead"}:
        return "ошибка проверки"

    return "не проверен"


def normalize_proxy_status_for_db(raw_status: str | None) -> str:
    value = (raw_status or "").strip().lower()

    allowed_statuses = {
        "working",
        "timeout",
        "unstable",
        "cloudfront_blocked",
        "proxy_failed",
        "failed",
    }

    if value in allowed_statuses:
        return value

    return "failed"


async def safe_edit_message_text(query, text: str, reply_markup=None, **kwargs):
    try:
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            **kwargs,
        )
    except BadRequest as e:
        if "Message is not modified" in str(e):
            return
        raise


def build_proxies_keyboard(proxies: list[dict]) -> InlineKeyboardMarkup:
    keyboard = []

    for index, proxy in enumerate(proxies, start=1):
        ui_status = humanize_proxy_status(proxy.get("status"))
        short_proxy = proxy_short(proxy.get("proxy_text", ""), max_len=35)
        keyboard.append([
            InlineKeyboardButton(
                f"{index}. {short_proxy} [{ui_status}]",
                callback_data=f"proxy:open:{proxy['id']}",
            )
        ])

    keyboard.append([InlineKeyboardButton("➕ Добавить прокси", callback_data="proxy:add")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")])

    return InlineKeyboardMarkup(keyboard)


def build_proxy_card_keyboard(proxy_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 Проверить прокси", callback_data=f"proxy:check:{proxy_id}")],
        [InlineKeyboardButton("🗑 Удалить прокси", callback_data=f"proxy:delete:{proxy_id}")],
        [InlineKeyboardButton("⬅️ Назад к прокси", callback_data="menu:proxies")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
    ])


def build_proxy_delete_confirm_keyboard(proxy_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"proxy:confirm_delete:{proxy_id}")],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"proxy:open:{proxy_id}")],
    ])


async def show_proxies_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    current_user = get_current_user(update)
    user_id = current_user["id"]

    proxies = get_user_proxies(user_id)

    if proxies:
        text = "📡 Прокси\n\n"
    else:
        text = (
            "📡 Прокси\n\n"
            "У тебя пока нет добавленных прокси.\n\n"
            "Нажми «Добавить прокси», чтобы загрузить список."
        )

    await safe_edit_message_text(
        query,
        text=text,
        reply_markup=build_proxies_keyboard(proxies),
    )


async def show_proxy_card(query, user_id: int, proxy_id: int):
    proxy = get_proxy_by_id(user_id, proxy_id)

    if not proxy:
        await safe_edit_message_text(
            query,
            "Прокси не найден.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад к прокси", callback_data="menu:proxies")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
            ]),
        )
        return

    ui_status = humanize_proxy_status(proxy.get("status"))
    last_check_at = proxy.get("last_check_at") or "ещё не проверялся"

    await safe_edit_message_text(
        query,
        "📄 Карточка прокси\n\n"
        f"Прокси: {proxy_short(proxy.get('proxy_text'))}\n"
        f"Статус: {ui_status}\n\n"
        f"Последняя проверка: {last_check_at}",
        reply_markup=build_proxy_card_keyboard(proxy_id),
    )


async def handle_proxy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    query = update.callback_query
    current_user = get_current_user(update)
    user_id = current_user["id"]

    if data == "proxy:add":
        context.user_data.clear()
        context.user_data["awaiting_proxies"] = True

        await safe_edit_message_text(
            query,
            "➕ Добавление прокси\n\n"
            "Пришли список прокси:\n"
            "1. текстом — каждый с новой строки\n"
            "2. .txt файлом\n\n"
            "Поддерживаются форматы:\n"
            "- host:port\n"
            "- host:port:user:pass\n"
            "- http://user:pass@host:port\n"
            "- socks5://user:pass@host:port",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад к прокси", callback_data="menu:proxies")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
            ]),
        )
        return

    if data.startswith("proxy:open:"):
        proxy_id = int(data.split(":")[-1])
        await show_proxy_card(query, user_id, proxy_id)
        return

    if data.startswith("proxy:check:"):
        proxy_id = int(data.split(":")[-1])
        proxy = get_proxy_by_id(user_id, proxy_id)

        if not proxy:
            await safe_edit_message_text(
                query,
                "Прокси не найден.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Назад к прокси", callback_data="menu:proxies")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
                ]),
            )
            return

        await safe_edit_message_text(
            query,
            "⏳ Проверяю прокси через GoLogin profile launch...\n\n"
            f"Прокси: {proxy_short(proxy.get('proxy_text', ''), max_len=50)}"
        )

        result = await check_proxy_alive(
            proxy_text=proxy["proxy_text"],
            headless=True,
        )

        update_proxy_last_check(user_id, proxy_id)

        result_status = normalize_proxy_status_for_db(result.get("status"))
        update_proxy_status(user_id, proxy_id, result_status)

        updated_proxy = get_proxy_by_id(user_id, proxy_id)
        ui_status = humanize_proxy_status(updated_proxy.get("status"))

        raw_error = (result.get("error") or "").strip()

        human_error = None
        if raw_error:
            lower_error = raw_error.lower()

            if "timeout" in lower_error:
                human_error = "Прокси не ответил вовремя."
            elif "407" in lower_error or "proxy authentication" in lower_error or "auth" in lower_error:
                human_error = "Неверный логин или пароль прокси."
            elif "403" in lower_error:
                human_error = "Доступ через этот прокси был отклонён."
            elif "tunnel" in lower_error:
                human_error = "Не удалось установить соединение через прокси."
            elif "dns" in lower_error or "name resolution" in lower_error:
                human_error = "Не удалось определить адрес прокси."
            elif "connection refused" in lower_error:
                human_error = "Прокси отклонил подключение."
            elif "connection reset" in lower_error:
                human_error = "Соединение через прокси было сброшено."
            elif "network" in lower_error:
                human_error = "Ошибка сети при проверке прокси."
            else:
                human_error = "Прокси не прошёл проверку."

        text_lines = [
            "🔎 Проверка прокси завершена",
            "",
            f"Прокси: {proxy_short(updated_proxy.get('proxy_text', ''), max_len=70)}",
            f"Статус: {ui_status}",
        ]

        if human_error and ui_status != "живой":
            text_lines.extend([
                "",
                f"Причина: {human_error}",
            ])

        await safe_edit_message_text(
            query,
            "\n".join(text_lines),
            reply_markup=build_proxy_card_keyboard(proxy_id),
        )
        return

    if data.startswith("proxy:delete:"):
        proxy_id = int(data.split(":")[-1])
        proxy = get_proxy_by_id(user_id, proxy_id)

        if not proxy:
            await safe_edit_message_text(
                query,
                "Прокси не найден.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Назад к прокси", callback_data="menu:proxies")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
                ]),
            )
            return

        await safe_edit_message_text(
            query,
            f"Ты точно хочешь удалить прокси?\n\n{proxy.get('proxy_text')}",
            reply_markup=build_proxy_delete_confirm_keyboard(proxy_id),
        )
        return

    if data.startswith("proxy:confirm_delete:"):
        proxy_id = int(data.split(":")[-1])

        delete_proxy(user_id, proxy_id)
        proxies = get_user_proxies(user_id)

        if proxies:
            text = "✅ Прокси удалён.\n\nОставшиеся прокси:\n\n"
            for index, proxy in enumerate(proxies, start=1):
                ui_status = humanize_proxy_status(proxy.get("status"))
                text += f"{index}. {proxy_short(proxy.get('proxy_text', ''), max_len=45)} [{ui_status}]\n"
        else:
            text = "✅ Прокси удалён.\n\nСписок прокси теперь пуст."

        await safe_edit_message_text(
            query,
            text,
            reply_markup=build_proxies_keyboard(proxies),
        )
        return


def _parse_proxy_lines(text: str) -> list[str]:
    result = []
    seen = set()

    for line in (text or "").splitlines():
        value = line.strip()
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        result.append(value)

    return result


async def handle_proxies_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    current_user = get_current_user(update)
    user_id = current_user["id"]

    proxy_list = _parse_proxy_lines(text)
    if not proxy_list:
        await update.message.reply_text(
            "❌ Не удалось найти ни одного прокси в сообщении."
        )
        return

    inserted_count = create_proxies_bulk(user_id, proxy_list)
    context.user_data.clear()

    await update.message.reply_text(
        f"✅ Добавлено прокси: {inserted_count}"
    )


async def handle_proxies_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_user = get_current_user(update)
    user_id = current_user["id"]

    document = update.message.document
    if not document:
        return

    file = await document.get_file()
    content = await file.download_as_bytearray()

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        await update.message.reply_text("❌ Файл должен быть в UTF-8.")
        return

    proxy_list = _parse_proxy_lines(text)
    if not proxy_list:
        await update.message.reply_text("❌ Не удалось найти прокси в файле.")
        return

    inserted_count = create_proxies_bulk(user_id, proxy_list)
    context.user_data.clear()

    await update.message.reply_text(
        f"✅ Добавлено прокси: {inserted_count}"
    )