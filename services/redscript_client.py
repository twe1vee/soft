from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import httpx

BASE_URL = "https://api.redscript.info"
DEFAULT_TIMEOUT_SECONDS = 45.0


class RedScriptApiError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        payload: dict | None = None,
        raw_text: str | None = None,
        is_ambiguous_success: bool = False,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}
        self.raw_text = raw_text or ""
        self.is_ambiguous_success = is_ambiguous_success


def _debug_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if k != "access_token"}


async def _request_once(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json; charset=UTF-8"}

    debug_payload = _debug_payload(payload)
    print(f"[redscript] POST {path} payload={json.dumps(debug_payload, ensure_ascii=False)}")

    timeout = httpx.Timeout(DEFAULT_TIMEOUT_SECONDS)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.ReadTimeout as exc:
        print(f"[redscript] timeout path={path} error={exc}")
        ambiguous = path == "/team/sendMail"
        raise RedScriptApiError(
            (
                "Ответ от RedScript не пришёл вовремя. Письмо могло быть уже отправлено."
                if ambiguous
                else f"Сбой сети при запросе к RedScript API: {exc}"
            ),
            raw_text="",
            is_ambiguous_success=ambiguous,
        ) from exc
    except httpx.HTTPError as exc:
        print(f"[redscript] network_error path={path} error={exc}")
        raise RedScriptApiError(
            f"Сбой сети при запросе к RedScript API: {exc}",
            raw_text="",
        ) from exc

    raw_text = (response.text or "").strip()
    print(f"[redscript] RESPONSE {path} status={response.status_code} body={raw_text[:4000]}")

    try:
        data = response.json()
    except Exception:
        raise RedScriptApiError(
            f"RedScript API вернул неожиданный ответ: HTTP {response.status_code} {raw_text[:300]}",
            status_code=response.status_code,
            raw_text=raw_text,
        )

    if response.status_code == 429:
        raise RedScriptApiError(
            "Превышен лимит запросов RedScript API. Попробуйте чуть позже.",
            status_code=response.status_code,
            payload=data,
            raw_text=raw_text,
        )

    if response.status_code == 424:
        detail = data.get("error")
        if isinstance(detail, dict):
            detail = detail.get("detail") or str(detail)
        raise RedScriptApiError(
            f"Почтовый провайдер RedScript не смог обработать запрос: {detail or 'HTTP 424'}",
            status_code=response.status_code,
            payload=data,
            raw_text=raw_text,
        )

    if response.status_code >= 400:
        err = data.get("error")
        if isinstance(err, dict):
            err = err.get("detail") or str(err)
        raise RedScriptApiError(
            f"Ошибка RedScript API: {err or f'HTTP {response.status_code}'}",
            status_code=response.status_code,
            payload=data,
            raw_text=raw_text,
        )

    if data.get("status") is False:
        err = data.get("error")
        if isinstance(err, dict):
            err = err.get("detail") or str(err)
        raise RedScriptApiError(
            f"RedScript API вернул ошибку: {err or 'неизвестная ошибка'}",
            status_code=response.status_code,
            payload=data,
            raw_text=raw_text,
        )

    return data


async def check_token(access_token: str) -> dict[str, Any]:
    token = (access_token or "").strip()
    if not token:
        raise RedScriptApiError("Пустой API ключ")

    payload = {"access_token": token}
    return await _request_once("/team/getMe", payload)


async def send_mail(
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
        "client_request_id": str(uuid4()),
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

    return await _request_once("/team/sendMail", payload)