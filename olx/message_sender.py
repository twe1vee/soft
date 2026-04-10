from __future__ import annotations

import time

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from db import get_active_template
from olx.account_runtime import close_runtime_page, open_account_runtime_page
from olx.browser_session import dismiss_cookie_banner_if_present
from olx.chat_open_guard import ensure_chat_open
from olx.markets.helpers import extract_url_domain, is_market_domain
from olx.markets.message_helpers import get_delivery_failed_texts
from olx.message_sender_chat import collect_chat_diagnostics
from olx.message_sender_debug import (
    base_result,
    normalize_text,
    safe_locator_text,
    save_debug_artifacts,
)
from olx.message_sender_page import (
    handle_olx_soft_error_page,
    is_cloudfront_block_page,
)
from olx.message_sender_submit import (
    attach_template_image,
    click_send_button,
    fill_message_input,
    verify_message_sent,
)

DEFAULT_SEND_MARKET = "olx_pt"


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


async def _has_daily_limit_banner(
    page,
    *,
    market_code: str = DEFAULT_SEND_MARKET,
) -> bool:
    phrases_map = {
        "olx_pt": [
            "atingiste o limite de novas conversas por dia",
            "limite de novas conversas por dia",
            "limite de novas conversas",
        ],
        "olx_pl": [
            "osiągnięto limit nowych rozmów na dziś",
            "osiagnieto limit nowych rozmow na dzis",
            "limit nowych rozmów dziennie",
            "limit nowych rozmow dziennie",
            "limit nowych rozmów",
            "limit nowych rozmow",
        ],
    }

    phrases = phrases_map.get((market_code or "").strip().lower(), phrases_map["olx_pt"])

    try:
        body = await page.locator("body").inner_text(timeout=2000)
    except Exception:
        body = ""

    body_norm = (body or "").strip().lower()
    if any(phrase in body_norm for phrase in phrases):
        return True

    for phrase in phrases:
        try:
            locator = page.get_by_text(phrase, exact=False)
            if await locator.count() > 0 and await locator.first.is_visible():
                return True
        except Exception:
            continue

    return False


def _detect_market_mismatch(
    ad_url: str,
    market_code: str,
) -> str | None:
    domain = extract_url_domain(ad_url)
    if not domain:
        return None

    if is_market_domain(domain, market_code):
        return None

    return (
        f"Ссылка объявления относится к другому рынку: {domain}. "
        f"Аккаунт работает на рынке {market_code}."
    )


def _normalize_olx_url_for_compare(url: str | None) -> str:
    text = (url or "").strip()
    if not text:
        return ""

    if "?" in text:
        base, query = text.split("?", 1)
        allowed_parts = []

        for part in query.split("&"):
            part = part.strip()
            if not part:
                continue
            if part.startswith("chat="):
                continue
            if part.startswith("isPreviewActive="):
                continue
            allowed_parts.append(part)

        text = base if not allowed_parts else f"{base}?{'&'.join(allowed_parts)}"

    return text.rstrip("/")


def _is_same_ad_page(current_url: str | None, ad_url: str | None) -> bool:
    current_norm = _normalize_olx_url_for_compare(current_url)
    ad_norm = _normalize_olx_url_for_compare(ad_url)

    if not current_norm or not ad_norm:
        return False

    return current_norm == ad_norm


async def _read_effective_input_text(input_locator) -> str:
    try:
        value = await input_locator.input_value()
        return value or ""
    except Exception:
        pass

    try:
        value = await input_locator.evaluate("(el) => el.value || el.textContent || ''")
        return value or ""
    except Exception:
        return ""


async def send_message_to_ad(
    cookies_json: str,
    proxy_text: str,
    ad_url: str,
    message_text: str,
    *,
    headless: bool = True,
    user_id: int | None = None,
    account_id: int | None = None,
    olx_profile_name: str | None = None,
    market_code: str = DEFAULT_SEND_MARKET,
) -> dict:
    result = base_result()
    result["ad_url"] = ad_url
    result["message_length"] = len(message_text or "")
    result["browser_engine"] = "gologin"
    result["gologin_profile_id"] = None
    result["gologin_profile_name"] = None
    result["debugger_address"] = None
    result["message_button_clicked"] = False
    result["message_button_clicked_retry"] = False
    result["chat_button_retry_debug"] = None
    result["chat_button_still_visible_after_click"] = None
    result["chat_button_text_after_click"] = None
    result["chat_button_still_visible_after_retry"] = None
    result["chat_button_text_after_retry"] = None
    result["input_found"] = False
    result["send_button_found"] = False
    result["daily_limit_reached"] = False
    result["personal_data_warning_possible"] = False
    result["personal_data_warning_handled"] = False
    result["submit_button_was_disabled_before_click"] = None
    result["recovered_by_reload"] = False
    result["timings_ms"] = {}
    result["final_message_text"] = message_text
    result["market_code"] = market_code

    result["template_image_requested"] = False
    result["template_image_path"] = None
    result["template_image_attached"] = False
    result["template_image_preview_visible"] = False
    result["template_image_error"] = None
    result["template_image_filename"] = None
    result["template_image_removed_old_previews"] = 0

    result["sanitized_message_detected"] = False
    result["original_message_text"] = message_text
    result["effective_message_text"] = None

    if not (ad_url or "").strip():
        result["status"] = "invalid_input"
        result["error"] = "Пустой ad_url"
        return result

    if not (message_text or "").strip():
        result["status"] = "invalid_input"
        result["error"] = "Пустой message_text"
        return result

    market_mismatch_error = _detect_market_mismatch(ad_url, market_code)
    if market_mismatch_error:
        result["status"] = "market_mismatch"
        result["error"] = market_mismatch_error
        return result

    page = None
    runtime_entry = None
    t_total = time.perf_counter()

    try:
        t_step = time.perf_counter()

        if not account_id or int(account_id) <= 0:
            result["status"] = "invalid_input"
            result["error"] = f"Некорректный account_id для send_message: {account_id}"
            return result

        page, runtime_entry = await open_account_runtime_page(
            user_id=user_id,
            account_id=int(account_id),
            cookies_json=cookies_json,
            proxy_text=proxy_text,
            url=ad_url,
            headless=headless,
            olx_profile_name=olx_profile_name,
            timeout=90000,
            wait_after_ms=1200,
            busy_reason="send_message",
        )
        result["timings_ms"]["open_account_runtime_page"] = _elapsed_ms(t_step)

        result["browser_engine"] = runtime_entry.runtime.get("browser_engine", "gologin")
        result["gologin_profile_id"] = runtime_entry.runtime.get("gologin_profile_id")
        result["gologin_profile_name"] = runtime_entry.runtime.get("gologin_profile_name")
        result["debugger_address"] = runtime_entry.runtime.get("debugger_address")

        try:
            await page.set_viewport_size({"width": 1440, "height": 1100})
            await page.wait_for_timeout(200)
        except Exception:
            pass

        result["final_url"] = page.url
        try:
            result["page_title"] = await page.title()
        except Exception:
            pass

        if await is_cloudfront_block_page(page):
            result["status"] = "cloudfront_blocked"
            result["error"] = "OLX/CloudFront заблокировал запрос и вернул 403 block page"
            result["timings_ms"]["total"] = _elapsed_ms(t_total)
            await save_debug_artifacts(page, result, prefix="cloudfront_blocked")
            return result

        handled_soft_error = await handle_olx_soft_error_page(page, market_code=market_code)
        result["handled_soft_error_page"] = handled_soft_error

        if handled_soft_error:
            try:
                result["page_title"] = await page.title()
            except Exception:
                pass
            result["final_url"] = page.url

        if await is_cloudfront_block_page(page):
            result["status"] = "cloudfront_blocked"
            result["error"] = "OLX/CloudFront заблокировал запрос и вернул 403 block page"
            result["timings_ms"]["total"] = _elapsed_ms(t_total)
            await save_debug_artifacts(page, result, prefix="cloudfront_blocked")
            return result

        t_step = time.perf_counter()
        await dismiss_cookie_banner_if_present(page)
        await page.wait_for_timeout(300)
        result["timings_ms"]["dismiss_cookie_banner"] = _elapsed_ms(t_step)

        t_step = time.perf_counter()
        result.update(await collect_chat_diagnostics(page))
        result["timings_ms"]["collect_chat_diagnostics_initial"] = _elapsed_ms(t_step)

        t_step = time.perf_counter()
        chat_open = await ensure_chat_open(
            page,
            target_url=ad_url,
            allow_reload=True,
            settle_ms=700,
            market_code=market_code,
        )
        input_locator = chat_open.get("input_locator")

        for key in (
            "message_button_clicked",
            "message_button_clicked_retry",
            "chat_button_retry_debug",
            "chat_button_still_visible_after_click",
            "chat_button_text_after_click",
            "chat_button_still_visible_after_retry",
            "chat_button_text_after_retry",
            "clicked_candidate",
            "clicked_candidate_debug",
            "click_mode",
            "chat_button_candidates",
            "recovered_by_reload",
            "debug_login_hint_found",
            "debug_blocking_chat_gate_found",
            "debug_chat_root_found",
            "debug_message_input_found",
            "debug_message_input_tag",
            "debug_message_input_placeholder",
            "debug_message_input_name",
            "handled_soft_error_page",
        ):
            if key in chat_open:
                result[key] = chat_open.get(key)

        result["final_url"] = page.url

        if not _is_same_ad_page(page.url, ad_url):
            result["timings_ms"]["find_or_open_chat"] = _elapsed_ms(t_step)
            result["status"] = "message_input_not_found"
            result["error"] = (
                "После retry/reload страница ушла со страницы объявления. "
                "Send-flow остановлен до ввода сообщения."
            )
            result["timings_ms"]["total"] = _elapsed_ms(t_total)
            await save_debug_artifacts(page, result, prefix="message_input_wrong_page")
            return result

        result["daily_limit_reached"] = await _has_daily_limit_banner(page, market_code=market_code)

        if chat_open.get("cloudfront_blocked"):
            result["timings_ms"]["find_or_open_chat"] = _elapsed_ms(t_step)
            result["status"] = "cloudfront_blocked"
            result["error"] = "OLX/CloudFront заблокировал запрос и вернул 403 block page"
            result["timings_ms"]["total"] = _elapsed_ms(t_total)
            await save_debug_artifacts(page, result, prefix="cloudfront_blocked")
            return result

        if input_locator is None:
            result["timings_ms"]["find_or_open_chat"] = _elapsed_ms(t_step)

            if result.get("daily_limit_reached"):
                result["status"] = "daily_limit_reached"
                result["error"] = "OLX показал лимит на новые диалоги за день"
                result["timings_ms"]["total"] = _elapsed_ms(t_total)
                await save_debug_artifacts(page, result, prefix="daily_limit_reached")
                return result

            if result.get("debug_login_hint_found") or result.get("debug_blocking_chat_gate_found"):
                result["status"] = "login_required_or_chat_blocked"
                result["error"] = (
                    "После попыток открыть чат открылся логин/блокирующий интерфейс "
                    "вместо поля ввода"
                )
                result["timings_ms"]["total"] = _elapsed_ms(t_total)
                await save_debug_artifacts(page, result, prefix="login_required_or_chat_blocked")
                return result

            result["status"] = "message_input_not_found"
            result["error"] = (
                "Не найдено поле ввода сообщения после retry открытия чата "
                "и одного reload страницы"
            )
            result["timings_ms"]["total"] = _elapsed_ms(t_total)
            await save_debug_artifacts(page, result, prefix="message_input_not_found")
            return result

        result["timings_ms"]["find_or_open_chat"] = _elapsed_ms(t_step)
        result["input_found"] = True

        t_step = time.perf_counter()
        result.update(await collect_chat_diagnostics(page))
        result["timings_ms"]["collect_chat_diagnostics_before_fill"] = _elapsed_ms(t_step)

        result["final_url"] = page.url

        if not _is_same_ad_page(page.url, ad_url):
            result["status"] = "message_input_not_found"
            result["error"] = (
                "Перед вводом сообщения страница уже не совпадала со страницей объявления."
            )
            result["timings_ms"]["total"] = _elapsed_ms(t_total)
            await save_debug_artifacts(page, result, prefix="message_input_wrong_page")
            return result

        template_image_path = None
        if user_id:
            try:
                template = get_active_template(int(user_id))
                template_image_path = (template.get("image_path") if template else "") or None
            except Exception:
                template_image_path = None

        if template_image_path:
            t_step = time.perf_counter()
            attach_result = await attach_template_image(page, template_image_path)
            result.update(attach_result)
            result["timings_ms"]["attach_template_image"] = _elapsed_ms(t_step)

            if not attach_result.get("template_image_attached"):
                result["status"] = "attachment_upload_failed"
                result["error"] = attach_result.get("template_image_error") or "Не удалось прикрепить фото шаблона"
                result["timings_ms"]["total"] = _elapsed_ms(t_total)
                await save_debug_artifacts(page, result, prefix="attachment_upload_failed")
                return result

            await page.wait_for_timeout(250)

        t_step = time.perf_counter()
        await fill_message_input(input_locator, message_text)
        result["timings_ms"]["fill_message_input"] = _elapsed_ms(t_step)

        await page.wait_for_timeout(250)

        effective_message_text = await _read_effective_input_text(input_locator)
        result["effective_message_text"] = effective_message_text

        original_norm = normalize_text(message_text)
        effective_norm = normalize_text(effective_message_text)

        if effective_norm != original_norm:
            result["sanitized_message_detected"] = True
            result["status"] = "message_contains_disallowed_characters"
            result["error"] = (
                "OLX изменил текст сообщения и удалил часть символов. "
                "Скорее всего, в шаблоне есть запрещённые или нестандартные символы. "
                "Измените текст шаблона и попробуйте снова."
            )
            result["timings_ms"]["total"] = _elapsed_ms(t_total)
            await save_debug_artifacts(
                page,
                result,
                prefix="message_contains_disallowed_characters",
            )
            return result

        try:
            submit_btn = page.locator('button[aria-label="Submit message"]').first
            submit_btn_exists = await submit_btn.count() > 0
            submit_btn_visible = submit_btn_exists and await submit_btn.is_visible()

            result["submit_button_visible_before_click"] = submit_btn_visible
            result["submit_button_text_before_click"] = await safe_locator_text(submit_btn)

            disabled_attr_before = await submit_btn.get_attribute("disabled") if submit_btn_exists else None
            aria_disabled_before = await submit_btn.get_attribute("aria-disabled") if submit_btn_exists else None

            submit_disabled_before = (
                disabled_attr_before is not None
                or (aria_disabled_before or "").lower() == "true"
            )

            result["submit_button_was_disabled_before_click"] = submit_disabled_before
            result["personal_data_warning_possible"] = bool(submit_btn_visible and submit_disabled_before)
        except Exception:
            result["submit_button_visible_before_click"] = None
            result["submit_button_text_before_click"] = None
            result["submit_button_was_disabled_before_click"] = None
            result["personal_data_warning_possible"] = False

        t_step = time.perf_counter()
        send_click_result = await click_send_button(
            page,
            input_locator,
            market_code=market_code,
        )
        result["timings_ms"]["click_send_button"] = _elapsed_ms(t_step)
        result["send_button_found"] = bool(send_click_result.get("send_clicked"))
        if send_click_result.get("personal_data_warning_handled"):
            result["personal_data_warning_handled"] = True
        send_clicked = bool(send_click_result.get("send_clicked"))

        try:
            submit_btn = page.locator('button[aria-label="Submit message"]').first
            submit_btn_exists = await submit_btn.count() > 0
            submit_btn_visible_after = submit_btn_exists and await submit_btn.is_visible()

            result["submit_button_visible_after_click"] = submit_btn_visible_after
            result["submit_button_text_after_click"] = await safe_locator_text(submit_btn)

            disabled_attr_after = await submit_btn.get_attribute("disabled") if submit_btn_exists else None
            aria_disabled_after = await submit_btn.get_attribute("aria-disabled") if submit_btn_exists else None

            submit_disabled_after = (
                disabled_attr_after is not None
                or (aria_disabled_after or "").lower() == "true"
            )

            if result.get("personal_data_warning_possible") and not submit_disabled_after:
                result["personal_data_warning_handled"] = True
        except Exception:
            result["submit_button_visible_after_click"] = None
            result["submit_button_text_after_click"] = None

        if not send_clicked:
            t_step = time.perf_counter()
            result.update(await collect_chat_diagnostics(page))
            result["timings_ms"]["collect_chat_diagnostics_send_button_not_found"] = _elapsed_ms(
                t_step
            )
            result["daily_limit_reached"] = await _has_daily_limit_banner(page, market_code=market_code)

            if result.get("daily_limit_reached"):
                result["status"] = "daily_limit_reached"
                result["error"] = "OLX показал лимит на новые диалоги за день"
                result["timings_ms"]["total"] = _elapsed_ms(t_total)
                await save_debug_artifacts(page, result, prefix="daily_limit_reached")
                return result

            result["status"] = "send_button_not_found"

            if result.get("personal_data_warning_possible") and not result.get("personal_data_warning_handled"):
                result["error"] = (
                    "OLX показал предупреждение о персональных данных и не дал отправить "
                    "сообщение автоматически."
                )
            else:
                result["error"] = "Не удалось нажать кнопку отправки сообщения"

            result["timings_ms"]["total"] = _elapsed_ms(t_total)
            await save_debug_artifacts(page, result, prefix="send_button_not_found")
            return result

        await page.wait_for_timeout(600)

        t_step = time.perf_counter()
        verification = await verify_message_sent(
            page,
            input_locator,
            message_text,
            market_code=market_code,
        )
        result["timings_ms"]["verify_message_sent"] = _elapsed_ms(t_step)
        result.update(verification)
        result["final_url"] = page.url

        t_step = time.perf_counter()
        result.update(await collect_chat_diagnostics(page))
        result["timings_ms"]["collect_chat_diagnostics_after_verify"] = _elapsed_ms(t_step)

        result["daily_limit_reached"] = await _has_daily_limit_banner(page, market_code=market_code)

        if verification.get("delivery_verified"):
            result["ok"] = True
            result["status"] = "sent"
            result["sent"] = True
            result["timings_ms"]["total"] = _elapsed_ms(t_total)
            await save_debug_artifacts(page, result, prefix="sent_success")
            return result

        if verification.get("delivery_failed"):
            reason = verification.get("delivery_failed_reason") or "OLX показал, что сообщение не доставлено"

            for market_hint in get_delivery_failed_texts(market_code):
                if market_hint and market_hint.lower() in reason.lower():
                    break

            result["status"] = "message_delivery_failed"
            result["error"] = reason
            result["timings_ms"]["total"] = _elapsed_ms(t_total)
            await save_debug_artifacts(page, result, prefix="message_delivery_failed")
            return result

        if result.get("daily_limit_reached"):
            result["status"] = "daily_limit_reached"
            result["error"] = "OLX показал лимит на новые диалоги за день"
            result["timings_ms"]["total"] = _elapsed_ms(t_total)
            await save_debug_artifacts(page, result, prefix="daily_limit_reached")
            return result

        result["status"] = "send_clicked_unverified"

        if result.get("personal_data_warning_possible") and not result.get("personal_data_warning_handled"):
            result["error"] = (
                "OLX показал предупреждение о персональных данных. Отправка началась, "
                "но сайт не подтвердил, что сообщение ушло."
            )
        else:
            result["error"] = (
                "Сообщение не удалось подтвердить автоматически. Возможно, OLX не принял отправку."
            )
        result["timings_ms"]["total"] = _elapsed_ms(t_total)
        await save_debug_artifacts(page, result, prefix="send_clicked_unverified")
        return result

    except PlaywrightTimeoutError as exc:
        result["status"] = "timeout"
        result["error"] = str(exc)
        result["timings_ms"]["total"] = _elapsed_ms(t_total)
        return result

    except Exception as exc:
        result["error"] = str(exc)
        result["status"] = "browser_failed"
        result["timings_ms"]["total"] = _elapsed_ms(t_total)
        try:
            if page is not None:
                await save_debug_artifacts(page, result, prefix=result["status"])
        except Exception:
            pass
        return result

    finally:
        if runtime_entry is not None:
            await close_runtime_page(runtime_entry, page)