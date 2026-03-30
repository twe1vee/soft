import re

from telegram import Update
from telegram.ext import ContextTypes
from html import escape as html_escape

from db import get_or_create_user, ensure_default_template
from telegram_ui.menu import get_main_menu_inline_keyboard


def _normalize_text(value) -> str:
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_numeric_token(token: str) -> str:
    token = (token or "").strip()
    token = token.replace(" ", "").replace("\u00a0", "")

    if not token:
        return ""

    comma_count = token.count(",")
    dot_count = token.count(".")

    if comma_count and dot_count:
        last_comma = token.rfind(",")
        last_dot = token.rfind(".")

        if last_comma > last_dot:
            token = token.replace(".", "")
            token = token.replace(",", ".")
        else:
            token = token.replace(",", "")
        return token

    if comma_count:
        if comma_count > 1:
            parts = token.split(",")
            token = "".join(parts[:-1]) + "." + parts[-1]
        else:
            left, right = token.split(",", 1)
            if right.isdigit() and 1 <= len(right) <= 2:
                token = left + "." + right
            else:
                token = left + right
        return token

    if dot_count:
        if dot_count > 1:
            parts = token.split(".")
            last = parts[-1]
            if last.isdigit() and 1 <= len(last) <= 2:
                token = "".join(parts[:-1]) + "." + last
            else:
                token = "".join(parts)
        else:
            left, right = token.split(".", 1)
            if right.isdigit() and 1 <= len(right) <= 2:
                token = left + "." + right
            else:
                token = left + right
        return token

    return token


def _format_caption_price(raw_price) -> str:
    from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

    text = _normalize_text(raw_price)
    if not text:
        return "не найдена"

    text = text.replace("EUR", " ").replace("eur", " ").replace("€", " ")
    text = re.sub(r"\s+", " ", text).strip()

    matches = re.findall(r"\d[\d\s.,]*", text)
    if not matches:
        return "не найдена"

    numeric_text = ""
    for match in matches:
        cleaned = _normalize_numeric_token(match)
        if cleaned:
            numeric_text = cleaned
            break

    if not numeric_text:
        return "не найдена"

    try:
        value = Decimal(numeric_text).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return "не найдена"

    return f"{value:.2f}".replace(".", ",") + "€"


def get_current_user(update: Update) -> dict:
    tg_user = update.effective_user
    user = get_or_create_user(
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
    )
    ensure_default_template(user["id"])
    return user


def build_ad_caption(ad_data: dict) -> str:
    ad_id = ad_data.get("ad_id") or "—"
    url = _normalize_text(ad_data.get("url")) or "—"
    status = _normalize_text(ad_data.get("status")) or ""

    if status == "draft_ready":
        status_text = "Готово к написанию. Отправить ?"
    elif status in {"queued", "send_queued", "sending"}:
        status_text = "Отправляем"
    else:
        status_text = "Готово"

    return (
        "📦 Объявление\n"
        f"🆔 ID#{ad_id}\n\n\n"
        f"📌 {status_text}\n\n"
        f'🔗 <a href="{html_escape(url, quote=True)}">Ссылка на объявление</a>'
    )


async def show_main_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str = "⚙️ Панель управления\n\nВыберите действие из списка ниже:",
):
    if update.message:
        await update.message.reply_text(
            text,
            reply_markup=get_main_menu_inline_keyboard(),
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=get_main_menu_inline_keyboard(),
        )