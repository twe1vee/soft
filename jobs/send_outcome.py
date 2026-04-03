from __future__ import annotations


def is_success_send_status(send_status: str) -> bool:
    return send_status == "sent"


def should_mark_proxy_failed(send_status: str) -> bool:
    return send_status == "proxy_failed"


def build_ad_failure_status(send_status: str) -> str:
    return f"send_failed:{send_status}"


def build_message_failure_status(send_status: str) -> str:
    return f"send_failed:{send_status}"