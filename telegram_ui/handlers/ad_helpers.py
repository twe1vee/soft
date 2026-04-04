import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from olx.markets.helpers import is_market_url

OLX_URL_PATTERN = r"https?://[^\s]*olx[^\s]*"
MAX_URLS_PER_MESSAGE = 5
DEFAULT_AD_MARKET = "olx_pt"


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

        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{account_id}. {profile_name} [{status}]{proxy_suffix}",
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
    market_code: str = DEFAULT_AD_MARKET,
) -> list[str]:
    seen = set()
    result = []

    for url in re.findall(OLX_URL_PATTERN, text or "", re.IGNORECASE):
        normalized = url.strip()
        if not normalized or normalized in seen:
            continue

        if not is_market_url(normalized, market_code):
            continue

        seen.add(normalized)
        result.append(normalized)

    return result[:MAX_URLS_PER_MESSAGE]