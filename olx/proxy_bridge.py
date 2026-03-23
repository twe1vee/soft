from __future__ import annotations

from dataclasses import dataclass

from olx.privoxy_pool import ensure_privoxy_instance, validate_source_proxy_text


@dataclass(slots=True, frozen=True)
class BridgeConfig:
    bridge_host: str
    bridge_port: int

    @property
    def server(self) -> str:
        return f"http://{self.bridge_host}:{self.bridge_port}"


def build_bridge_proxy_settings(proxy_text: str) -> dict[str, str]:
    """
    Возвращает proxy-конфиг для Playwright.

    Теперь для каждого source proxy_text используется отдельный локальный
    Privoxy instance на своём порту.
    """
    validate_source_proxy_text(proxy_text)
    instance = ensure_privoxy_instance(proxy_text)

    config = BridgeConfig(
        bridge_host=instance["listen_host"],
        bridge_port=instance["listen_port"],
    )
    return {
        "server": config.server,
    }


def get_bridge_server(proxy_text: str) -> str:
    instance = ensure_privoxy_instance(proxy_text)
    return f"http://{instance['listen_host']}:{instance['listen_port']}"