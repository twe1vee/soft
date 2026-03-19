import json

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from db import (
    create_account,
    get_account_by_id,
    get_user_accounts,
    update_account_cookies,
    mark_account_checked,
    delete_account,
)
from telegram_ui.handlers.common import get_current_user


def build_accounts_keyboard(accounts: list[dict]) -> InlineKeyboardMarkup:
    keyboard = []

    for index, account in enumerate(accounts, start=1):
        profile_name = account.get("olx_profile_name") or "без имени"
        status = account.get("status", "unknown")

        keyboard.append([
            InlineKeyboardButton(
                f"{index}. {profile_name} [{status}]",
                callback_data=f"account:open:{account['id']}",
            )
        ])

    keyboard.append([
        InlineKeyboardButton("➕ Добавить аккаунт", callback_data="account:add")
    ])
    keyboard.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")
    ])

    return InlineKeyboardMarkup(keyboard)


def build_account_card_keyboard(account_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Проверить аккаунт", callback_data=f"account:check:{account_id}")],
        [InlineKeyboardButton("♻️ Обновить cookies", callback_data=f"account:update_cookies:{account_id}")],
        [InlineKeyboardButton("🗑 Удалить аккаунт", callback_data=f"account:delete:{account_id}")],
        [InlineKeyboardButton("⬅️ Назад к аккаунтам", callback_data="menu:account")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
    ])


def build_account_delete_confirm_keyboard(account_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"account:confirm_delete:{account_id}")],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"account:open:{account_id}")],
    ])


def parse_cookies_json(text: str) -> str | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, (list, dict)):
        return None

    return json.dumps(parsed, ensure_ascii=False)


async def show_accounts_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    current_user = get_current_user(update)
    user_id = current_user["id"]

    accounts = get_user_accounts(user_id)

    if accounts:
        text = "👤 Аккаунты OLX\n\n"

        for index, account in enumerate(accounts, start=1):
            profile_name = account.get("olx_profile_name") or "без имени"
            status = account.get("status", "unknown")

            text += f"{index}. {profile_name} — {status}\n"
    else:
        text = (
            "👤 Аккаунты OLX\n\n"
            "У тебя пока нет добавленных аккаунтов.\n\n"
            "Нажми «Добавить аккаунт», чтобы загрузить cookies."
        )

    await query.edit_message_text(
        text=text,
        reply_markup=build_accounts_keyboard(accounts),
    )


async def show_account_card(query, user_id: int, account_id: int):
    account = get_account_by_id(user_id, account_id)

    if not account:
        await query.edit_message_text(
            "Аккаунт не найден.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад к аккаунтам", callback_data="menu:account")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
            ]),
        )
        return

    profile_name = account.get("olx_profile_name") or "без имени"
    status = account.get("status", "unknown")
    last_check_at = account.get("last_check_at") or "ещё не проверялся"

    await query.edit_message_text(
        "👤 Карточка аккаунта\n\n"
        f"ID: {account['id']}\n"
        f"Имя профиля: {profile_name}\n"
        f"Статус: {status}\n"
        f"Последняя проверка: {last_check_at}",
        reply_markup=build_account_card_keyboard(account_id),
    )


async def handle_account_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    query = update.callback_query

    current_user = get_current_user(update)
    user_id = current_user["id"]

    if data == "account:add":
        context.user_data.clear()
        context.user_data["awaiting_account_cookies"] = True

        await query.edit_message_text(
            "➕ Добавление аккаунта\n\n"
            "Пришли cookies одним из способов:\n"
            "1. JSON текстом в сообщении\n"
            "2. .txt файлом с JSON внутри\n\n"
            "После получения я сохраню новый аккаунт в базу со статусом new.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад к аккаунтам", callback_data="menu:account")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
            ]),
        )
        return

    if data.startswith("account:open:"):
        account_id = int(data.split(":")[-1])
        await show_account_card(query, user_id, account_id)
        return

    if data.startswith("account:check:"):
        account_id = int(data.split(":")[-1])

        account = get_account_by_id(user_id, account_id)
        if not account:
            await query.edit_message_text(
                "Аккаунт не найден.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Назад к аккаунтам", callback_data="menu:account")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
                ]),
            )
            return

        mark_account_checked(user_id, account_id)
        await show_account_card(query, user_id, account_id)
        return

    if data.startswith("account:update_cookies:"):
        account_id = int(data.split(":")[-1])

        account = get_account_by_id(user_id, account_id)
        if not account:
            await query.edit_message_text(
                "Аккаунт не найден.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Назад к аккаунтам", callback_data="menu:account")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
                ]),
            )
            return

        context.user_data.clear()
        context.user_data["awaiting_account_cookies_update"] = account_id

        await query.edit_message_text(
            "♻️ Обновление cookies\n\n"
            "Пришли новые cookies:\n"
            "1. JSON текстом\n"
            "2. .txt файлом\n\n"
            f"Я обновлю cookies у аккаунта ID {account_id}.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад к аккаунту", callback_data=f"account:open:{account_id}")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
            ]),
        )
        return

    if data.startswith("account:delete:"):
        account_id = int(data.split(":")[-1])

        account = get_account_by_id(user_id, account_id)
        if not account:
            await query.edit_message_text(
                "Аккаунт не найден.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Назад к аккаунтам", callback_data="menu:account")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
                ]),
            )
            return

        await query.edit_message_text(
            f"Ты точно хочешь удалить аккаунт ID {account_id}?",
            reply_markup=build_account_delete_confirm_keyboard(account_id),
        )
        return

    if data.startswith("account:confirm_delete:"):
        account_id = int(data.split(":")[-1])

        account = get_account_by_id(user_id, account_id)
        if not account:
            await query.edit_message_text(
                "Аккаунт уже не найден.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Назад к аккаунтам", callback_data="menu:account")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
                ]),
            )
            return

        delete_account(user_id, account_id)

        accounts = get_user_accounts(user_id)

        if accounts:
            text = "✅ Аккаунт удалён.\n\nОставшиеся аккаунты:\n\n"
            for index, item in enumerate(accounts, start=1):
                profile_name = item.get("olx_profile_name") or "без имени"
                status = item.get("status", "unknown")
                text += f"{index}. {profile_name} — {status}\n"
        else:
            text = "✅ Аккаунт удалён.\n\nУ тебя больше нет добавленных аккаунтов."

        await query.edit_message_text(
            text=text,
            reply_markup=build_accounts_keyboard(accounts),
        )
        return


async def save_new_account_from_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE, cookies_json: str):
    current_user = get_current_user(update)
    user_id = current_user["id"]

    account_id = create_account(
        user_id=user_id,
        cookies_json=cookies_json,
        status="new",
        olx_profile_name=None,
    )

    context.user_data.pop("awaiting_account_cookies", None)

    accounts = get_user_accounts(user_id)

    text_lines = [
        "✅ Аккаунт успешно добавлен.\n",
        f"ID нового аккаунта: {account_id}\n",
        "Текущий список аккаунтов:\n",
    ]

    for index, account in enumerate(accounts, start=1):
        profile_name = account.get("olx_profile_name") or "без имени"
        status = account.get("status", "unknown")
        text_lines.append(f"{index}. {profile_name} — {status}")

    if update.message:
        await update.message.reply_text(
            "\n".join(text_lines),
            reply_markup=build_accounts_keyboard(accounts),
        )


async def update_existing_account_cookies(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    account_id: int,
    cookies_json: str,
):
    current_user = get_current_user(update)
    user_id = current_user["id"]

    account = get_account_by_id(user_id, account_id)
    if not account:
        context.user_data.pop("awaiting_account_cookies_update", None)
        await update.message.reply_text("Аккаунт не найден.")
        return

    update_account_cookies(user_id, account_id, cookies_json)
    context.user_data.pop("awaiting_account_cookies_update", None)

    updated_account = get_account_by_id(user_id, account_id)
    profile_name = updated_account.get("olx_profile_name") or "без имени"
    status = updated_account.get("status", "unknown")
    last_check_at = updated_account.get("last_check_at") or "ещё не проверялся"

    await update.message.reply_text(
        "✅ Cookies обновлены.\n\n"
        f"ID: {updated_account['id']}\n"
        f"Имя профиля: {profile_name}\n"
        f"Статус: {status}\n"
        f"Последняя проверка: {last_check_at}",
        reply_markup=build_account_card_keyboard(account_id),
    )


async def handle_account_cookies_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    cookies_json = parse_cookies_json(text)

    if not cookies_json:
        await update.message.reply_text(
            "Не удалось распознать cookies как JSON.\n\n"
            "Пришли cookies одним сообщением в JSON-формате "
            "или .txt файлом с JSON внутри."
        )
        return

    updating_account_id = context.user_data.get("awaiting_account_cookies_update")
    if updating_account_id:
        await update_existing_account_cookies(update, context, updating_account_id, cookies_json)
        return

    await save_new_account_from_cookies(update, context, cookies_json)


async def handle_account_cookies_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.document:
        return

    document = update.message.document

    if document.file_name and not document.file_name.lower().endswith(".txt"):
        await update.message.reply_text(
            "Поддерживается только .txt файл с JSON cookies внутри."
        )
        return

    file = await document.get_file()
    file_bytes = await file.download_as_bytearray()

    try:
        text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        await update.message.reply_text(
            "Не удалось прочитать файл как UTF-8 текст.\n\n"
            "Сохрани cookies в обычный .txt файл в UTF-8."
        )
        return

    cookies_json = parse_cookies_json(text)

    if not cookies_json:
        await update.message.reply_text(
            "Файл прочитан, но внутри невалидный JSON.\n\n"
            "Проверь содержимое .txt файла."
        )
        return

    updating_account_id = context.user_data.get("awaiting_account_cookies_update")
    if updating_account_id:
        await update_existing_account_cookies(update, context, updating_account_id, cookies_json)
        return

    await save_new_account_from_cookies(update, context, cookies_json)