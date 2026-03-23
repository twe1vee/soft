from __future__ import annotations

from typing import Any
import json
from pathlib import Path
from datetime import datetime


def base_result() -> dict[str, Any]:
    return {
        "ok": False,
        "sent": False,
        "status": None,
        "error": None,
        "ad_url": None,
        "final_url": None,
        "bridge_server": None,
        "message_length": 0,
        "page_title": None,
        "input_found": False,
        "message_button_clicked": False,
        "send_button_found": False,
        "submit_button_visible_before_click": None,
        "submit_button_text_before_click": None,
        "submit_button_visible_after_click": None,
        "submit_button_text_after_click": None,
        "debug_chat_root_found": False,
        "debug_login_hint_found": False,
        "handled_soft_error_page": False,
        "debug_html_path": None,
        "debug_png_path": None,
        "debug_json_path": None,
        "debug_html_error": None,
        "debug_png_error": None,
        "debug_json_error": None,
        "chat_button_still_visible_after_click": None,
        "chat_button_text_after_click": None,
        "post_send_message_visible": False,
        "post_send_input_empty": False,
        "post_send_chat_root_found": False,
        "post_send_body_has_text": False,
        "post_send_url": None,
        "delivery_verified": False,
        "post_send_exact_message_match_count": 0,
    }


def debug_dir() -> Path:
    path = Path("debug_artifacts")
    path.mkdir(parents=True, exist_ok=True)
    return path


def debug_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def normalize_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def first_non_empty_text(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


async def safe_locator_text(locator) -> str:
    try:
        text = await locator.inner_text()
        return normalize_text(text)
    except Exception:
        return ""


async def save_debug_artifacts(page, result: dict, prefix: str = "send_debug") -> dict:
    stamp = debug_stamp()
    artifacts_dir = debug_dir()

    html_path = artifacts_dir / f"{prefix}_{stamp}.html"
    png_path = artifacts_dir / f"{prefix}_{stamp}.png"
    json_path = artifacts_dir / f"{prefix}_{stamp}.json"

    try:
        html = await page.content()
        html_path.write_text(html, encoding="utf-8")
        result["debug_html_path"] = str(html_path)
    except Exception as exc:
        result["debug_html_error"] = str(exc)

    try:
        await page.screenshot(path=str(png_path), full_page=True)
        result["debug_png_path"] = str(png_path)
    except Exception as exc:
        result["debug_png_error"] = str(exc)

    try:
        json_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result["debug_json_path"] = str(json_path)
    except Exception as exc:
        result["debug_json_error"] = str(exc)

    return result