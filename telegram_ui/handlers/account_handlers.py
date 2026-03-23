import json

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from db import (
    create_account,
    delete_account,
    get_account_by_id,
    get_proxy_by_id,
    get_user_accounts,
    get_user_proxies,
    update_account_cookies,
    update_account_last_check,
    update_account_profile_name,
    update_account_proxy,
    update_account_status,
    update_proxy_last_check,
    update_proxy_status,
)
from olx.account_session import check_account_with_proxy
from telegram_ui.handlers.common import get_current_user


def account_display_name(account: dict, fallback_index: int | None = None) -> str:
    raw = (account.get("olx_profile_name") or "").strip()
    if raw and raw.lower() not in {"без имени", "без названия"}:
        return raw
    if fallback_index is not None:
        return f"Аккаунт {fallback_index}"
    return "Аккаунт"


def humanize_account_status(status: str | None) -> str:
    value = (status or "").strip().lower()
    if value in {"connected", "working", "checked"}:
        return "живой"
    if value in {"failed", "proxy_failed", "invalid_cookies", "missing_proxy", "proxy_not_found", "missing_cookies"}:
        return "мёртвый"
    return "не проверен"


def short_proxy_text(proxy_text: str, max_len: int = 60) -> str:
    value = (proxy_text or "").strip()
    if len(value) <= max_len:
        return value
    return value[:max_len] + "..."


def build_accounts_keyboard(accounts: list[dict]) -> InlineKeyboardMarkup:
    keyboard = []

    for index, account in enumerate(accounts, start=1):
        profile_name = account_display_name(account, fallback_index=index)
        status = humanize_account_status(account.get("status"))

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

    for index, proxy in enumerate(proxies, start=1):
        proxy_text = proxy.get("proxy_text", "")
        status = proxy.get("status", "unknown")
        ui_status = "живой" if status in {"working", "connected", "checked"} else ("мёртвый" if status == "failed" else "не проверен")
        short_proxy = short_proxy_text(proxy_text, max_len=42)

        keyboard.append([
            InlineKeyboardButton(
                f"{index}. {short_proxy} [{ui_status}]",
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
    profile_name = account_display_name(account)
    ui_status = "живой" if result.get("status") == "connected" else "мёртвый"
    final_url = result.get("final_url") or "—"
    error = result.get("error")

    lines = [
        "🔎 Проверка аккаунта завершена\n",
        f"Аккаунт: {profile_name}",
        f"Статус: {ui_status}",
        f"Прокси: {short_proxy_text(proxy.get('proxy_text', ''), max_len=60)}",
        f"Final URL: {final_url}",
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
        text = "👤 Аккаунты OLX\n\n"
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

    profile_name = account_display_name(account)
    status = humanize_account_status(account.get("status"))
    last_check_at = account.get("last_check_at") or "ещё не проверялся"

    proxy_text = "не привязан"
    proxy_id = account.get("proxy_id")
    if proxy_id:
        proxy = get_proxy_by_id(user_id, proxy_id)
        if proxy:
            proxy_text = short_proxy_text(proxy.get("proxy_text", ""), max_len=60)
        else:
            proxy_text = "не найден"

    await query.edit_message_text(
        "📌 Карточка аккаунта\n\n"
        f"Аккаунт: {profile_name}\n"
        f"Статус: {status}\n"
        f"Прокси: {proxy_text}\n\n"
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
            "После получения я сохраню новый аккаунт в базу.",
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
            f"🔗 Выбери прокси для аккаунта «{account_display_name(account)}»:",
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
            update_account_status(user_id, account_id, "failed")
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
            update_account_status(user_id, account_id, "failed")
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
            update_account_status(user_id, account_id, "failed")
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
            f"Аккаунт: {account_display_name(account)}\n"
            f"Прокси: {short_proxy_text(proxy_text or '', max_len=50)}"
        )

        profile_name = (result.get("profile_name") or "").strip()
        if profile_name:
            update_account_profile_name(user_id, account_id, profile_name)

        new_status = "connected" if result.get("status") == "connected" else "failed"

        update_account_status(user_id, account_id, new_status)
        update_account_last_check(user_id, account_id)
        update_proxy_last_check(user_id, proxy["id"])

        if new_status == "connected":
            update_proxy_status(user_id, proxy["id"], "working")
        else:
            update_proxy_status(user_id, proxy["id"], "failed")

        profile_name = (result.get("profile_name") or "").strip()
        if profile_name:
            update_account_profile_name(user_id, account_id, profile_name)

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
            f"Я обновлю cookies у аккаунта «{account_display_name(account)}».",
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
            f"Ты точно хочешь удалить аккаунт «{account_display_name(account)}»?",
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
                profile_name = account_display_name(item, fallback_index=index)
                status = humanize_account_status(item.get("status"))
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

    existing_accounts = get_user_accounts(user_id)
    default_name = f"Аккаунт {len(existing_accounts) + 1}"

    create_account(
        user_id=user_id,
        cookies_json=cookies_json,
        status="new",
        olx_profile_name=default_name,
    )

    context.user_data.pop("awaiting_account_cookies", None)

    accounts = get_user_accounts(user_id)
    text_lines = [
        "✅ Аккаунт успешно добавлен.\n",
        "Текущий список аккаунтов:\n",
    ]

    for index, account in enumerate(accounts, start=1):
        profile_name = account_display_name(account, fallback_index=index)
        status = humanize_account_status(account.get("status"))
        text_lines.append(f"{index}. {profile_name} — {status}")

    if update.message:
        await update.message.reply_text(
            "\n".join(text_lines),
            reply_markup=build_accounts_keyboard(accounts),
        )


async def handle_account_cookies_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    cookies_json = parse_cookies_json(text)
    if not cookies_json:
        await update.message.reply_text(
            "Не удалось распознать cookies JSON.\n\n"
            "Пришли валидный JSON текстом."
        )
        return

    account_id_to_update = context.user_data.get("awaiting_account_cookies_update")
    current_user = get_current_user(update)
    user_id = current_user["id"]

    if account_id_to_update:
        account = get_account_by_id(user_id, account_id_to_update)
        if not account:
            context.user_data.pop("awaiting_account_cookies_update", None)
            await update.message.reply_text("Аккаунт для обновления не найден.")
            return

        update_account_cookies(user_id, account_id_to_update, cookies_json)
        update_account_status(user_id, account_id_to_update, "new")
        context.user_data.pop("awaiting_account_cookies_update", None)

        updated = get_account_by_id(user_id, account_id_to_update)
        await update.message.reply_text(
            "✅ Cookies обновлены.\n\n"
            f"Аккаунт: {account_display_name(updated)}\n"
            "Статус сброшен в «не проверен».",
        )
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
            "Не удалось прочитать файл как UTF-8 текст."
        )
        return

    await handle_account_cookies_text(update, context, text)