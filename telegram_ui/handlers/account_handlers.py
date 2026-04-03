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
from olx.account_runtime import close_account_runtime, mark_account_runtime_deleted
from olx.account_session import check_account_alive
from olx.profile_manager_gologin import (
    delete_account_gologin_profile,
    sync_account_profile_cookies,
)
from olx.profile_name_editor import normalize_profile_name, update_olx_profile_name
from telegram_ui.handlers.account_helpers import (
    account_display_name,
    build_account_card_keyboard,
    build_account_check_result_text,
    build_account_delete_confirm_keyboard,
    build_account_proxy_select_keyboard,
    build_accounts_keyboard,
    humanize_account_status,
    normalize_account_status_for_db,
    normalize_proxy_status_from_account_check,
    parse_cookies_json,
    short_proxy_text,
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


def _build_not_found_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад к аккаунтам", callback_data="menu:account")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
    ])


def _build_account_rename_result_text(account: dict, result: dict) -> str:
    profile_name = account_display_name(account)
    status = result.get("status") or "failed"
    requested_name = result.get("requested_name") or "—"
    previous_name = result.get("previous_name") or "—"
    saved_name = result.get("saved_name") or "—"
    final_url = result.get("final_url") or "—"
    error = result.get("error")
    delay_seconds = result.get("delay_seconds") or 0

    if status == "updated":
        return (
            "✅ Имя профиля обновлено\n\n"
            f"Аккаунт: {profile_name}\n"
            f"Было: {previous_name}\n"
            f"Стало: {saved_name}\n"
            f"Задержка перед сменой: {delay_seconds} сек\n"
        )

    if status == "unchanged":
        return (
            "ℹ️ Имя профиля не изменено\n\n"
            f"Аккаунт: {profile_name}\n"
            f"На OLX уже стоит имя: {saved_name}\n"
            f"Final URL: {final_url}"
        )

    text = (
        "❌ Не удалось изменить имя профиля\n\n"
        f"Аккаунт: {profile_name}\n"
        f"Новое имя: {requested_name}\n"
        f"Было: {previous_name}\n"
        f"Final URL: {final_url}"
    )
    if error:
        text += f"\nОшибка: {error}"
    return text


async def _delete_account_and_profile(*, user_id: int, account_id: int) -> str:
    cleanup_lines: list[str] = []

    try:
        await mark_account_runtime_deleted(account_id)
        cleanup_lines.append("Runtime помечен как удалённый.")
    except Exception as exc:
        cleanup_lines.append(f"Не удалось пометить runtime как удалённый: {exc}")

    try:
        await close_account_runtime(account_id, reason="account_deleted")
        cleanup_lines.append("Активный runtime закрыт.")
    except Exception as exc:
        cleanup_lines.append(f"Не удалось закрыть runtime: {exc}")

    try:
        cleanup_result = delete_account_gologin_profile(
            user_id=user_id,
            account_id=account_id,
        )
        if cleanup_result.get("deleted"):
            cleanup_lines.append("GoLogin profile тоже удалён.")
        elif cleanup_result.get("reason") == "no_profile":
            cleanup_lines.append("У аккаунта не было GoLogin profile.")
    except Exception as exc:
        cleanup_lines.append(f"Профиль GoLogin удалить не удалось: {exc}")

    delete_account(user_id, account_id)
    return "\n".join(cleanup_lines)


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
            reply_markup=_build_not_found_markup(),
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
        f"Прокси: {proxy_text}\n\n"
        f"Последняя проверка: {last_check_at}",
        reply_markup=build_account_card_keyboard(account_id, has_proxy=bool(account.get("proxy_id"))),
    )


async def _handle_bind_proxy(query, user_id: int, account_id: int):
    account = get_account_by_id(user_id, account_id)

    if not account:
        await safe_edit_message_text(query, "Аккаунт не найден.", reply_markup=_build_not_found_markup())
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


async def _handle_set_proxy(query, user_id: int, account_id: int, proxy_id: int):
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


async def _handle_check_account(query, user_id: int, account_id: int):
    account = get_account_by_id(user_id, account_id)

    if not account:
        await safe_edit_message_text(query, "Аккаунт не найден.", reply_markup=_build_not_found_markup())
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
        await _handle_bind_proxy(query, user_id, account_id)
        return

    if data.startswith("account:set_proxy:"):
        _, _, account_id_str, proxy_id_str = data.split(":")
        await _handle_set_proxy(query, user_id, int(account_id_str), int(proxy_id_str))
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
        await _handle_check_account(query, user_id, account_id)
        return

    if data.startswith("account:rename:"):
        account_id = int(data.split(":")[-1])
        account = get_account_by_id(user_id, account_id)

        if not account:
            await safe_edit_message_text(
                query,
                "Аккаунт не найден.",
                reply_markup=_build_not_found_markup(),
            )
            return

        context.user_data.clear()
        context.user_data["awaiting_account_profile_rename"] = account_id

        await safe_edit_message_text(
            query,
            "✏️ Изменение имени профиля\n\n"
            "Пришли новое имя одним следующим сообщением.\n\n"
            "Оно будет изменено на площадке OLX.\n"
            "Перед самой сменой софт подождёт 2–4 секунды.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад к аккаунту", callback_data=f"account:open:{account_id}")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
            ]),
        )
        return

    if data.startswith("account:update_cookies:"):
        account_id = int(data.split(":")[-1])
        account = get_account_by_id(user_id, account_id)

        if not account:
            await safe_edit_message_text(query, "Аккаунт не найден.", reply_markup=_build_not_found_markup())
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
            await safe_edit_message_text(query, "Аккаунт не найден.", reply_markup=_build_not_found_markup())
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
            await safe_edit_message_text(query, "Аккаунт уже не найден.", reply_markup=_build_not_found_markup())
            return

        cleanup_note = await _delete_account_and_profile(
            user_id=user_id,
            account_id=account_id,
        )

        accounts = get_user_accounts(user_id)

        if accounts:
            text = "✅ Аккаунт удалён.\n"
            if cleanup_note:
                text += f"\n{cleanup_note}\n"
            text += "\nОставшиеся аккаунты:\n\n"

            for index, item in enumerate(accounts, start=1):
                profile_name = account_display_name(item, fallback_index=index)
                status = humanize_account_status(item.get("status"))
                text += f"{index}. {profile_name} [{status}]\n"
        else:
            text = "✅ Аккаунт удалён."
            if cleanup_note:
                text += f"\n\n{cleanup_note}"
            text += "\n\nСписок аккаунтов теперь пуст."

        await safe_edit_message_text(
            query,
            text,
            reply_markup=build_accounts_keyboard(accounts),
        )
        return


async def handle_account_profile_rename_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
):
    current_user = get_current_user(update)
    user_id = current_user["id"]

    account_id = context.user_data.get("awaiting_account_profile_rename")
    if not account_id:
        await update.message.reply_text("Сейчас имя аккаунта не ожидается.")
        return

    new_name = normalize_profile_name(text)
    if len(new_name) < 2:
        await update.message.reply_text(
            "❌ Имя слишком короткое.\n\nПришли имя длиной хотя бы 2 символа."
        )
        return

    if len(new_name) > 40:
        await update.message.reply_text(
            "❌ Имя слишком длинное.\n\nПришли имя до 40 символов."
        )
        return

    account = get_account_by_id(user_id, account_id)
    if not account:
        context.user_data.pop("awaiting_account_profile_rename", None)
        await update.message.reply_text("Аккаунт не найден.")
        return

    proxy_id = account.get("proxy_id")
    if not proxy_id:
        context.user_data.pop("awaiting_account_profile_rename", None)
        await update.message.reply_text(
            "❌ У аккаунта не привязан прокси.\n\nСначала привяжи прокси, затем повтори."
        )
        return

    proxy = get_proxy_by_id(user_id, proxy_id)
    if not proxy:
        context.user_data.pop("awaiting_account_profile_rename", None)
        await update.message.reply_text(
            "❌ Привязанный прокси не найден.\n\nПривяжи другой прокси и повтори."
        )
        return

    cookies_json = account.get("cookies_json")
    if not cookies_json:
        context.user_data.pop("awaiting_account_profile_rename", None)
        await update.message.reply_text(
            "❌ У аккаунта отсутствуют cookies.\n\nСначала обнови cookies."
        )
        return

    await update.message.reply_text(
        "⏳ Меняю имя профиля на OLX...\n\n"
        f"Аккаунт: {account_display_name(account)}\n"
        f"Новое имя: {new_name}\n"
        "Перед сменой будет пауза 2–4 сек."
    )

    result = await update_olx_profile_name(
        user_id=user_id,
        account_id=account_id,
        cookies_json=cookies_json,
        proxy_text=proxy.get("proxy_text") or "",
        olx_profile_name=account.get("olx_profile_name"),
        requested_name=new_name,
        headless=True,
    )

    if result.get("ok") and result.get("saved_name"):
        update_account_profile_name(user_id, account_id, result["saved_name"])

    updated_account = get_account_by_id(user_id, account_id) or account

    context.user_data.pop("awaiting_account_profile_rename", None)

    await update.message.reply_text(
        _build_account_rename_result_text(updated_account, result),
        reply_markup=build_account_card_keyboard(
            account_id,
            has_proxy=bool(updated_account.get("proxy_id")),
        ),
    )


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