from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RetryDecision:
    should_retry: bool
    delay_seconds: float | None = None
    reason: str | None = None


SEND_TRANSIENT_STATUSES = {
    "message_input_not_found",
    "send_button_not_found",
    "send_clicked_unverified",
    "timeout",
}

SEND_SLOW_RETRY_STATUSES = {
    "cloudfront_blocked",
}

SEND_FATAL_STATUSES = {
    "login_required_or_chat_blocked",
    "browser_failed",
    "missing_cookies",
    "missing_proxy",
    "proxy_not_found",
    "account_not_found",
    "missing_url",
    "empty_draft",
    "invalid_input",
}

REPLY_TRANSIENT_STATUSES = {
    "message_input_not_found",
    "send_button_not_found",
    "send_clicked_unverified",
    "timeout",
    "failed_open_runtime",
}

REPLY_SLOW_RETRY_STATUSES = {
    "cloudfront_blocked",
    "skipped_runtime_blocked",
}

REPLY_FATAL_STATUSES = {
    "login_required_or_chat_blocked",
    "missing_cookies",
    "missing_proxy",
    "proxy_not_found",
    "account_not_found",
    "conversation_not_found",
    "invalid_input",
}

DIALOGS_TRANSIENT_STATUSES = {
    "failed_open_runtime",
    "dialogs_open_timeout",
    "dialogs_parse_timeout",
    "failed",
}

DIALOGS_SLOW_RETRY_STATUSES = {
    "cloudfront_blocked",
    "skipped_runtime_blocked",
}

DIALOGS_FATAL_STATUSES = {
    "not_logged_in",
    "skipped_deleted_account",
    "skipped_missing_credentials",
}


def _build_decision(
    *,
    attempt: int,
    max_attempts: int,
    is_retryable: bool,
    delay_seconds: float,
    reason: str,
) -> RetryDecision:
    if not is_retryable:
        return RetryDecision(False, None, reason)

    if attempt >= max_attempts:
        return RetryDecision(False, None, f"{reason}_attempts_exhausted")

    return RetryDecision(True, delay_seconds, reason)


def get_retry_decision(
    *,
    action_type: str,
    status: str | None,
    attempt: int,
    max_attempts: int,
) -> RetryDecision:
    normalized_action = (action_type or "").strip().lower()
    normalized_status = (status or "unknown").strip().lower()

    if normalized_action == "send":
        if normalized_status in SEND_TRANSIENT_STATUSES:
            return _build_decision(
                attempt=attempt,
                max_attempts=max_attempts,
                is_retryable=True,
                delay_seconds=5.0,
                reason="send_transient",
            )

        if normalized_status in SEND_SLOW_RETRY_STATUSES:
            return _build_decision(
                attempt=attempt,
                max_attempts=max_attempts,
                is_retryable=True,
                delay_seconds=45.0,
                reason="send_slow_retry",
            )

        if normalized_status in SEND_FATAL_STATUSES:
            return RetryDecision(False, None, "send_fatal")

        return RetryDecision(False, None, "send_unknown_no_retry")

    if normalized_action == "reply":
        if normalized_status in REPLY_TRANSIENT_STATUSES:
            return _build_decision(
                attempt=attempt,
                max_attempts=max_attempts,
                is_retryable=True,
                delay_seconds=5.0,
                reason="reply_transient",
            )

        if normalized_status in REPLY_SLOW_RETRY_STATUSES:
            return _build_decision(
                attempt=attempt,
                max_attempts=max_attempts,
                is_retryable=True,
                delay_seconds=45.0,
                reason="reply_slow_retry",
            )

        if normalized_status in REPLY_FATAL_STATUSES:
            return RetryDecision(False, None, "reply_fatal")

        return RetryDecision(False, None, "reply_unknown_no_retry")

    if normalized_action == "dialogs_check":
        if normalized_status in DIALOGS_TRANSIENT_STATUSES:
            return _build_decision(
                attempt=attempt,
                max_attempts=max_attempts,
                is_retryable=True,
                delay_seconds=10.0,
                reason="dialogs_transient",
            )

        if normalized_status in DIALOGS_SLOW_RETRY_STATUSES:
            return _build_decision(
                attempt=attempt,
                max_attempts=max_attempts,
                is_retryable=True,
                delay_seconds=60.0,
                reason="dialogs_slow_retry",
            )

        if normalized_status in DIALOGS_FATAL_STATUSES:
            return RetryDecision(False, None, "dialogs_fatal")

        return RetryDecision(False, None, "dialogs_unknown_no_retry")

    return RetryDecision(False, None, "unknown_action_type")