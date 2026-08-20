"""Local application configuration loader.

Reads and lazily creates `config/app_config.json` inside the project root.
All defaults are baked in so first-launch works without any manual step.
"""
import json
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
CONFIG_FILE = CONFIG_DIR / "app_config.json"
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
BACKUP_DIR = DATA_DIR / "backups"
LOG_DIR = ROOT / "logs"
FRONTEND_BUILD_DIR = ROOT / "frontend" / "build"

DEFAULTS: Dict[str, Any] = {
    "database": {
        "path": "data/epc_estimator.db",
    },
    "server": {
        "host": "127.0.0.1",
        "port": 8000,
        "open_browser": True,
    },
    "network": {
        "offline_mode": False,
        "allowed_hosts": [
            "api.stlouisfed.org",
            "api.frankfurter.dev",
            "api.frankfurter.app",
        ],
    },
    "cache": {
        "fred_ttl_seconds": 21600,
        "fx_ttl_seconds": 604800,
    },
    "backup": {
        "keep_last": 20,
    },
    "logging": {
        "level": "INFO",
        "max_bytes": 2_000_000,
        "backup_count": 5,
    },
    "fred": {
        "api_key": "",
    },
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def ensure_dirs() -> None:
    for d in (CONFIG_DIR, DATA_DIR, CACHE_DIR, BACKUP_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_config() -> Dict[str, Any]:
    """Load config file, creating it with defaults if missing.

    An `EPC_FRED_API_KEY` (or legacy `FRED_API_KEY`) env var overrides the
    file value so users can keep secrets outside the repo when they wish.
    """
    ensure_dirs()
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps(DEFAULTS, indent=2), encoding="utf-8")
        cfg = dict(DEFAULTS)
    else:
        try:
            cfg = _deep_merge(DEFAULTS, json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            cfg = dict(DEFAULTS)

    # Env override for FRED key (backwards compat with prior .env)
    import os
    env_key = os.environ.get("EPC_FRED_API_KEY") or os.environ.get("FRED_API_KEY")
    if env_key:
        cfg.setdefault("fred", {})["api_key"] = env_key

    # Resolve database path relative to project root
    db_path = Path(cfg["database"]["path"])
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    cfg["database"]["_resolved_path"] = str(db_path)
    return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    ensure_dirs()
    # Never persist resolved/derived fields
    persist = {k: v for k, v in cfg.items() if not k.startswith("_")}
    if "database" in persist and isinstance(persist["database"], dict):
        persist["database"] = {k: v for k, v in persist["database"].items() if not k.startswith("_")}
    CONFIG_FILE.write_text(json.dumps(persist, indent=2), encoding="utf-8")


# Module-level singletons -----------------------------------------------------
CONFIG: Dict[str, Any] = load_config()


def refresh() -> Dict[str, Any]:
    global CONFIG
    CONFIG = load_config()
    return CONFIG
