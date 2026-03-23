from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


_RUNTIME_LOCK = threading.Lock()

MANAGED_BEGIN = "# === OLX_SOFT_MANAGED_FORWARD_BEGIN ==="
MANAGED_END = "# === OLX_SOFT_MANAGED_FORWARD_END ==="


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _state_dir() -> Path:
    raw = _env("OLX_PRIVOXY_STATE_DIR")
    if raw:
        path = Path(raw)
    else:
        path = Path(tempfile.gettempdir()) / "olx_soft_privoxy_runtime"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _state_file() -> Path:
    return _state_dir() / "state.json"


def _runtime_config_file() -> Path:
    return _state_dir() / "privoxy_runtime.conf"


def _default_listen_host() -> str:
    return _env("OLX_PRIVOXY_LISTEN_HOST", "127.0.0.1") or "127.0.0.1"


def _default_listen_port() -> int:
    return int(_env("OLX_PRIVOXY_LISTEN_PORT", "8118") or "8118")


def _privoxy_executable() -> str:
    return _env("OLX_PRIVOXY_EXE", "privoxy.exe" if os.name == "nt" else "privoxy") or "privoxy"


def _privoxy_base_config() -> Path:
    raw = _env("OLX_PRIVOXY_BASE_CONFIG")
    if not raw:
        raise RuntimeError(
            "Не задан OLX_PRIVOXY_BASE_CONFIG. "
            "Укажи путь к твоему рабочему base-config Privoxy."
        )

    path = Path(raw)
    if not path.exists():
        raise RuntimeError(f"Не найден base-config Privoxy: {path}")

    return path


def parse_source_proxy_text(proxy_text: str) -> dict:
    raw = (proxy_text or "").strip()
    if not raw:
        raise ValueError("Пустой proxy_text")

    parts = raw.split(":")
    if len(parts) not in (2, 4):
        raise ValueError(
            "Неверный формат proxy_text. Используй host:port или host:port:login:password"
        )

    host = (parts[0] or "").strip()
    if not host:
        raise ValueError("Пустой host в proxy_text")

    port_raw = (parts[1] or "").strip()
    if not port_raw.isdigit():
        raise ValueError("Port должен быть числом")

    port = int(port_raw)
    if port < 1 or port > 65535:
        raise ValueError("Port вне диапазона 1..65535")

    username = None
    password = None

    if len(parts) == 4:
        username = (parts[2] or "").strip()
        password = (parts[3] or "").strip()

        if not username:
            raise ValueError("Пустой login в proxy_text")
        if not password:
            raise ValueError("Пустой password в proxy_text")

    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "raw": raw,
    }


def validate_source_proxy_text(proxy_text: str) -> str:
    parsed = parse_source_proxy_text(proxy_text)
    return parsed["raw"]


def _proxy_key(proxy_text: str) -> str:
    normalized = validate_source_proxy_text(proxy_text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _managed_forward_block(proxy_text: str) -> str:
    proxy = parse_source_proxy_text(proxy_text)
    host = proxy["host"]
    port = proxy["port"]
    username = proxy["username"]
    password = proxy["password"]

    if username and password:
        forward_line = f"forward-socks5   /   {username}:{password}@{host}:{port} ."
    else:
        forward_line = f"forward-socks5   /   {host}:{port} ."

    lines = [
        "",
        MANAGED_BEGIN,
        "forward   127.*.*.*/     .",
        "forward   localhost/     .",
        forward_line,
        MANAGED_END,
        "",
    ]
    return "\n".join(lines)


def _strip_previous_managed_block(text: str) -> str:
    if MANAGED_BEGIN not in text or MANAGED_END not in text:
        return text

    before, _, tail = text.partition(MANAGED_BEGIN)
    _, _, after = tail.partition(MANAGED_END)
    return before.rstrip() + "\n" + after.lstrip()


def _build_runtime_config(base_config_text: str, proxy_text: str) -> str:
    cleaned = _strip_previous_managed_block(base_config_text)
    return cleaned.rstrip() + "\n" + _managed_forward_block(proxy_text)


def _load_state() -> dict:
    path = _state_file()
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    _state_file().write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_runtime_config(proxy_text: str) -> Path:
    base_config_path = _privoxy_base_config()
    base_text = base_config_path.read_text(encoding="utf-8")
    runtime_text = _build_runtime_config(base_text, proxy_text)

    runtime_path = _runtime_config_file()
    runtime_path.write_text(runtime_text, encoding="utf-8")
    return runtime_path


def _is_windows() -> bool:
    return os.name == "nt"


def _is_pid_alive(pid: int | None) -> bool:
    if not pid:
        return False

    try:
        if _is_windows():
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = (result.stdout or "") + "\n" + (result.stderr or "")
            return str(pid) in output
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


def _stop_existing_privoxy() -> None:
    state = _load_state()
    pid = state.get("pid")

    if pid and _is_pid_alive(pid):
        try:
            if _is_windows():
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            else:
                os.kill(pid, 15)
        except Exception:
            pass

    if _is_windows():
        try:
            subprocess.run(
                ["taskkill", "/IM", "privoxy.exe", "/F"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception:
            pass


def _launch_privoxy(runtime_config_path: Path) -> int:
    exe = _privoxy_executable()

    if _is_windows():
        creationflags = 0
        creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

        proc = subprocess.Popen(
            [exe, str(runtime_config_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=False,
        )
    else:
        proc = subprocess.Popen(
            [exe, str(runtime_config_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            close_fds=True,
        )

    return proc.pid


def _wait_until_port_ready(host: str, port: int, timeout_sec: float = 15.0) -> bool:
    deadline = time.time() + timeout_sec

    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.5):
                return True
        except Exception:
            time.sleep(0.25)

    return False


def ensure_privoxy_route(proxy_text: str) -> dict:
    with _RUNTIME_LOCK:
        normalized = validate_source_proxy_text(proxy_text)
        key = _proxy_key(normalized)
        listen_host = _default_listen_host()
        listen_port = _default_listen_port()

        state = _load_state()
        current_key = state.get("proxy_key")
        current_pid = state.get("pid")
        runtime_path = _runtime_config_file()

        if (
            current_key == key
            and current_pid
            and _is_pid_alive(current_pid)
            and runtime_path.exists()
            and _wait_until_port_ready(listen_host, listen_port, timeout_sec=1.0)
        ):
            return {
                "listen_host": listen_host,
                "listen_port": listen_port,
                "runtime_config": str(runtime_path),
                "pid": current_pid,
                "changed": False,
            }

        runtime_path = _write_runtime_config(normalized)
        _stop_existing_privoxy()
        pid = _launch_privoxy(runtime_path)

        if not _wait_until_port_ready(listen_host, listen_port, timeout_sec=15.0):
            raise RuntimeError(
                f"Privoxy не поднялся на {listen_host}:{listen_port} после переключения proxy"
            )

        new_state = {
            "proxy_key": key,
            "proxy_text": normalized,
            "pid": pid,
            "runtime_config": str(runtime_path),
            "listen_host": listen_host,
            "listen_port": listen_port,
        }
        _save_state(new_state)

        return {
            "listen_host": listen_host,
            "listen_port": listen_port,
            "runtime_config": str(runtime_path),
            "pid": pid,
            "changed": True,
        }