from __future__ import annotations

from typing import Any


def build_send_result_text(
    ad: dict | None,
    account: dict | None,
    proxy: dict | None,
    result: dict[str, Any],
    *,
    job_id: str,
) -> str:
    status = result.get("status") or "unknown"
    error = result.get("error")
    account_status = result.get("account_status")

    account_status_map = {
        "working": "живой",
        "loading_retry": "не прогрузился, был повтор",
        "write_limited": "лимит на новые сообщения",
        "dead": "мёртвый",
    }
    account_status_text = account_status_map.get(account_status, account_status)

    prefix = ""
    if result.get("retry_used"):
        first_try_status = result.get("first_try_status")
        if first_try_status:
            prefix = f"Повторная попытка после: {first_try_status}\n"
        else:
            prefix = "Повторная попытка использовалась\n"

    if result.get("ok") or result.get("sent") or status == "sent":
        if account_status_text:
            return f"{prefix}Доставлено\nСтатус аккаунта: {account_status_text}".strip()
        return f"{prefix}Доставлено".strip()

    if error:
        if account_status_text:
            return f"{prefix}Ошибка\n{error}\nСтатус аккаунта: {account_status_text}".strip()
        return f"{prefix}Ошибка\n{error}".strip()

    if account_status_text:
        return f"{prefix}Ошибка\nСтатус: {status}\nСтатус аккаунта: {account_status_text}".strip()

    return f"{prefix}Ошибка\nСтатус: {status}".strip()


def build_failure_result(
    *,
    status: str,
    error: str,
    ad: dict | None = None,
    account: dict | None = None,
    proxy: dict | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "sent": False,
        "status": status,
        "error": error,
        "ad_url": (ad or {}).get("url"),
        "account_id": (account or {}).get("id"),
        "proxy_id": (proxy or {}).get("id"),
        "final_url": (ad or {}).get("url"),
    }