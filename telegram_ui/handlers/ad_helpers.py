import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from olx.markets.helpers import is_market_url
from olx.markets.registry import get_supported_market_codes

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


def _humanize_market(market: str | None) -> str:
    value = (market or "").strip().lower()
    if value == "olx_pl":
        return "OLX PL"
    return "OLX PT"


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
        market_label = _humanize_market(account.get("market"))

        proxy_suffix = f" | proxy:{proxy_id}" if proxy_id else " | без proxy"

        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{account_id}. {profile_name} [{market_label} | {status}]{proxy_suffix}",
                    callback_data=f"approve_account:{ad_row_id}:{pending_action_id}:{account_id}",
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                "⬅️ Назад",
                callback_data=f"back_to_actions:{ad_row_id}:{pending_action_id}",
            )
        ]
    )

    return InlineKeyboardMarkup(keyboard)


def extract_unique_olx_urls(
    text: str,
    market_code: str | None = None,
) -> list[str]:
    seen = set()
    result = []

    supported_markets = get_supported_market_codes()
    normalized_market = (market_code or "").strip().lower()

    for url in re.findall(OLX_URL_PATTERN, text or "", re.IGNORECASE):
        normalized = url.strip()
        if not normalized or normalized in seen:
            continue

        if normalized_market:
            if not is_market_url(normalized, normalized_market):
                continue
        else:
            if not any(is_market_url(normalized, code) for code in supported_markets):
                continue

        seen.add(normalized)
        result.append(normalized)

    return result[:MAX_URLS_PER_MESSAGE]