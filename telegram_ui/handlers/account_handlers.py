from __future__ import annotations

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
    update_account_market,
    update_account_profile_name,
    update_account_proxy,
    update_account_status,
    update_proxy_last_check,
    update_proxy_status,
)
from olx.account_runtime import close_account_runtime, mark_account_runtime_deleted
from olx.profile_manager_gologin import (
    delete_account_gologin_profile,
    sync_account_profile_cookies,
)
from olx.profile_name_editor import normalize_profile_name, update_olx_profile_name
from telegram_ui.handlers.account_helpers import (
    account_display_name,
    build_account_card_keyboard,
    build_account_delete_confirm_keyboard,
    build_account_market_select_keyboard,
    build_account_proxy_select_keyboard,
    build_accounts_keyboard,
    humanize_account_market,
    humanize_account_status,
    parse_cookies_json,
    short_proxy_text,
)
from telegram_ui.handlers.common import get_current_user


DEFAULT_ACCOUNT_MARKET = "olx_pt"


async def safe_edit_message_text(query, text: str, reply_markup=None, **kwargs):
    try:
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            **kwargs,
        )
        return True
    except BadRequest as e:
        if "Message is not modified" in str(e):
            return True
        raise


async def safe_edit_or_reply(query, text: str, reply_markup=None, **kwargs):
    try:
        return await safe_edit_message_text(
            query,
            text,
            reply_markup=reply_markup,
            **kwargs,
        )
    except BadRequest as e:
        error_text = str(e)
        stale_markers = [
            "Query is too old",
            "query is too old",
            "response timeout expired",
            "query id is invalid",
            "message to edit not found",
        ]
        if any(marker in error_text for marker in stale_markers):
            await query.message.reply_text(
                text=text,
                reply_markup=reply_markup,
                **kwargs,
            )
            return False
        raise


async def _edit_or_reply_to_prompt(update: Update, text: str, reply_markup=None):
    reply_to = update.message.reply_to_message if update.message else None
    if reply_to and reply_to.from_user and reply_to.from_user.is_bot:
        try:
            await reply_to.edit_text(text=text, reply_markup=reply_markup)
            try:
                await update.message.delete()
            except Exception:
                pass
            return
        except Exception:
            pass

    await update.message.reply_text(text, reply_markup=reply_markup)


def _build_not_found_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад к аккаунтам", callback_data="menu:account")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
    ])


def _build_after_account_import_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить ещё аккаунт", callback_data="account:add")],
        [InlineKeyboardButton("⬅️ Назад к аккаунтам", callback_data="menu:account")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
    ])


def _normalize_market(value: str | None) -> str:
    raw = (value or DEFAULT_ACCOUNT_MARKET).strip().lower()
    return raw or DEFAULT_ACCOUNT_MARKET


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

    await safe_edit_or_reply(
        query,
        text=text,
        reply_markup=build_accounts_keyboard(accounts),
    )


async def show_account_card(query, user_id: int, account_id: int):
    account = get_account_by_id(user_id, account_id)

    if not account:
        await safe_edit_or_reply(
            query,
            "Аккаунт не найден.",
            reply_markup=_build_not_found_markup(),
        )
        return

    profile_name = account_display_name(account)
    status = humanize_account_status(account.get("status"))
    market_text = humanize_account_market(account.get("market"))
    last_check_at = account.get("last_check_at") or "ещё не проверялся"

    proxy_text = "не привязан"
    proxy_id = account.get("proxy_id")
    if proxy_id:
        proxy = get_proxy_by_id(user_id, proxy_id)
        if proxy:
            proxy_text = short_proxy_text(proxy.get("proxy_text", ""), max_len=60)
        else:
            proxy_text = "не найден"

    await safe_edit_or_reply(
        query,
        "📄 Карточка аккаунта\n\n"
        f"Аккаунт: {profile_name}\n"
        f"Рынок: {market_text}\n"
        f"Статус: {status}\n"
        f"Прокси: {proxy_text}\n\n"
        f"Последняя проверка: {last_check_at}",
        reply_markup=build_account_card_keyboard(account_id, has_proxy=bool(account.get("proxy_id"))),
    )


async def _handle_bind_proxy(query, user_id: int, account_id: int):
    account = get_account_by_id(user_id, account_id)

    if not account:
        await safe_edit_or_reply(query, "Аккаунт не найден.", reply_markup=_build_not_found_markup())
        return

    proxies = get_user_proxies(user_id)
    if not proxies:
        await safe_edit_or_reply(
            query,
            "❌ У тебя пока нет прокси для привязки.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад к аккаунту", callback_data=f"account:open:{account_id}")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
            ]),
        )
        return

    await safe_edit_or_reply(
        query,
        f"🔗 Выбери прокси для аккаунта «{account_display_name(account)}»:",
        reply_markup=build_account_proxy_select_keyboard(account_id, proxies),
    )


async def _handle_set_proxy(query, user_id: int, account_id: int, proxy_id: int):
    account = get_account_by_id(user_id, account_id)
    if not account:
        await safe_edit_or_reply(query, "Аккаунт не найден.")
        return

    proxy = get_proxy_by_id(user_id, proxy_id)
    if not proxy:
        await safe_edit_or_reply(
            query,
            "Прокси не найден.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад к аккаунту", callback_data=f"account:open:{account_id}")],
            ]),
        )
        return

    update_account_proxy(user_id, account_id, proxy_id)
    await show_account_card(query, user_id, account_id)


async def handle_account_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    query = update.callback_query
    current_user = get_current_user(update)
    user_id = current_user["id"]

    if data == "account:add":
        context.user_data.clear()
        await safe_edit_or_reply(
            query,
            "➕ Добавление аккаунта\n\n"
            "Сначала выбери рынок аккаунта.\n\n"
            "После этого я попрошу прислать cookies JSON.",
            reply_markup=build_account_market_select_keyboard(add_mode=True),
        )
        return

    if data.startswith("account:set_market_for_add:"):
        market_code = _normalize_market(data.split(":")[-1])

        context.user_data.clear()
        context.user_data["awaiting_account_cookies"] = True
        context.user_data["awaiting_account_market"] = market_code

        await safe_edit_or_reply(
            query,
            "➕ Добавление аккаунта\n\n"
            f"Рынок: {humanize_account_market(market_code)}\n\n"
            "Теперь пришли cookies одним из способов:\n"
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

    if data.startswith("account:change_market:"):
        account_id = int(data.split(":")[-1])
        account = get_account_by_id(user_id, account_id)

        if not account:
            await safe_edit_or_reply(
                query,
                "Аккаунт не найден.",
                reply_markup=_build_not_found_markup(),
            )
            return

        await safe_edit_or_reply(
            query,
            "🌍 Смена рынка аккаунта\n\n"
            f"Аккаунт: {account_display_name(account)}\n"
            f"Текущий рынок: {humanize_account_market(account.get('market'))}\n\n"
            "Выбери новый рынок:",
            reply_markup=build_account_market_select_keyboard(add_mode=False, account_id=account_id),
        )
        return

    if data.startswith("account:set_market:"):
        _, _, account_id_str, market_code = data.split(":")
        account_id = int(account_id_str)

        account = get_account_by_id(user_id, account_id)
        if not account:
            await safe_edit_or_reply(
                query,
                "Аккаунт не найден.",
                reply_markup=_build_not_found_markup(),
            )
            return

        update_account_market(user_id, account_id, _normalize_market(market_code))
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
            await safe_edit_or_reply(query, "Аккаунт не найден.")
            return

        update_account_proxy(user_id, account_id, None)
        await show_account_card(query, user_id, account_id)
        return

    if data.startswith("account:check:"):
        account_id = int(data.split(":")[-1])
        account = get_account_by_id(user_id, account_id)

        if not account:
            await safe_edit_or_reply(query, "Аккаунт не найден.", reply_markup=_build_not_found_markup())
            return

        from jobs.check_jobs import ensure_check_jobs_started

        manager = await ensure_check_jobs_started(context.application, worker_count=2)
        await manager.enqueue_account_check(
            user_id=user_id,
            account_id=account_id,
            chat_id=query.message.chat_id,
            source_message_id=query.message.message_id,
        )

        proxy_text = "не привязан"
        proxy_id = account.get("proxy_id")
        if proxy_id:
            proxy = get_proxy_by_id(user_id, proxy_id)
            if proxy:
                proxy_text = short_proxy_text(proxy.get("proxy_text", ""), max_len=50)

        await safe_edit_or_reply(
            query,
            "⏳ Проверка аккаунта поставлена в очередь.\n\n"
            f"Аккаунт: {account_display_name(account)}\n"
            f"Рынок: {humanize_account_market(account.get('market'))}\n"
            f"Прокси: {proxy_text}",
            reply_markup=build_account_card_keyboard(account_id, has_proxy=bool(account.get("proxy_id"))),
        )
        return

    if data.startswith("account:rename:"):
        account_id = int(data.split(":")[-1])
        account = get_account_by_id(user_id, account_id)

        if not account:
            await safe_edit_or_reply(
                query,
                "Аккаунт не найден.",
                reply_markup=_build_not_found_markup(),
            )
            return

        context.user_data.clear()
        context.user_data["awaiting_account_profile_rename"] = account_id

        await safe_edit_or_reply(
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
            await safe_edit_or_reply(query, "Аккаунт не найден.", reply_markup=_build_not_found_markup())
            return

        context.user_data.clear()
        context.user_data["awaiting_account_cookies_update"] = account_id

        await safe_edit_or_reply(
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
            await safe_edit_or_reply(query, "Аккаунт не найден.", reply_markup=_build_not_found_markup())
            return

        await safe_edit_or_reply(
            query,
            f"Ты точно хочешь удалить аккаунт «{account_display_name(account)}»?",
            reply_markup=build_account_delete_confirm_keyboard(account_id),
        )
        return

    if data.startswith("account:confirm_delete:"):
        account_id = int(data.split(":")[-1])
        account = get_account_by_id(user_id, account_id)

        if not account:
            await safe_edit_or_reply(query, "Аккаунт уже не найден.", reply_markup=_build_not_found_markup())
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
                market = humanize_account_market(item.get("market"))
                text += f"{index}. {profile_name} [{market} | {status}]\n"
        else:
            text = "✅ Аккаунт удалён."
            if cleanup_note:
                text += f"\n\n{cleanup_note}"
            text += "\n\nСписок аккаунтов теперь пуст."

        await safe_edit_or_reply(
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
            await _edit_or_reply_to_prompt(
                update,
                "❌ Не удалось распознать cookies JSON.\n\n"
                "Пришли корректный JSON текстом или .txt файлом.",
                reply_markup=_build_after_account_import_keyboard(),
            )
            return

        market_code = _normalize_market(context.user_data.get("awaiting_account_market"))
        create_account(user_id=user_id, cookies_json=normalized, market=market_code)
        context.user_data.clear()
        await _edit_or_reply_to_prompt(
            update,
            f"✅ Аккаунт добавлен.\nРынок: {humanize_account_market(market_code)}",
            reply_markup=_build_after_account_import_keyboard(),
        )
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
        await _edit_or_reply_to_prompt(
            update,
            "❌ Файл должен быть в UTF-8.",
            reply_markup=_build_after_account_import_keyboard(),
        )
        return

    normalized = parse_cookies_json(text)
    if not normalized:
        await _edit_or_reply_to_prompt(
            update,
            "❌ Не удалось распознать cookies JSON в файле.",
            reply_markup=_build_after_account_import_keyboard(),
        )
        return

    if context.user_data.get("awaiting_account_cookies"):
        market_code = _normalize_market(context.user_data.get("awaiting_account_market"))
        create_account(user_id=user_id, cookies_json=normalized, market=market_code)
        context.user_data.clear()
        await _edit_or_reply_to_prompt(
            update,
            f"✅ Аккаунт добавлен.\nРынок: {humanize_account_market(market_code)}",
            reply_markup=_build_after_account_import_keyboard(),
        )
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