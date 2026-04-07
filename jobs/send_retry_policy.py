from __future__ import annotations

TRANSIENT_SEND_STATUSES = {
    "message_input_not_found",
    "send_button_not_found",
    "send_clicked_unverified",
    "timeout",
}

DEAD_SEND_STATUSES = {
    "cloudfront_blocked",
    "login_required_or_chat_blocked",
    "browser_failed",
}

WRITE_LIMITED_SEND_STATUSES = {
    "daily_limit_reached",
}

WRITE_BLOCKED_SEND_STATUSES = {
    "message_delivery_failed",
}


def should_requeue_send_status(
    send_status: str,
    *,
    attempt: int,
    max_attempts: int,
) -> bool:
    return send_status in TRANSIENT_SEND_STATUSES and attempt < max_attempts


def map_send_status_to_account_status(
    send_status: str,
    *,
    retry_used: bool,
) -> str | None:
    if send_status == "sent":
        return "working"

    if send_status in WRITE_LIMITED_SEND_STATUSES:
        return "write_limited"

    if send_status in WRITE_BLOCKED_SEND_STATUSES:
        return "write_blocked"

    if send_status in TRANSIENT_SEND_STATUSES:
        return "dead" if retry_used else "loading_retry"

    if send_status in DEAD_SEND_STATUSES:
        return "dead"

    return None