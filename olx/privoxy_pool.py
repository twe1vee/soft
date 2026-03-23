from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path


_POOL_LOCK = threading.Lock()

MANAGED_BEGIN = "# === OLX_SOFT_MANAGED_FORWARD_BEGIN ==="
MANAGED_END = "# === OLX_SOFT_MANAGED_FORWARD_END ==="


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _privoxy_base_config() -> Path:
    raw = _env("OLX_PRIVOXY_BASE_CONFIG")
    if not raw:
        raise RuntimeError(
            "Не задан OLX_PRIVOXY_BASE_CONFIG. Укажи путь к твоему рабочему base-config Privoxy."
        )

    path = Path(raw)
    if not path.exists():
        raise RuntimeError(f"Не найден base-config Privoxy: {path}")

    return path


def _privoxy_root_dir() -> Path:
    return _privoxy_base_config().parent


def _state_dir() -> Path:
    raw = _env("OLX_PRIVOXY_STATE_DIR")
    if raw:
        path = Path(raw)
    else:
        path = _privoxy_root_dir() / "olx_soft_privoxy_pool"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _pool_state_file() -> Path:
    return _state_dir() / "pool_state.json"


def _instance_dir(proxy_key: str) -> Path:
    path = _state_dir() / proxy_key
    path.mkdir(parents=True, exist_ok=True)
    return path


def _base_port() -> int:
    return int(_env("OLX_PRIVOXY_BASE_PORT", "8118") or "8118")


def _max_instances() -> int:
    return int(_env("OLX_PRIVOXY_MAX_INSTANCES", "50") or "50")


def _listen_host() -> str:
    return _env("OLX_PRIVOXY_LISTEN_HOST", "127.0.0.1") or "127.0.0.1"


def _privoxy_executable() -> str:
    return _env("OLX_PRIVOXY_EXE", "privoxy.exe" if os.name == "nt" else "privoxy") or "privoxy"


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
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _load_pool_state() -> dict:
    path = _pool_state_file()
    if not path.exists():
        return {"instances": {}}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"instances": {}}
        if "instances" not in data or not isinstance(data["instances"], dict):
            data["instances"] = {"instances": {}}
        return data
    except Exception:
        return {"instances": {}}


def _save_pool_state(state: dict) -> None:
    _pool_state_file().write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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


def _is_port_open(host: str, port: int, timeout_sec: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True
    except Exception:
        return False


def _wait_until_port_ready(host: str, port: int, timeout_sec: float = 15.0) -> bool:
    deadline = time.time() + timeout_sec

    while time.time() < deadline:
        if _is_port_open(host, port, timeout_sec=1.0):
            return True
        time.sleep(0.25)

    return False


def _stop_pid(pid: int | None) -> None:
    if not pid:
        return

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


def _strip_previous_managed_block(text: str) -> str:
    if MANAGED_BEGIN not in text or MANAGED_END not in text:
        return text

    before, _, tail = text.partition(MANAGED_BEGIN)
    _, _, after = tail.partition(MANAGED_END)
    return before.rstrip() + "\n" + after.lstrip()


def _build_managed_forward_block(proxy_text: str) -> str:
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


def _build_runtime_config(base_config_text: str, proxy_text: str, listen_host: str, listen_port: int) -> str:
    cleaned = _strip_previous_managed_block(base_config_text)

    lines = cleaned.splitlines()
    filtered = []

    for line in lines:
        stripped = line.strip().lower()

        if stripped.startswith("listen-address"):
            continue

        filtered.append(line)

    filtered.append(f"listen-address {listen_host}:{listen_port}")
    filtered.append(_build_managed_forward_block(proxy_text))

    return "\n".join(filtered).rstrip() + "\n"


def _find_free_port(start_port: int, max_instances: int, host: str, used_ports: set[int]) -> int:
    for port in range(start_port, start_port + max_instances):
        if port in used_ports:
            continue
        if not _is_port_open(host, port, timeout_sec=0.3):
            return port

    raise RuntimeError("Не удалось найти свободный порт для нового Privoxy instance")


def _write_runtime_config(proxy_key: str, proxy_text: str, listen_host: str, listen_port: int) -> Path:
    base_config_path = _privoxy_base_config()
    base_text = base_config_path.read_text(encoding="utf-8")

    runtime_text = _build_runtime_config(
        base_config_text=base_text,
        proxy_text=proxy_text,
        listen_host=listen_host,
        listen_port=listen_port,
    )

    instance_path = _instance_dir(proxy_key)
    runtime_config_path = instance_path / "privoxy_runtime.conf"
    runtime_config_path.write_text(runtime_text, encoding="utf-8")
    return runtime_config_path


def _launch_privoxy(runtime_config_path: Path) -> int:
    exe = _privoxy_executable()
    working_dir = str(_privoxy_root_dir())

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
            cwd=working_dir,
        )
    else:
        proc = subprocess.Popen(
            [exe, str(runtime_config_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            cwd=working_dir,
        )

    return proc.pid


def ensure_privoxy_instance(proxy_text: str) -> dict:
    with _POOL_LOCK:
        normalized = validate_source_proxy_text(proxy_text)
        proxy_key = _proxy_key(normalized)
        listen_host = _listen_host()

        state = _load_pool_state()
        instances = state.setdefault("instances", {})
        instance = instances.get(proxy_key)

        if instance:
            pid = instance.get("pid")
            port = int(instance.get("listen_port"))
            if _is_pid_alive(pid) and _is_port_open(listen_host, port, timeout_sec=0.5):
                return {
                    "proxy_key": proxy_key,
                    "listen_host": listen_host,
                    "listen_port": port,
                    "runtime_config": instance.get("runtime_config"),
                    "pid": pid,
                    "changed": False,
                }

        used_ports = set()
        for item in instances.values():
            try:
                used_ports.add(int(item.get("listen_port")))
            except Exception:
                continue

        port = instance.get("listen_port") if instance and instance.get("listen_port") else None
        if port:
            port = int(port)
            if _is_port_open(listen_host, port, timeout_sec=0.3):
                used_ports.discard(port)
        else:
            port = _find_free_port(
                start_port=_base_port(),
                max_instances=_max_instances(),
                host=listen_host,
                used_ports=used_ports,
            )

        runtime_config = _write_runtime_config(
            proxy_key=proxy_key,
            proxy_text=normalized,
            listen_host=listen_host,
            listen_port=port,
        )

        if instance:
            _stop_pid(instance.get("pid"))

        pid = _launch_privoxy(runtime_config)

        if not _wait_until_port_ready(listen_host, port, timeout_sec=15.0):
            raise RuntimeError(
                f"Privoxy instance не поднялся на {listen_host}:{port}"
            )

        instances[proxy_key] = {
            "proxy_text": normalized,
            "listen_host": listen_host,
            "listen_port": port,
            "pid": pid,
            "runtime_config": str(runtime_config),
            "updated_at": int(time.time()),
        }
        _save_pool_state(state)

        return {
            "proxy_key": proxy_key,
            "listen_host": listen_host,
            "listen_port": port,
            "runtime_config": str(runtime_config),
            "pid": pid,
            "changed": True,
        }


def prewarm_privoxy_instances(proxy_texts: list[str], limit: int = 5) -> list[dict]:
    results = []
    unique = []
    seen = set()

    for raw in proxy_texts:
        try:
            normalized = validate_source_proxy_text(raw)
        except Exception as exc:
            results.append({
                "proxy_text": raw,
                "ok": False,
                "error": str(exc),
            })
            continue

        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)

    for proxy_text in unique[:limit]:
        try:
            instance = ensure_privoxy_instance(proxy_text)
            results.append({
                "proxy_text": proxy_text,
                "ok": True,
                "listen_host": instance["listen_host"],
                "listen_port": instance["listen_port"],
                "runtime_config": instance["runtime_config"],
                "pid": instance["pid"],
                "changed": instance["changed"],
            })
        except Exception as exc:
            results.append({
                "proxy_text": proxy_text,
                "ok": False,
                "error": str(exc),
            })

    return results