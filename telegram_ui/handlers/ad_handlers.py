import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from db import (
    ad_exists,
    ad_seen_globally,
    count_global_ad_views,
    save_ad,
    create_pending_action,
    update_ad_status,
    update_ad_draft,
    update_pending_action_status,
    get_ad_by_id,
    get_ad_by_ad_id,
    create_message,
    get_user_accounts,
    get_account_by_id,
    get_proxy_by_id,
    update_proxy_status,
    update_proxy_last_check,
)
from olx.draft import generate_draft
from olx.parser import parse_olx_ad
from olx.message_sender import send_message_to_ad
from telegram_ui.handlers.common import build_ad_caption, get_current_user
from telegram_ui.menu import build_action_keyboard, build_back_to_menu_keyboard

OLX_URL_PATTERN = r"https?://[^\s]*olx[^\s]*"
MAX_URLS_PER_MESSAGE = 5


def sort_accounts_for_send(accounts: list[dict]) -> list[dict]:
    priority = {
        "connected": 0,
        "checked": 1,
        "new": 2,
    }
    return sorted(
        accounts,
        key=lambda a: (
            priority.get(a.get("status", ""), 9),
            a.get("id", 0),
        ),
    )


def build_account_select_keyboard(
    ad_row_id: int,
    pending_action_id: int,
    accounts: list[dict],
) -> InlineKeyboardMarkup:
    keyboard = []

    for account in accounts:
        profile_name = account.get("olx_profile_name") or "без имени"
        status = account.get("status", "unknown")
        proxy_id = account.get("proxy_id")
        account_id = account["id"]

        proxy_suffix = f" | proxy:{proxy_id}" if proxy_id else " | без proxy"

        keyboard.append([
            InlineKeyboardButton(
                f"{account_id}. {profile_name} [{status}]{proxy_suffix}",
                callback_data=f"approve_account:{ad_row_id}:{pending_action_id}:{account_id}",
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Назад",
            callback_data=f"back_to_actions:{ad_row_id}:{pending_action_id}",
        )
    ])

    return InlineKeyboardMarkup(keyboard)


def build_send_result_text(ad: dict, account: dict, proxy: dict, result: dict) -> str:
    profile_name = account.get("olx_profile_name") or "без имени"
    proxy_id = proxy.get("id")
    status = result.get("status") or "unknown"
    final_url = result.get("final_url") or ad.get("url") or "—"
    error = result.get("error")

    lines = [
        build_ad_caption(ad),
        "",
        "📤 Результат отправки",
        f"Аккаунт ID: {account['id']}",
        f"Имя профиля: {profile_name}",
        f"Proxy ID: {proxy_id}",
        f"Статус отправки: {status}",
        f"Final URL: {final_url}",
    ]

    if error:
        lines.append(f"Ошибка: {error}")

    if result.get("ok") or result.get("sent") or status == "sent":
        lines.append("✅ Сообщение реально отправлено продавцу")

    return "\n".join(lines)


async def handle_links_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    current_user = get_current_user(update)
    user_id = current_user["id"]

    urls = re.findall(OLX_URL_PATTERN, text, re.IGNORECASE)

    if not urls:
        await update.message.reply_text(
            "Пришли до 5 ссылок OLX одним сообщением.",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return

    urls = urls[:MAX_URLS_PER_MESSAGE]

    for url in urls:
        try:
            ad_data = await parse_olx_ad(url)
        except Exception as e:
            await update.message.reply_text(
                f"Ошибка парсинга:\n{url}\n\n{e}",
                reply_markup=build_back_to_menu_keyboard(),
            )
            continue

        if not ad_data.get("ad_id"):
            await update.message.reply_text(
                f"Не удалось извлечь ad_id:\n{url}",
                reply_markup=build_back_to_menu_keyboard(),
            )
            continue

        ad_id = ad_data["ad_id"]

        if ad_exists(user_id, ad_id):
            existing_ad = get_ad_by_ad_id(user_id, ad_id)
            await update.message.reply_text(
                f"Это объявление уже смотрели ранее.\n\nID в базе: {existing_ad['id']}",
                reply_markup=build_back_to_menu_keyboard(),
            )
            continue

        globally_seen = ad_seen_globally(ad_id)
        global_views_before_save = count_global_ad_views(ad_id)

        ad_data["status"] = "draft_ready"
        ad_data["draft_text"] = generate_draft(user_id, ad_data)

        ad_row_id = save_ad(user_id, ad_data)

        create_message(
            ad_db_id=ad_row_id,
            direction="outgoing",
            text=ad_data["draft_text"],
            status="auto_draft",
        )

        action_id = create_pending_action(
            ad_db_id=ad_row_id,
            action_type="review_draft",
            payload_text=ad_data["draft_text"],
        )

        keyboard = build_action_keyboard(ad_row_id, action_id)
        saved_ad = get_ad_by_id(user_id, ad_row_id)

        extra_note = ""
        if globally_seen:
            extra_note = (
                f"\n\nЭто объявление уже встречалось в системе ранее "
                f"({global_views_before_save} раз).\n"
            )

        await update.message.reply_text(
            build_ad_caption(saved_ad) + extra_note,
            reply_markup=keyboard,
        )

    context.user_data.clear()


async def handle_editing_ad_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    current_user = get_current_user(update)
    user_id = current_user["id"]

    editing_ad_id = context.user_data.get("editing_ad_id")
    editing_action_id = context.user_data.get("editing_action_id")

    if not editing_ad_id or not editing_action_id:
        await update.message.reply_text(
            "Нет объявления для редактирования.",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return

    ad = get_ad_by_id(user_id, editing_ad_id)
    if not ad:
        await update.message.reply_text(
            "Объявление не найдено или не принадлежит вам.",
            reply_markup=build_back_to_menu_keyboard(),
        )
        context.user_data.pop("editing_ad_id", None)
        context.user_data.pop("editing_action_id", None)
        return

    new_text = text

    update_ad_draft(user_id, editing_ad_id, new_text, new_status="draft_ready")
    ad = get_ad_by_id(user_id, editing_ad_id)

    create_message(
        ad_db_id=editing_ad_id,
        direction="outgoing",
        text=new_text,
        status="edited_draft",
    )

    context.user_data.pop("editing_ad_id", None)
    context.user_data.pop("editing_action_id", None)

    keyboard = build_action_keyboard(editing_ad_id, editing_action_id)

    await update.message.reply_text(
        "✏️ Черновик обновлен.\n\n" + build_ad_caption(ad),
        reply_markup=keyboard,
    )


async def handle_ad_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    current_user = get_current_user(update)
    user_id = current_user["id"]
    query = update.callback_query

    parts = data.split(":")
    if not parts:
        await query.edit_message_reply_markup(reply_markup=None)
        return

    action = parts[0]

    if action in {"approve", "edit", "reject", "back_to_actions"}:
        if len(parts) != 3:
            await query.edit_message_text("Некорректные данные кнопки.")
            return

        _, ad_row_id_str, pending_action_id_str = parts

        try:
            ad_row_id = int(ad_row_id_str)
            pending_action_id = int(pending_action_id_str)
        except ValueError:
            await query.edit_message_text("Некорректные данные кнопки.")
            return

        ad = get_ad_by_id(user_id, ad_row_id)
        if not ad:
            await query.edit_message_text("Объявление не найдено или не принадлежит вам.")
            return

        if action == "approve":
            accounts = get_user_accounts(user_id)

            available_accounts = [
                a for a in accounts
                if a.get("cookies_json")
            ]
            available_accounts = sort_accounts_for_send(available_accounts)

            if not available_accounts:
                update_ad_status(user_id, ad_row_id, "send_blocked_no_account")

                await query.edit_message_text(
                    build_ad_caption(ad) + "\n\n❌ Нет доступных аккаунтов с cookies для отправки."
                )
                return

            await query.edit_message_text(
                build_ad_caption(ad) + "\n\nВыбери аккаунт для отправки:",
                reply_markup=build_account_select_keyboard(
                    ad_row_id=ad_row_id,
                    pending_action_id=pending_action_id,
                    accounts=available_accounts,
                ),
            )
            return

        if action == "back_to_actions":
            await query.edit_message_text(
                build_ad_caption(ad),
                reply_markup=build_action_keyboard(ad_row_id, pending_action_id),
            )
            return

        if action == "reject":
            update_ad_status(user_id, ad_row_id, "rejected")
            update_pending_action_status(pending_action_id, "cancelled")
            ad = get_ad_by_id(user_id, ad_row_id)

            await query.edit_message_text(
                build_ad_caption(ad) + "\n\n❌ Статус: REJECTED"
            )
            return

        if action == "edit":
            context.user_data["editing_ad_id"] = ad_row_id
            context.user_data["editing_action_id"] = pending_action_id

            await query.message.reply_text(
                "Пришли новый текст сообщения одним следующим сообщением."
            )
            return

    if action == "approve_account":
        if len(parts) != 4:
            await query.edit_message_text("Некорректные данные кнопки выбора аккаунта.")
            return

        _, ad_row_id_str, pending_action_id_str, account_id_str = parts

        try:
            ad_row_id = int(ad_row_id_str)
            pending_action_id = int(pending_action_id_str)
            account_id = int(account_id_str)
        except ValueError:
            await query.edit_message_text("Некорректные данные кнопки выбора аккаунта.")
            return

        ad = get_ad_by_id(user_id, ad_row_id)
        if not ad:
            await query.edit_message_text("Объявление не найдено или не принадлежит вам.")
            return

        account = get_account_by_id(user_id, account_id)
        if not account:
            update_ad_status(user_id, ad_row_id, "send_blocked_account_not_found")

            await query.edit_message_text(
                build_ad_caption(ad) + "\n\n❌ Выбранный аккаунт не найден."
            )
            return

        cookies_json = account.get("cookies_json")
        if not cookies_json:
            update_ad_status(user_id, ad_row_id, "send_blocked_missing_cookies")

            await query.edit_message_text(
                build_ad_caption(ad) + "\n\n❌ У выбранного аккаунта отсутствуют cookies_json."
            )
            return

        proxy_id = account.get("proxy_id")
        if not proxy_id:
            update_ad_status(user_id, ad_row_id, "send_blocked_no_proxy")

            await query.edit_message_text(
                build_ad_caption(ad) + "\n\n❌ У выбранного аккаунта не привязан proxy."
            )
            return

        proxy = get_proxy_by_id(user_id, proxy_id)
        if not proxy:
            update_ad_status(user_id, ad_row_id, "send_blocked_proxy_not_found")

            await query.edit_message_text(
                build_ad_caption(ad) + "\n\n❌ Привязанный к аккаунту proxy не найден."
            )
            return

        proxy_text = proxy.get("proxy_text")
        ad_url = ad.get("url")
        draft_text = ad.get("draft_text") or ""

        if not ad_url:
            update_ad_status(user_id, ad_row_id, "send_blocked_missing_url")

            await query.edit_message_text(
                build_ad_caption(ad) + "\n\n❌ У объявления отсутствует URL."
            )
            return

        if not draft_text.strip():
            update_ad_status(user_id, ad_row_id, "send_blocked_empty_draft")

            await query.edit_message_text(
                build_ad_caption(ad) + "\n\n❌ У объявления пустой draft_text."
            )
            return

        await query.edit_message_text(
            build_ad_caption(ad)
            + "\n\n⏳ Отправляю сообщение через реальный браузер...\n"
            + f"Аккаунт ID: {account['id']}\n"
            + f"Proxy ID: {proxy['id']}"
        )

        result = await send_message_to_ad(
            cookies_json=cookies_json,
            proxy_text=proxy_text,
            ad_url=ad_url,
            message_text=draft_text,
            headless=True,
        )

        send_status = result.get("status") or "unknown_error"

        update_proxy_last_check(user_id, proxy["id"])

        if send_status == "sent":
            update_proxy_status(user_id, proxy["id"], "working")
            update_ad_status(user_id, ad_row_id, "sent")
            update_pending_action_status(pending_action_id, "done")
            create_message(
                ad_db_id=ad_row_id,
                direction="outgoing",
                text=draft_text,
                status="sent",
            )
        else:
            if send_status == "proxy_failed":
                update_proxy_status(user_id, proxy["id"], "failed")

            update_ad_status(user_id, ad_row_id, f"send_failed:{send_status}")
            update_pending_action_status(pending_action_id, "failed")
            create_message(
                ad_db_id=ad_row_id,
                direction="outgoing",
                text=draft_text,
                status=f"send_failed:{send_status}",
            )

        updated_ad = get_ad_by_id(user_id, ad_row_id)

        await query.edit_message_text(
            build_send_result_text(updated_ad, account, proxy, result)
        )
        return

    await query.edit_message_text("Неизвестное действие.")