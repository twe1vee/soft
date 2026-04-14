from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

import httpx

BASE_URL = "https://api.redscript.info"
DEFAULT_TIMEOUT_SECONDS = 45.0
MAX_REQUESTS_PER_SECOND = 3
MIN_REQUEST_INTERVAL_SECONDS = 1.0 / MAX_REQUESTS_PER_SECOND


class RedScriptApiError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        payload: dict | None = None,
        raw_text: str | None = None,
        is_ambiguous_success: bool = False,
        error_code: str | None = None,
        is_retryable_network: bool = False,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}
        self.raw_text = raw_text or ""
        self.is_ambiguous_success = is_ambiguous_success
        self.error_code = error_code
        self.is_retryable_network = is_retryable_network


_client_lock = asyncio.Lock()
_request_lock = asyncio.Lock()
_shared_client: httpx.AsyncClient | None = None
_last_request_monotonic: float = 0.0


def _debug_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if k != "access_token"}


def _extract_error_code_and_message(data: dict[str, Any], raw_text: str) -> tuple[str | None, str]:
    if not isinstance(data, dict):
        return None, raw_text[:300] or "неизвестная ошибка"

    direct_error = data.get("error")
    main_service = data.get("main_service")

    if isinstance(direct_error, dict):
        msg = (
            direct_error.get("detail")
            or direct_error.get("error_message")
            or direct_error.get("message")
            or str(direct_error)
        )
        code = (
            direct_error.get("error_type")
            or direct_error.get("code")
            or main_service
        )
        return code, str(msg or "неизвестная ошибка")

    if isinstance(direct_error, str):
        stripped = direct_error.strip()

        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                nested = json.loads(stripped)
            except Exception:
                nested = None

            if isinstance(nested, dict):
                msg = (
                    nested.get("detail")
                    or nested.get("error_message")
                    or nested.get("message")
                    or str(nested)
                )
                code = (
                    nested.get("error_type")
                    or nested.get("code")
                    or main_service
                )
                return code, str(msg or stripped)

        if stripped.startswith("ERR_"):
            return stripped, stripped

        return main_service, stripped

    for key, value in data.items():
        if isinstance(key, str) and key.startswith("ERR_"):
            return key, str(value)

    return main_service, raw_text[:300] or "неизвестная ошибка"


def _humanize_api_error(
    *,
    status_code: int | None,
    error_code: str | None,
    message: str,
    path: str,
    is_ambiguous_success: bool,
) -> str:
    text = (message or "").strip()
    code = (error_code or "").strip()

    if is_ambiguous_success:
        return "Ответ от RedScript не пришёл вовремя. Письмо могло быть уже отправлено."

    if status_code == 429:
        return "Превышен лимит запросов RedScript API. Попробуйте чуть позже."

    if code == "ERR_SERVICE_NOT_EXISTS":
        return "В RedScript не найден выбранный сервис."

    if code == "CountryOrServiceError":
        return "В RedScript не подошла комбинация страны и сервиса."

    if code == "HYPE_MAILER_ERROR":
        return f"Почтовый провайдер RedScript не смог обработать запрос: {text or 'ошибка Hype'}"

    if code == "GOSU_MAILER_ERROR":
        return f"Почтовый провайдер RedScript не смог обработать запрос: {text or 'ошибка Gosu'}"

    if status_code == 424:
        return f"Почтовый провайдер RedScript не смог обработать запрос: {text or 'HTTP 424'}"

    if status_code in {401, 403}:
        return "RedScript отклонил доступ. Проверь API ключ."

    if status_code == 404:
        return "RedScript не нашёл нужный эндпоинт."

    if status_code == 422:
        return f"RedScript отклонил параметры запроса: {text or 'HTTP 422'}"

    if status_code and status_code >= 500:
        return f"RedScript временно недоступен: {text or f'HTTP {status_code}'}"

    if path == "/team/getMe":
        return text or "Не удалось проверить API ключ."

    return text or "RedScript вернул ошибку."


async def _get_client() -> httpx.AsyncClient:
    global _shared_client

    async with _client_lock:
        if _shared_client is None or _shared_client.is_closed:
            timeout = httpx.Timeout(DEFAULT_TIMEOUT_SECONDS)
            _shared_client = httpx.AsyncClient(timeout=timeout)
        return _shared_client


async def close_redscript_client() -> None:
    global _shared_client

    async with _client_lock:
        if _shared_client is not None and not _shared_client.is_closed:
            await _shared_client.aclose()
        _shared_client = None


async def _respect_rate_limit() -> None:
    global _last_request_monotonic

    async with _request_lock:
        loop = asyncio.get_running_loop()
        now = loop.time()

        if _last_request_monotonic > 0:
            elapsed = now - _last_request_monotonic
            if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
                await asyncio.sleep(MIN_REQUEST_INTERVAL_SECONDS - elapsed)

        _last_request_monotonic = loop.time()


async def _request_once(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json; charset=UTF-8"}

    debug_payload = _debug_payload(payload)
    print(f"[redscript] POST {path} payload={json.dumps(debug_payload, ensure_ascii=False)}")

    await _respect_rate_limit()
    client = await _get_client()

    try:
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
            is_retryable_network=not ambiguous,
        ) from exc
    except httpx.HTTPError as exc:
        print(f"[redscript] network_error path={path} error={exc}")
        raise RedScriptApiError(
            f"Сбой сети при запросе к RedScript API: {exc}",
            raw_text="",
            is_retryable_network=True,
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

    error_code, error_message = _extract_error_code_and_message(data, raw_text)

    if response.status_code >= 400:
        raise RedScriptApiError(
            _humanize_api_error(
                status_code=response.status_code,
                error_code=error_code,
                message=error_message,
                path=path,
                is_ambiguous_success=False,
            ),
            status_code=response.status_code,
            payload=data,
            raw_text=raw_text,
            error_code=error_code,
            is_retryable_network=response.status_code in {429, 502, 503, 504},
        )

    if data.get("status") is False:
        raise RedScriptApiError(
            _humanize_api_error(
                status_code=response.status_code,
                error_code=error_code,
                message=error_message,
                path=path,
                is_ambiguous_success=False,
            ),
            status_code=response.status_code,
            payload=data,
            raw_text=raw_text,
            error_code=error_code,
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