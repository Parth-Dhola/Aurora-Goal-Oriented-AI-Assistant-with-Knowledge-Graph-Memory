"""
core/config.py — Persistent configuration & URL normalization for Aurora Android App
"""
import os
import json
from pathlib import Path

CONFIG_FILE = Path(os.path.expanduser("~")) / ".aurora_app_config.json"
DEFAULT_HOST = "http://localhost:8000"
SESSION_ID = "android-session"


def normalize_url(url: str) -> str:
    """Ensure URL has http:// or https:// prefix and no trailing slash."""
    url = url.strip()
    if not url:
        return DEFAULT_HOST
    if not (url.startswith("http://") or url.startswith("https://")):
        url = f"http://{url}"
    return url.rstrip("/")


def load_config() -> dict:
    try:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"server_url": DEFAULT_HOST, "theme": "aurora"}


def save_config(cfg: dict):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[Config] Save error: {e}")


_cfg = load_config()
SERVER_URL = normalize_url(_cfg.get("server_url", DEFAULT_HOST))
CURRENT_THEME = _cfg.get("theme", "aurora")


def set_server_url(url: str):
    global SERVER_URL
    SERVER_URL = normalize_url(url)
    save_config({"server_url": SERVER_URL, "theme": CURRENT_THEME})


def set_theme(theme_name: str):
    global CURRENT_THEME
    CURRENT_THEME = theme_name
    save_config({"server_url": SERVER_URL, "theme": CURRENT_THEME})


def get_api_base() -> str:
    return f"{SERVER_URL}/api"


def get_ws_base() -> str:
    ws_protocol = "wss" if SERVER_URL.startswith("https") else "ws"
    host = SERVER_URL.split("://")[-1]
    return f"{ws_protocol}://{host}/ws"
