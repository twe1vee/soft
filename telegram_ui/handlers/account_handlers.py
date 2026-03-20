import json

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from db import (
    create_account,
    get_account_by_id,
    get_user_accounts,
    update_account_cookies,
    update_account_status,
    update_account_proxy,
    update_account_last_check,
    delete_account,
    get_user_proxies,
    get_proxy_by_id,
    update_proxy_status,
    update_proxy_last_check,
)
from olx.account_session import check_account_with_proxy
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

    keyboard.append([InlineKeyboardButton("➕ Добавить аккаунт", callback_data="account:add")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")])

    return InlineKeyboardMarkup(keyboard)


def build_account_card_keyboard(account_id: int, has_proxy: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("🔎 Проверить аккаунт", callback_data=f"account:check:{account_id}")],
        [InlineKeyboardButton("🔗 Привязать прокси", callback_data=f"account:bind_proxy:{account_id}")],
    ]

    if has_proxy:
        rows.append([InlineKeyboardButton("❌ Отвязать прокси", callback_data=f"account:clear_proxy:{account_id}")])

    rows.extend([
        [InlineKeyboardButton("♻️ Обновить cookies", callback_data=f"account:update_cookies:{account_id}")],
        [InlineKeyboardButton("🗑 Удалить аккаунт", callback_data=f"account:delete:{account_id}")],
        [InlineKeyboardButton("⬅️ Назад к аккаунтам", callback_data="menu:account")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
    ])

    return InlineKeyboardMarkup(rows)


def build_account_delete_confirm_keyboard(account_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"account:confirm_delete:{account_id}")],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"account:open:{account_id}")],
    ])


def build_account_proxy_select_keyboard(account_id: int, proxies: list[dict]) -> InlineKeyboardMarkup:
    keyboard = []

    for proxy in proxies:
        proxy_text = proxy.get("proxy_text", "")
        status = proxy.get("status", "unknown")
        short_proxy = proxy_text if len(proxy_text) <= 42 else proxy_text[:42] + "..."

        keyboard.append([
            InlineKeyboardButton(
                f"{proxy['id']}. {short_proxy} [{status}]",
                callback_data=f"account:set_proxy:{account_id}:{proxy['id']}",
            )
        ])

    keyboard.append([InlineKeyboardButton("⬅️ Назад к аккаунту", callback_data=f"account:open:{account_id}")])
    return InlineKeyboardMarkup(keyboard)


def parse_cookies_json(text: str) -> str | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, (list, dict)):
        return None

    return json.dumps(parsed, ensure_ascii=False)


def build_account_check_result_text(account: dict, proxy: dict, result: dict) -> str:
    profile_name = account.get("olx_profile_name") or "без имени"
    status = result.get("status") or "unknown"
    final_url = result.get("final_url") or "—"
    error = result.get("error")
    auth_cookie_names = result.get("auth_cookie_names") or []

    lines = [
        "🔎 Проверка аккаунта завершена\n",
        f"ID аккаунта: {account['id']}",
        f"Имя профиля: {profile_name}",
        f"Статус: {status}",
        f"Proxy ID: {proxy['id']}",
        f"Final URL: {final_url}",
        f"Auth cookies: {', '.join(auth_cookie_names) if auth_cookie_names else '—'}",
    ]

    if error:
        lines.append(f"Ошибка: {error}")

    return "\n".join(lines)


async def show_accounts_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    current_user = get_current_user(update)
    user_id = current_user["id"]

    accounts = get_user_accounts(user_id)

    if accounts:
        text = "📂 Аккаунты OLX\n\n"
        for index, account in enumerate(accounts, start=1):
            profile_name = account.get("olx_profile_name") or "без имени"
            status = account.get("status", "unknown")
            proxy_id = account.get("proxy_id")
            proxy_suffix = f" | proxy:{proxy_id}" if proxy_id else ""
            text += f"{index}. {profile_name} — {status}{proxy_suffix}\n"
    else:
        text = (
            "📂 Аккаунты OLX\n\n"
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

    proxy_text = "не привязан"
    proxy_id = account.get("proxy_id")
    if proxy_id:
        proxy = get_proxy_by_id(user_id, proxy_id)
        if proxy:
            raw_proxy_text = proxy.get("proxy_text", "")
            short_proxy = raw_proxy_text if len(raw_proxy_text) <= 60 else raw_proxy_text[:60] + "..."
            proxy_text = f"{proxy_id} | {short_proxy}"
        else:
            proxy_text = f"{proxy_id} | не найден"

    await query.edit_message_text(
        "📄 Карточка аккаунта\n\n"
        f"ID: {account['id']}\n"
        f"Имя профиля: {profile_name}\n"
        f"Статус: {status}\n"
        f"Прокси: {proxy_text}\n"
        f"Последняя проверка: {last_check_at}",
        reply_markup=build_account_card_keyboard(account_id, has_proxy=bool(account.get("proxy_id"))),
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

    if data.startswith("account:bind_proxy:"):
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

        proxies = get_user_proxies(user_id)
        if not proxies:
            await query.edit_message_text(
                "❌ У тебя пока нет прокси для привязки.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Назад к аккаунту", callback_data=f"account:open:{account_id}")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
                ]),
            )
            return

        await query.edit_message_text(
            f"🔗 Выбери прокси для аккаунта ID {account_id}:",
            reply_markup=build_account_proxy_select_keyboard(account_id, proxies),
        )
        return

    if data.startswith("account:set_proxy:"):
        _, _, account_id_str, proxy_id_str = data.split(":")
        account_id = int(account_id_str)
        proxy_id = int(proxy_id_str)

        account = get_account_by_id(user_id, account_id)
        if not account:
            await query.edit_message_text("Аккаунт не найден.")
            return

        proxy = get_proxy_by_id(user_id, proxy_id)
        if not proxy:
            await query.edit_message_text(
                "Прокси не найден.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Назад к аккаунту", callback_data=f"account:open:{account_id}")],
                ]),
            )
            return

        update_account_proxy(user_id, account_id, proxy_id)
        await show_account_card(query, user_id, account_id)
        return

    if data.startswith("account:clear_proxy:"):
        account_id = int(data.split(":")[-1])
        account = get_account_by_id(user_id, account_id)

        if not account:
            await query.edit_message_text("Аккаунт не найден.")
            return

        update_account_proxy(user_id, account_id, None)
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

        proxy_id = account.get("proxy_id")
        if not proxy_id:
            update_account_status(user_id, account_id, "missing_proxy")

            await query.edit_message_text(
                "❌ У аккаунта не привязан прокси.\n\n"
                "Сначала привяжи 1 прокси к этому аккаунту.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 Привязать прокси", callback_data=f"account:bind_proxy:{account_id}")],
                    [InlineKeyboardButton("⬅️ Назад к аккаунту", callback_data=f"account:open:{account_id}")],
                ]),
            )
            return

        proxy = get_proxy_by_id(user_id, proxy_id)
        if not proxy:
            update_account_status(user_id, account_id, "proxy_not_found")

            await query.edit_message_text(
                "❌ Привязанный прокси не найден.\n\n"
                "Привяжи другой прокси.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 Выбрать другой прокси", callback_data=f"account:bind_proxy:{account_id}")],
                    [InlineKeyboardButton("⬅️ Назад к аккаунту", callback_data=f"account:open:{account_id}")],
                ]),
            )
            return

        cookies_json = account.get("cookies_json")
        proxy_text = proxy.get("proxy_text")

        if not cookies_json:
            update_account_status(user_id, account_id, "missing_cookies")
            update_account_last_check(user_id, account_id)

            await query.edit_message_text(
                "❌ У аккаунта отсутствуют cookies_json.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Назад к аккаунту", callback_data=f"account:open:{account_id}")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
                ]),
            )
            return

        await query.edit_message_text(
            "⏳ Проверяю аккаунт через браузер и привязанный proxy...\n\n"
            f"Аккаунт ID: {account_id}\n"
            f"Proxy ID: {proxy['id']}"
        )

        result = await check_account_with_proxy(
            cookies_json=cookies_json,
            proxy_text=proxy_text,
            headless=True,
        )

        new_status = result.get("status") or "unknown_error"

        update_account_status(user_id, account_id, new_status)
        update_account_last_check(user_id, account_id)

        update_proxy_last_check(user_id, proxy["id"])
        if new_status == "connected":
            update_proxy_status(user_id, proxy["id"], "working")
        elif new_status == "proxy_failed":
            update_proxy_status(user_id, proxy["id"], "failed")

        updated_account = get_account_by_id(user_id, account_id)

        await query.edit_message_text(
            build_account_check_result_text(updated_account, proxy, result),
            reply_markup=build_account_card_keyboard(account_id, has_proxy=True),
        )
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
                proxy_id = item.get("proxy_id")
                proxy_suffix = f" | proxy:{proxy_id}" if proxy_id else ""
                text += f"{index}. {profile_name} — {status}{proxy_suffix}\n"
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
        proxy_id = account.get("proxy_id")
        proxy_suffix = f" | proxy:{proxy_id}" if proxy_id else ""
        text_lines.append(f"{index}. {profile_name} — {status}{proxy_suffix}")

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
    proxy_id = updated_account.get("proxy_id")
    proxy_suffix = str(proxy_id) if proxy_id else "не привязан"

    await update.message.reply_text(
        "✅ Cookies обновлены.\n\n"
        f"ID: {updated_account['id']}\n"
        f"Имя профиля: {profile_name}\n"
        f"Статус: {status}\n"
        f"Proxy ID: {proxy_suffix}\n"
        f"Последняя проверка: {last_check_at}",
        reply_markup=build_account_card_keyboard(account_id, has_proxy=bool(proxy_id)),
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