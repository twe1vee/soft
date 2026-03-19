from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from db import (
    create_proxies_bulk,
    get_proxy_by_id,
    get_user_proxies,
    mark_proxy_checked,
    delete_proxy,
)
from telegram_ui.handlers.common import get_current_user


def build_proxies_keyboard(proxies: list[dict]) -> InlineKeyboardMarkup:
    keyboard = []

    for index, proxy in enumerate(proxies, start=1):
        status = proxy.get("status", "unknown")
        proxy_text = proxy.get("proxy_text", "")

        short_proxy = proxy_text
        if len(short_proxy) > 35:
            short_proxy = short_proxy[:35] + "..."

        keyboard.append([
            InlineKeyboardButton(
                f"{index}. {short_proxy} [{status}]",
                callback_data=f"proxy:open:{proxy['id']}",
            )
        ])

    keyboard.append([
        InlineKeyboardButton("➕ Добавить прокси", callback_data="proxy:add")
    ])
    keyboard.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")
    ])

    return InlineKeyboardMarkup(keyboard)


def build_proxy_card_keyboard(proxy_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Проверить прокси", callback_data=f"proxy:check:{proxy_id}")],
        [InlineKeyboardButton("🗑 Удалить прокси", callback_data=f"proxy:delete:{proxy_id}")],
        [InlineKeyboardButton("⬅️ Назад к прокси", callback_data="menu:proxies")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
    ])


def build_proxy_delete_confirm_keyboard(proxy_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"proxy:confirm_delete:{proxy_id}")],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"proxy:open:{proxy_id}")],
    ])


def parse_proxy_lines(text: str) -> list[str]:
    proxies = []
    seen = set()

    for raw_line in text.splitlines():
        value = raw_line.strip()
        if not value:
            continue

        if value in seen:
            continue

        seen.add(value)
        proxies.append(value)

    return proxies


async def show_proxies_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    current_user = get_current_user(update)
    user_id = current_user["id"]

    proxies = get_user_proxies(user_id)

    if proxies:
        text = "🌐 Прокси\n\n"

        for index, proxy in enumerate(proxies, start=1):
            proxy_text = proxy.get("proxy_text", "")
            status = proxy.get("status", "unknown")

            short_proxy = proxy_text
            if len(short_proxy) > 45:
                short_proxy = short_proxy[:45] + "..."

            text += f"{index}. {short_proxy} — {status}\n"
    else:
        text = (
            "🌐 Прокси\n\n"
            "У тебя пока нет добавленных прокси.\n\n"
            "Нажми «Добавить прокси», чтобы загрузить список."
        )

    await query.edit_message_text(
        text=text,
        reply_markup=build_proxies_keyboard(proxies),
    )


async def show_proxy_card(query, user_id: int, proxy_id: int):
    proxy = get_proxy_by_id(user_id, proxy_id)

    if not proxy:
        await query.edit_message_text(
            "Прокси не найден.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад к прокси", callback_data="menu:proxies")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
            ]),
        )
        return

    proxy_text = proxy.get("proxy_text", "")
    status = proxy.get("status", "unknown")
    last_check_at = proxy.get("last_check_at") or "ещё не проверялся"

    await query.edit_message_text(
        "🌐 Карточка прокси\n\n"
        f"ID: {proxy['id']}\n"
        f"Прокси: {proxy_text}\n"
        f"Статус: {status}\n"
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

        await query.edit_message_text(
            "➕ Добавление прокси\n\n"
            "Пришли прокси одним из способов:\n"
            "1. текстом в сообщении\n"
            "2. несколькими строками\n"
            "3. .txt файлом\n\n"
            "Формат строки:\n"
            "ip:port:login:password",
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
            await query.edit_message_text(
                "Прокси не найден.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Назад к прокси", callback_data="menu:proxies")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
                ]),
            )
            return

        mark_proxy_checked(user_id, proxy_id, status="working")
        await show_proxy_card(query, user_id, proxy_id)
        return

    if data.startswith("proxy:delete:"):
        proxy_id = int(data.split(":")[-1])

        proxy = get_proxy_by_id(user_id, proxy_id)
        if not proxy:
            await query.edit_message_text(
                "Прокси не найден.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Назад к прокси", callback_data="menu:proxies")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
                ]),
            )
            return

        await query.edit_message_text(
            f"Ты точно хочешь удалить прокси ID {proxy_id}?",
            reply_markup=build_proxy_delete_confirm_keyboard(proxy_id),
        )
        return

    if data.startswith("proxy:confirm_delete:"):
        proxy_id = int(data.split(":")[-1])

        proxy = get_proxy_by_id(user_id, proxy_id)
        if not proxy:
            await query.edit_message_text(
                "Прокси уже не найден.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Назад к прокси", callback_data="menu:proxies")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
                ]),
            )
            return

        delete_proxy(user_id, proxy_id)

        proxies = get_user_proxies(user_id)

        if proxies:
            text = "✅ Прокси удалён.\n\nОставшиеся прокси:\n\n"
            for index, item in enumerate(proxies, start=1):
                proxy_text = item.get("proxy_text", "")
                status = item.get("status", "unknown")

                short_proxy = proxy_text
                if len(short_proxy) > 45:
                    short_proxy = short_proxy[:45] + "..."

                text += f"{index}. {short_proxy} — {status}\n"
        else:
            text = "✅ Прокси удалён.\n\nУ тебя больше нет добавленных прокси."

        await query.edit_message_text(
            text=text,
            reply_markup=build_proxies_keyboard(proxies),
        )
        return


async def save_new_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE, proxy_lines: list[str]):
    current_user = get_current_user(update)
    user_id = current_user["id"]

    inserted_count = create_proxies_bulk(user_id, proxy_lines)
    context.user_data.pop("awaiting_proxies", None)

    proxies = get_user_proxies(user_id)

    text_lines = [
        "✅ Прокси успешно добавлены.\n",
        f"Добавлено новых прокси: {inserted_count}\n",
        "Текущий список прокси:\n",
    ]

    for index, proxy in enumerate(proxies, start=1):
        proxy_text = proxy.get("proxy_text", "")
        status = proxy.get("status", "unknown")

        short_proxy = proxy_text
        if len(short_proxy) > 45:
            short_proxy = short_proxy[:45] + "..."

        text_lines.append(f"{index}. {short_proxy} — {status}")

    if update.message:
        await update.message.reply_text(
            "\n".join(text_lines),
            reply_markup=build_proxies_keyboard(proxies),
        )


async def handle_proxies_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    proxy_lines = parse_proxy_lines(text)

    if not proxy_lines:
        await update.message.reply_text(
            "Не удалось найти ни одной строки прокси.\n\n"
            "Пришли прокси по одному в строке.\n"
            "Формат: ip:port:login:password"
        )
        return

    await save_new_proxies(update, context, proxy_lines)


async def handle_proxies_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.document:
        return

    document = update.message.document

    if document.file_name and not document.file_name.lower().endswith(".txt"):
        await update.message.reply_text(
            "Поддерживается только .txt файл со списком прокси."
        )
        return

    file = await document.get_file()
    file_bytes = await file.download_as_bytearray()

    try:
        text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        await update.message.reply_text(
            "Не удалось прочитать файл как UTF-8 текст.\n\n"
            "Сохрани список прокси в обычный .txt файл в UTF-8."
        )
        return

    proxy_lines = parse_proxy_lines(text)

    if not proxy_lines:
        await update.message.reply_text(
            "Файл прочитан, но внутри не найдено строк с прокси."
        )
        return

    await save_new_proxies(update, context, proxy_lines)