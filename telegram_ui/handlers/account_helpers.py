import json

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


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
    if value == "timeout":
        return "timeout"
    if value == "unstable":
        return "unstable"
    if value == "cloudfront_blocked":
        return "cloudfront_blocked"
    if value == "proxy_failed":
        return "proxy_failed"
    if value == "not_logged_in":
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
        [InlineKeyboardButton(" Проверить аккаунт", callback_data=f"account:check:{account_id}")],
        [InlineKeyboardButton("✏️ Изменить имя", callback_data=f"account:rename:{account_id}")],
        [InlineKeyboardButton(" Привязать прокси", callback_data=f"account:bind_proxy:{account_id}")],
    ]

    if has_proxy:
        rows.append([InlineKeyboardButton("❌ Отвязать прокси", callback_data=f"account:clear_proxy:{account_id}")])

    rows.extend([
        [InlineKeyboardButton("♻️ Обновить cookies", callback_data=f"account:update_cookies:{account_id}")],
        [InlineKeyboardButton(" Удалить аккаунт", callback_data=f"account:delete:{account_id}")],
        [InlineKeyboardButton("⬅️ Назад к аккаунтам", callback_data="menu:account")],
        [InlineKeyboardButton(" Главное меню", callback_data="menu:main")],
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