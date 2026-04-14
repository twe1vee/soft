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

    if value in {"failed", "dead", "invalid_type"}:
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
        "invalid_type",
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


def _build_after_proxy_import_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить ещё прокси", callback_data="proxy:add")],
        [InlineKeyboardButton("⬅️ Назад к прокси", callback_data="menu:proxies")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
    ])


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


def _is_valid_socks5_proxy(proxy_text: str) -> bool:
    raw = (proxy_text or "").strip()
    if not raw:
        return False

    lower = raw.lower()

    if "://" in lower:
        return lower.startswith("socks5://")

    parts = [p.strip() for p in raw.split(":")]
    if len(parts) == 2:
        return True
    if len(parts) >= 4:
        return True

    return False


def _normalize_single_proxy(proxy_text: str) -> str | None:
    raw = (proxy_text or "").strip()
    if not raw:
        return None

    lower = raw.lower()

    if "://" in lower:
        if not lower.startswith("socks5://"):
            return None
        return raw

    parts = [p.strip() for p in raw.split(":")]
    if len(parts) == 2:
        host, port = parts
        if not host or not port:
            return None
        return f"socks5://{host}:{port}"

    if len(parts) >= 4:
        host = parts[0]
        port = parts[1]
        username = parts[2]
        password = ":".join(parts[3:])
        if not host or not port or not username or not password:
            return None
        return f"socks5://{username}:{password}@{host}:{port}"

    return None


def _parse_proxy_lines(text: str) -> tuple[list[str], list[str]]:
    valid: list[str] = []
    invalid: list[str] = []
    seen = set()

    for line in (text or "").splitlines():
        value = line.strip()
        if not value:
            continue

        normalized = _normalize_single_proxy(value)
        if not normalized:
            invalid.append(value)
            continue

        if normalized in seen:
            continue

        seen.add(normalized)
        valid.append(normalized)

    return valid, invalid


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
            "Разрешён только SOCKS5:\n"
            "- socks5://user:pass@host:port\n"
            "- socks5://host:port\n"
            "- host:port\n"
            "- host:port:user:pass\n\n"
            "HTTP / HTTPS / SOCKS4 не принимаются.",
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

        proxy_text = proxy.get("proxy_text", "")

        if not _is_valid_socks5_proxy(proxy_text):
            update_proxy_last_check(user_id, proxy_id)
            update_proxy_status(user_id, proxy_id, "invalid_type")

            await safe_edit_message_text(
                query,
                "🔎 Проверка прокси завершена\n\n"
                f"Прокси: {proxy_short(proxy_text, max_len=70)}\n"
                "Статус: ошибка проверки\n\n"
                "Причина: поддерживается только SOCKS5.",
                reply_markup=build_proxy_card_keyboard(proxy_id),
            )
            return

        from jobs.check_jobs import ensure_check_jobs_started

        manager = await ensure_check_jobs_started(context.application, worker_count=2)
        await manager.enqueue_proxy_check(
            user_id=user_id,
            proxy_id=proxy_id,
            chat_id=query.message.chat_id,
            source_message_id=query.message.message_id,
        )

        await safe_edit_message_text(
            query,
            "⏳ Проверка прокси поставлена в очередь.\n\n"
            f"Прокси: {proxy_short(proxy_text, max_len=50)}",
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
            f"Ты точно хочешь удалить прокси?\n\n{proxy_short(proxy.get('proxy_text', ''), max_len=70)}",
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


async def handle_proxies_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    current_user = get_current_user(update)
    user_id = current_user["id"]

    proxy_list, invalid_list = _parse_proxy_lines(text)
    if not proxy_list:
        await _edit_or_reply_to_prompt(
            update,
            "❌ Не удалось найти ни одного подходящего прокси.\n\n"
            "Разрешён только SOCKS5.",
            reply_markup=_build_after_proxy_import_keyboard(),
        )
        return

    inserted_count = create_proxies_bulk(user_id, proxy_list)
    context.user_data.clear()

    reply = f"✅ Добавлено прокси: {inserted_count}"
    if invalid_list:
        preview = "\n".join(invalid_list[:5])
        reply += (
            "\n\n⚠️ Пропущены строки с неподдерживаемым типом.\n"
            "Разрешён только SOCKS5.\n\n"
            f"{preview}"
        )

    await _edit_or_reply_to_prompt(
        update,
        reply,
        reply_markup=_build_after_proxy_import_keyboard(),
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
        await _edit_or_reply_to_prompt(
            update,
            "❌ Файл должен быть в UTF-8.",
            reply_markup=_build_after_proxy_import_keyboard(),
        )
        return

    proxy_list, invalid_list = _parse_proxy_lines(text)
    if not proxy_list:
        await _edit_or_reply_to_prompt(
            update,
            "❌ Не удалось найти ни одного подходящего прокси в файле.\n\n"
            "Разрешён только SOCKS5.",
            reply_markup=_build_after_proxy_import_keyboard(),
        )
        return

    inserted_count = create_proxies_bulk(user_id, proxy_list)
    context.user_data.clear()

    reply = f"✅ Добавлено прокси: {inserted_count}"
    if invalid_list:
        preview = "\n".join(invalid_list[:5])
        reply += (
            "\n\n⚠️ Пропущены строки с неподдерживаемым типом.\n"
            "Разрешён только SOCKS5.\n\n"
            f"{preview}"
        )

    await _edit_or_reply_to_prompt(
        update,
        reply,
        reply_markup=_build_after_proxy_import_keyboard(),
    )