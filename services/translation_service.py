from __future__ import annotations

from typing import Any

import argostranslate.translate


DEFAULT_FROM_CODE = "pt"
DEFAULT_TO_CODE = "ru"


def _normalize_text(text: str | None) -> str:
    return (text or "").strip()


def _find_installed_language(code: str):
    installed_languages = argostranslate.translate.get_installed_languages()
    return next((lang for lang in installed_languages if lang.code == code), None)


def _get_translation(from_code: str, to_code: str):
    from_lang = _find_installed_language(from_code)
    to_lang = _find_installed_language(to_code)

    if not from_lang or not to_lang:
        return None

    try:
        return from_lang.get_translation(to_lang)
    except Exception:
        return None


def is_translation_ready(
    *,
    from_code: str = DEFAULT_FROM_CODE,
    to_code: str = DEFAULT_TO_CODE,
) -> bool:
    return _get_translation(from_code, to_code) is not None


def translate_to_russian(
    text: str,
    *,
    from_code: str = DEFAULT_FROM_CODE,
    to_code: str = DEFAULT_TO_CODE,
) -> dict[str, Any]:
    clean_text = _normalize_text(text)

    result: dict[str, Any] = {
        "ok": False,
        "provider": "argos",
        "source_lang": from_code,
        "target_lang": to_code,
        "translated_text": None,
        "error": None,
        "skipped": False,
    }

    if not clean_text:
        result["skipped"] = True
        result["error"] = "empty_text"
        return result

    translation = _get_translation(from_code, to_code)
    if translation is None:
        result["error"] = f"translation_pair_not_ready:{from_code}->{to_code}"
        return result

    try:
        translated_text = (translation.translate(clean_text) or "").strip()
        if not translated_text:
            result["error"] = "empty_translation"
            return result

        result["ok"] = True
        result["translated_text"] = translated_text
        return result
    except Exception as exc:
        result["error"] = f"argos_exception:{exc}"
        return result