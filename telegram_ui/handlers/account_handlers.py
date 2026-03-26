import json

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
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
from olx.account_session import check_account_alive
from olx.profile_manager_gologin import (
    delete_account_gologin_profile,
    sync_account_profile_cookies,
)
from telegram_ui.handlers.common import get_current_user


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


def account_display_name(account: dict, fallback_index: int | None = None) -> str:
    raw = (account.get("olx_profile_name") or "").strip()
    if raw and raw.lower() not in {"без имени", "без названия"}:
        return raw
    if fallback_index is not None:
        return f"Аккаунт {fallback_index}"
    return "Аккаунт"


def humanize_account_status(status: str | None) -> str:
    value = (status or "").strip().lower()

    if value in {"connected", "working"}:
        return "живой"
    if value == "timeout":
        return "timeout"
    if value == "unstable":
        return "нестабильный"
    if value == "not_logged_in":
        return "не авторизован"
    if value == "cloudfront_blocked":
        return "заблокирован olx"
    if value == "proxy_failed":
        return "ошибка прокси"
    if value == "missing_proxy":
        return "нет прокси"
    if value == "proxy_not_found":
        return "прокси не найден"
    if value == "missing_cookies":
        return "нет cookies"
    if value == "failed":
        return "ошибка проверки"

    return "не проверен"


def humanize_proxy_status(status: str | None) -> str:
    value = (status or "").strip().lower()

    if value in {"working", "connected", "checked"}:
        return "живой"
    if value == "timeout":
        return "timeout"
    if value == "unstable":
        return "нестабильный"
    if value == "cloudfront_blocked":
        return "заблокирован olx"
    if value == "proxy_failed":
        return "ошибка прокси"
    if value == "failed":
        return "ошибка проверки"

    return "не проверен"


def normalize_account_status_for_db(raw_status: str | None) -> str:
    value = (raw_status or "").strip().lower()

    allowed_statuses = {
        "connected",
        "timeout",
        "unstable",
        "not_logged_in",
        "cloudfront_blocked",
        "proxy_failed",
        "missing_proxy",
        "proxy_not_found",
        "missing_cookies",
        "failed",
    }

    if value in allowed_statuses:
        return value

    return "failed"


def normalize_proxy_status_from_account_check(account_status: str | None) -> str:
    value = (account_status or "").strip().lower()

    if value == "connected":
        return "working"

    if value in {"timeout"}:
        return "timeout"

    if value in {"unstable"}:
        return "unstable"

    if value in {"cloudfront_blocked"}:
        return "cloudfront_blocked"

    if value in {"proxy_failed"}:
        return "proxy_failed"

    if value in {"not_logged_in"}:
        # Прокси при этом может быть живой, просто аккаунт неавторизован
        return "working"

    return "failed"


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
        ui_status = humanize_proxy_status(proxy.get("status"))
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
    ui_status = humanize_account_status(result.get("status"))
    final_url = result.get("final_url") or "—"
    error = result.get("error")
    browser_engine = result.get("browser_engine") or account.get("browser_engine") or "—"
    gologin_profile_id = result.get("gologin_profile_id") or account.get("gologin_profile_id") or "—"

    lines = [
        "🔎 Проверка аккаунта завершена\n",
        f"Аккаунт: {profile_name}",
        f"Статус: {ui_status}",
        f"Engine: {browser_engine}",
        f"GoLogin profile: {gologin_profile_id}",
        f"Прокси: {short_proxy_text(proxy.get('proxy_text', ''), max_len=60)}",
        f"Final URL: {final_url}",
    ]

    if result.get("page_title"):
        lines.append(f"Title: {result['page_title']}")

    if result.get("body_length") is not None:
        lines.append(f"Body length: {result['body_length']}")

    if result.get("attempts_used"):
        lines.append(f"Attempts: {result['attempts_used']}")

    if error:
        lines.append(f"Ошибка: {error}")

    return "\n".join(lines)


async def show_accounts_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    current_user = get_current_user(update)
    user_id = current_user["id"]

    accounts = get_user_accounts(user_id)

    if accounts:
        text = "📁 Аккаунты OLX\n\n"
    else:
        text = (
            "📁 Аккаунты OLX\n\n"
            "У тебя пока нет добавленных аккаунтов.\n\n"
            "Нажми «Добавить аккаунт», чтобы загрузить cookies."
        )

    await safe_edit_message_text(
        query,
        text=text,
        reply_markup=build_accounts_keyboard(accounts),
    )


async def show_account_card(query, user_id: int, account_id: int):
    account = get_account_by_id(user_id, account_id)

    if not account:
        await safe_edit_message_text(
            query,
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

    browser_engine = account.get("browser_engine") or "—"
    gologin_profile_id = account.get("gologin_profile_id") or "—"

    await safe_edit_message_text(
        query,
        "📄 Карточка аккаунта\n\n"
        f"Аккаунт: {profile_name}\n"
        f"Статус: {status}\n"
        f"Engine: {browser_engine}\n"
        f"GoLogin profile: {gologin_profile_id}\n"
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

        await safe_edit_message_text(
            query,
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
            await safe_edit_message_text(
                query,
                "Аккаунт не найден.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Назад к аккаунтам", callback_data="menu:account")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
                ]),
            )
            return

        proxies = get_user_proxies(user_id)
        if not proxies:
            await safe_edit_message_text(
                query,
                "❌ У тебя пока нет прокси для привязки.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Назад к аккаунту", callback_data=f"account:open:{account_id}")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
                ]),
            )
            return

        await safe_edit_message_text(
            query,
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
            await safe_edit_message_text(query, "Аккаунт не найден.")
            return

        proxy = get_proxy_by_id(user_id, proxy_id)
        if not proxy:
            await safe_edit_message_text(
                query,
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
            await safe_edit_message_text(query, "Аккаунт не найден.")
            return

        update_account_proxy(user_id, account_id, None)
        await show_account_card(query, user_id, account_id)
        return

    if data.startswith("account:check:"):
        account_id = int(data.split(":")[-1])
        account = get_account_by_id(user_id, account_id)

        if not account:
            await safe_edit_message_text(
                query,
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
            update_account_last_check(user_id, account_id)

            await safe_edit_message_text(
                query,
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
            update_account_last_check(user_id, account_id)

            await safe_edit_message_text(
                query,
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

            await safe_edit_message_text(
                query,
                "❌ У аккаунта отсутствуют cookies_json.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Назад к аккаунту", callback_data=f"account:open:{account_id}")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
                ]),
            )
            return

        await safe_edit_message_text(
            query,
            "⏳ Проверяю аккаунт через браузер и привязанный proxy...\n\n"
            f"Аккаунт: {account_display_name(account)}\n"
            f"Прокси: {short_proxy_text(proxy_text or '', max_len=50)}"
        )

        result = await check_account_alive(
            cookies_json=cookies_json,
            proxy_text=proxy_text,
            headless=True,
            user_id=user_id,
            account_id=account_id,
            olx_profile_name=account.get("olx_profile_name"),
        )

        profile_name = (result.get("profile_name") or "").strip()
        if profile_name:
            update_account_profile_name(user_id, account_id, profile_name)

        result_status = normalize_account_status_for_db(result.get("status"))
        update_account_status(user_id, account_id, result_status)
        update_account_last_check(user_id, account_id)
        update_proxy_last_check(user_id, proxy["id"])

        normalized_proxy_status = normalize_proxy_status_from_account_check(result_status)
        update_proxy_status(user_id, proxy["id"], normalized_proxy_status)

        updated_account = get_account_by_id(user_id, account_id)

        await safe_edit_message_text(
            query,
            build_account_check_result_text(updated_account, proxy, result),
            reply_markup=build_account_card_keyboard(account_id, has_proxy=True),
        )
        return

    if data.startswith("account:update_cookies:"):
        account_id = int(data.split(":")[-1])
        account = get_account_by_id(user_id, account_id)

        if not account:
            await safe_edit_message_text(
                query,
                "Аккаунт не найден.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Назад к аккаунтам", callback_data="menu:account")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
                ]),
            )
            return

        context.user_data.clear()
        context.user_data["awaiting_account_cookies_update"] = account_id

        await safe_edit_message_text(
            query,
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
            await safe_edit_message_text(
                query,
                "Аккаунт не найден.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Назад к аккаунтам", callback_data="menu:account")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
                ]),
            )
            return

        await safe_edit_message_text(
            query,
            f"Ты точно хочешь удалить аккаунт «{account_display_name(account)}»?",
            reply_markup=build_account_delete_confirm_keyboard(account_id),
        )
        return

    if data.startswith("account:confirm_delete:"):
        account_id = int(data.split(":")[-1])
        account = get_account_by_id(user_id, account_id)

        if not account:
            await safe_edit_message_text(
                query,
                "Аккаунт уже не найден.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Назад к аккаунтам", callback_data="menu:account")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
                ]),
            )
            return

        cleanup_note = ""
        try:
            cleanup_result = delete_account_gologin_profile(
                user_id=user_id,
                account_id=account_id,
            )
            if cleanup_result.get("deleted"):
                cleanup_note = "\nGoLogin profile тоже удалён."
        except Exception as exc:
            cleanup_note = f"\nПрофиль GoLogin удалить не удалось: {exc}"

        delete_account(user_id, account_id)
        accounts = get_user_accounts(user_id)

        if accounts:
            text = "✅ Аккаунт удалён." + cleanup_note + "\n\nОставшиеся аккаунты:\n\n"
            for index, item in enumerate(accounts, start=1):
                profile_name = account_display_name(item, fallback_index=index)
                status = humanize_account_status(item.get("status"))
                text += f"{index}. {profile_name} [{status}]\n"
        else:
            text = "✅ Аккаунт удалён." + cleanup_note + "\n\nСписок аккаунтов теперь пуст."

        await safe_edit_message_text(
            query,
            text,
            reply_markup=build_accounts_keyboard(accounts),
        )
        return


async def handle_account_cookies_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    current_user = get_current_user(update)
    user_id = current_user["id"]

    if context.user_data.get("awaiting_account_cookies"):
        normalized = parse_cookies_json(text)
        if not normalized:
            await update.message.reply_text(
                "❌ Не удалось распознать cookies JSON.\n\n"
                "Пришли корректный JSON текстом или .txt файлом."
            )
            return

        create_account(user_id=user_id, cookies_json=normalized)
        context.user_data.clear()
        await update.message.reply_text("✅ Аккаунт добавлен.")
        return

    account_id = context.user_data.get("awaiting_account_cookies_update")
    if account_id:
        normalized = parse_cookies_json(text)
        if not normalized:
            await update.message.reply_text(
                "❌ Не удалось распознать cookies JSON.\n\n"
                "Пришли корректный JSON текстом или .txt файлом."
            )
            return

        account = get_account_by_id(user_id, account_id)
        if not account:
            context.user_data.clear()
            await update.message.reply_text("❌ Аккаунт не найден.")
            return

        update_account_cookies(user_id, account_id, normalized)

        sync_note = ""
        try:
            sync_result = sync_account_profile_cookies(
                user_id=user_id,
                account_id=account_id,
                cookies_json=normalized,
            )
            if sync_result.get("synced"):
                sync_note = "\nCookies сразу синхронизированы в GoLogin профиль."
        except Exception as exc:
            sync_note = f"\nНе удалось сразу синхронизировать cookies в GoLogin: {exc}"

        context.user_data.clear()
        await update.message.reply_text("✅ Cookies обновлены." + sync_note)
        return


async def handle_account_cookies_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    normalized = parse_cookies_json(text)
    if not normalized:
        await update.message.reply_text("❌ Не удалось распознать cookies JSON в файле.")
        return

    if context.user_data.get("awaiting_account_cookies"):
        create_account(user_id=user_id, cookies_json=normalized)
        context.user_data.clear()
        await update.message.reply_text("✅ Аккаунт добавлен.")
        return

    account_id = context.user_data.get("awaiting_account_cookies_update")
    if account_id:
        account = get_account_by_id(user_id, account_id)
        if not account:
            context.user_data.clear()
            await update.message.reply_text("❌ Аккаунт не найден.")
            return

        update_account_cookies(user_id, account_id, normalized)

        sync_note = ""
        try:
            sync_result = sync_account_profile_cookies(
                user_id=user_id,
                account_id=account_id,
                cookies_json=normalized,
            )
            if sync_result.get("synced"):
                sync_note = "\nCookies сразу синхронизированы в GoLogin профиль."
        except Exception as exc:
            sync_note = f"\nНе удалось сразу синхронизировать cookies в GoLogin: {exc}"

        context.user_data.clear()
        await update.message.reply_text("✅ Cookies обновлены." + sync_note)