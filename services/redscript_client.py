from __future__ import annotations

from typing import Any

import requests

BASE_URL = "https://api.redscript.info"
DEFAULT_TIMEOUT_SECONDS = 8


class RedScriptApiError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, payload: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json; charset=UTF-8"}

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise RedScriptApiError(f"Сбой сети при запросе к RedScript API: {exc}") from exc

    try:
        data = response.json()
    except Exception:
        text = (response.text or "").strip()
        raise RedScriptApiError(
            f"RedScript API вернул неожиданный ответ: HTTP {response.status_code} {text[:300]}",
            status_code=response.status_code,
        )

    if response.status_code == 429:
        raise RedScriptApiError(
            "Превышен лимит запросов RedScript API. Попробуйте чуть позже.",
            status_code=response.status_code,
            payload=data,
        )

    if response.status_code == 424:
        detail = data.get("error")
        if isinstance(detail, dict):
            detail = detail.get("detail") or str(detail)
        raise RedScriptApiError(
            f"Почтовый провайдер RedScript не смог обработать запрос: {detail or 'HTTP 424'}",
            status_code=response.status_code,
            payload=data,
        )

    if response.status_code >= 400:
        err = data.get("error")
        if isinstance(err, dict):
            err = err.get("detail") or str(err)
        raise RedScriptApiError(
            f"Ошибка RedScript API: {err or f'HTTP {response.status_code}'}",
            status_code=response.status_code,
            payload=data,
        )

    if data.get("status") is False:
        err = data.get("error")
        if isinstance(err, dict):
            err = err.get("detail") or str(err)
        raise RedScriptApiError(
            f"RedScript API вернул ошибку: {err or 'неизвестная ошибка'}",
            status_code=response.status_code,
            payload=data,
        )

    return data


def check_token(access_token: str) -> dict[str, Any]:
    token = (access_token or "").strip()
    if not token:
        raise RedScriptApiError("Пустой API ключ")

    return _post("/team/getMe", {"access_token": token})


def send_mail(
    access_token: str,
    *,
    email: str,
    mail_service: str,
    country: str,
    type_value: str,
    service: str,
    version: str,
    name: str,
    amount: str | int | float,
    image: str | None = None,
    initials: str | None = None,
    address: str | None = None,
    appid: str | None = None,
) -> dict[str, Any]:
    token = (access_token or "").strip()
    if not token:
        raise RedScriptApiError("Пустой API ключ")

    payload: dict[str, Any] = {
        "access_token": token,
        "email": (email or "").strip(),
        "mail_service": (mail_service or "").strip(),
        "country": (country or "").strip(),
        "type": (type_value or "").strip(),
        "service": (service or "").strip(),
        "version": (version or "").strip(),
        "name": (name or "").strip(),
        "amount": amount,
    }

    if image:
        payload["image"] = image.strip()

    if initials:
        payload["initials"] = initials.strip()

    if address:
        payload["address"] = address.strip()

    if appid:
        payload["appid"] = appid.strip()

    return _post("/team/sendMail", payload)