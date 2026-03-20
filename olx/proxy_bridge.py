from __future__ import annotations

from dataclasses import dataclass


DEFAULT_BRIDGE_HOST = "127.0.0.1"
DEFAULT_BRIDGE_PORT = 8118


@dataclass(slots=True, frozen=True)
class BridgeConfig:
    bridge_host: str = DEFAULT_BRIDGE_HOST
    bridge_port: int = DEFAULT_BRIDGE_PORT

    @property
    def server(self) -> str:
        return f"http://{self.bridge_host}:{self.bridge_port}"


def validate_source_proxy_text(proxy_text: str) -> str:
    """
    Нам важно не допускать запуск без клиентского прокси.
    Даже если Playwright фактически идёт через локальный Privoxy,
    снаружи мы всё равно требуем, чтобы у пользователя был задан proxy_text.
    """
    value = (proxy_text or "").strip()
    if not value:
        raise ValueError("Не передан клиентский proxy")
    return value


def build_bridge_proxy_settings(
    proxy_text: str,
    bridge_host: str = DEFAULT_BRIDGE_HOST,
    bridge_port: int = DEFAULT_BRIDGE_PORT,
) -> dict[str, str]:
    """
    Возвращает proxy-конфиг для Playwright.
    На данном этапе client SOCKS5 уже должен быть подключён в Privoxy снаружи.
    """
    validate_source_proxy_text(proxy_text)

    config = BridgeConfig(
        bridge_host=bridge_host,
        bridge_port=bridge_port,
    )
    return {"server": config.server}


def get_bridge_server(
    bridge_host: str = DEFAULT_BRIDGE_HOST,
    bridge_port: int = DEFAULT_BRIDGE_PORT,
) -> str:
    return f"http://{bridge_host}:{bridge_port}"