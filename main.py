"""EPC Equipment Parametric Cost Estimation — local launcher.

Single entry point for end users: run `python main.py` and everything
required to use the estimator on `http://localhost:8000` is prepared:

* required directories (`data/`, `data/cache/`, `data/backups/`, `logs/`,
  `config/`) are created if missing;
* the local SQLite database is created on first run;
* uvicorn boots the FastAPI backend on the port defined in
  `config/app_config.json` (default 8000) and serves the pre-built React
  frontend from the same origin (see `frontend/build/`);
* a browser tab is opened at the app URL.

No third-party server, database or cloud service is required. The only
external HTTP endpoints that may be contacted are FRED and Frankfurter
(strictly enforced by a whitelist inside the backend).
"""
import json
import logging
import os
import sys
import threading
import time
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "config" / "app_config.json"

REQUIRED_DIRS = [
    ROOT / "config",
    ROOT / "data",
    ROOT / "data" / "cache",
    ROOT / "data" / "backups",
    ROOT / "logs",
]


def _ensure_dirs() -> None:
    for d in REQUIRED_DIRS:
        d.mkdir(parents=True, exist_ok=True)


def _startup_logger() -> logging.Logger:
    handler = RotatingFileHandler(ROOT / "logs" / "startup.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    log = logging.getLogger("epc.startup")
    log.setLevel(logging.INFO)
    if not any(isinstance(h, RotatingFileHandler) for h in log.handlers):
        log.addHandler(handler)
    # Mirror on stdout so the terminal shows progress
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler) for h in log.handlers):
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(sh)
    log.propagate = False
    return log


def _load_config() -> dict:
    if not CONFIG_FILE.exists():
        # local_config.load_config() writes defaults, we just call it
        sys.path.insert(0, str(ROOT / "backend"))
        from local_config import load_config
        return load_config()
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _check_python() -> None:
    if sys.version_info < (3, 10):
        print("ERROR: Python 3.10 or newer is required. You are on {}.{}.{}".format(*sys.version_info[:3]))
        sys.exit(1)


def _check_dependencies() -> None:
    missing = []
    for mod in ("fastapi", "uvicorn", "pydantic", "httpx", "pandas", "openpyxl"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        print("ERROR: missing Python packages: " + ", ".join(missing))
        print("Install them with:  pip install -r requirements.txt")
        sys.exit(1)


def _open_browser_when_ready(url: str, delay: float = 1.6) -> None:
    def _run():
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


def main() -> None:
    _check_python()
    _ensure_dirs()
    _check_dependencies()

    log = _startup_logger()
    log.info("EPC Estimator — local launcher")

    # Make the backend importable
    sys.path.insert(0, str(ROOT / "backend"))
    cfg = _load_config()
    host = cfg.get("server", {}).get("host", "127.0.0.1")
    port = int(cfg.get("server", {}).get("port", 8000))
    open_browser = bool(cfg.get("server", {}).get("open_browser", True))
    build_dir = ROOT / "frontend" / "build"

    log.info("Data directory: %s", ROOT / "data")
    log.info("Database file:  %s", cfg.get("database", {}).get("path", "data/epc_estimator.db"))
    log.info("Config file:    %s", CONFIG_FILE)
    log.info("Offline mode:   %s", cfg.get("network", {}).get("offline_mode", False))
    if not build_dir.exists():
        log.warning(
            "Frontend build folder not found at %s. "
            "The API will still work, but you'll need to build the SPA "
            "(cd frontend && yarn install && yarn build) to use the UI locally.",
            build_dir,
        )

    url = f"http://localhost:{port}"
    log.info("Starting server on %s", url)
    if open_browser:
        _open_browser_when_ready(url)

    import uvicorn
    # log_config=None keeps uvicorn from clobbering our rotating file handlers
    uvicorn.run("server:app", host=host, port=port, log_level="info", reload=False)


if __name__ == "__main__":
    main()
