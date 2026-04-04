from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class MarketPolicy:
    code: str
    platform: str
    country_code: str
    label: str

    base_url: str
    home_url: str
    account_url: str
    dialogs_url: str

    allowed_domains: tuple[str, ...]
    cookie_domains: tuple[str, ...]

    currency_code: str
    currency_symbol: str
    decimal_separator: str
    thousands_separator: str
    default_locale: str

    price_decimals: int = 2
    ad_url_prefixes: tuple[str, ...] = field(default_factory=tuple)

    def is_allowed_domain(self, domain: str | None) -> bool:
        raw = (domain or "").strip().lower()
        if not raw:
            return False
        return any(raw == item or raw.endswith(f".{item}") for item in self.allowed_domains)

    def is_cookie_domain_allowed(self, domain: str | None) -> bool:
        raw = (domain or "").strip().lower().lstrip(".")
        if not raw:
            return False
        return any(raw == item or raw.endswith(f".{item}") for item in self.cookie_domains)

    def is_market_url(self, url: str | None) -> bool:
        raw = (url or "").strip().lower()
        if not raw:
            return False

        prefixes = self.ad_url_prefixes or (self.base_url,)
        return any(raw.startswith(prefix.lower()) for prefix in prefixes)

    def normalize_price_value(self, value: str | int | float | None) -> str:
        if value is None:
            return ""

        if isinstance(value, (int, float)):
            numeric = float(value)
        else:
            text = str(value).strip()
            if not text:
                return ""

            cleaned = (
                text.replace(self.currency_symbol, "")
                .replace("€", "")
                .replace("$", "")
                .replace("£", "")
                .replace("\xa0", " ")
                .strip()
            )

            cleaned = cleaned.replace(self.thousands_separator, "")
            cleaned = cleaned.replace(" ", "")
            cleaned = cleaned.replace(",", ".")
            try:
                numeric = float(cleaned)
            except Exception:
                return text

        formatted = f"{numeric:.{self.price_decimals}f}"
        integer_part, decimal_part = formatted.split(".")
        return f"{integer_part}{self.decimal_separator}{decimal_part}"