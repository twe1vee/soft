from __future__ import annotations

from typing import Any


def _humanize_send_error(
    status: str,
    error: str | None,
    account_status: str | None,
) -> str:
    if status == "login_required_or_chat_blocked":
        return (
            "OLX выбросил аккаунт из сессии. "
            "Этот аккаунт больше нельзя использовать для отправки сообщений."
        )

    if status == "message_delivery_failed":
        return (
            "OLX не даёт этому аккаунту отправлять новые сообщения. "
            "Старые диалоги ещё могут открываться, но для отправки нужен другой аккаунт."
        )

    if status == "message_input_not_found":
        return (
            "OLX не успел полностью прогрузить чат. "
            "Попробуйте отправить сообщение ещё раз."
        )

    if status == "daily_limit_reached":
        return (
            "На этом аккаунте достигнут лимит новых диалогов за день. "
            "Попробуйте позже или используйте другой аккаунт."
        )

    if status == "cloudfront_blocked":
        return (
            "OLX временно заблокировал доступ к странице. "
            "Попробуйте позже или используйте другой аккаунт / прокси."
        )

    if status == "send_button_not_found":
        return (
            "OLX не дал нажать кнопку отправки. "
            "Попробуйте ещё раз."
        )

    if status == "send_clicked_unverified":
        return (
            "Сообщение не удалось подтвердить автоматически. "
            "Возможно, OLX не принял отправку."
        )

    if status == "timeout":
        return (
            "OLX слишком долго загружался. "
            "Попробуйте ещё раз."
        )

    if status == "browser_failed":
        return (
            "Не удалось открыть локальный профиль GoLogin. "
            "Файл Cookies мог быть занят другим процессом. "
            "Попробуйте ещё раз."
        )

    return error or "Не удалось отправить сообщение."


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
        "write_blocked": "не может отправлять сообщения",
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

    human_error = _humanize_send_error(status, error, account_status)

    if account_status_text:
        return f"{prefix}Ошибка\n{human_error}\nСтатус аккаунта: {account_status_text}".strip()

    return f"{prefix}Ошибка\n{human_error}".strip()


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