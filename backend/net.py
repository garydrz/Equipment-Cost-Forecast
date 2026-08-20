"""Network egress guard + persistent JSON caches for FRED/FX responses.

Rules:
* Only hostnames whitelisted in `config/app_config.json` may be contacted.
* If `offline_mode` is enabled OR the host is not whitelisted, the request
  is short-circuited and a warning is logged; the caller receives `None`
  (which the callers translate into fallback/cache behaviour).
* Successful responses are persisted to `data/cache/*.json` so subsequent
  offline launches keep working.
"""
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

import httpx

from local_config import CACHE_DIR, CONFIG

logger = logging.getLogger("epc.net")

FRED_CACHE_FILE = CACHE_DIR / "fred_cache.json"
FX_CACHE_FILE = CACHE_DIR / "fx_cache.json"


# ---------- persistent JSON cache ------------------------------------------
def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_json(path: Path, data: Dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError as e:
        logger.warning("cache write failed for %s: %s", path, e)


# in-memory hot caches populated on startup, flushed on write
_fred_cache: Dict[str, Any] = _load_json(FRED_CACHE_FILE)
_fx_cache: Dict[str, Any] = _load_json(FX_CACHE_FILE)


def fred_cache_get(series_id: str) -> Optional[Dict[str, Any]]:
    entry = _fred_cache.get(series_id)
    if not entry:
        return None
    ttl = int(CONFIG["cache"].get("fred_ttl_seconds", 21600))
    if ttl > 0 and (time.time() - float(entry.get("ts", 0)) > ttl):
        return {"expired": True, **entry}
    return entry


def fred_cache_put(series_id: str, values: Dict[int, float]) -> None:
    _fred_cache[series_id] = {"ts": time.time(), "values": values}
    _save_json(FRED_CACHE_FILE, _fred_cache)


def fx_cache_get(key: str) -> Optional[float]:
    entry = _fx_cache.get(key)
    if not entry:
        return None
    ttl = int(CONFIG["cache"].get("fx_ttl_seconds", 604800))
    if ttl > 0 and (time.time() - float(entry.get("ts", 0)) > ttl):
        return None
    return float(entry["rate"])


def fx_cache_put(key: str, rate: float) -> None:
    _fx_cache[key] = {"ts": time.time(), "rate": float(rate)}
    _save_json(FX_CACHE_FILE, _fx_cache)


def cache_summary() -> Dict[str, Any]:
    return {
        "fred_series_cached": len(_fred_cache),
        "fred_series_ids": list(_fred_cache.keys()),
        "fx_pairs_cached": len(_fx_cache),
        "fred_cache_file": str(FRED_CACHE_FILE),
        "fx_cache_file": str(FX_CACHE_FILE),
    }


# ---------- whitelist HTTP -------------------------------------------------
def _is_allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    allowed = [h.lower() for h in CONFIG["network"].get("allowed_hosts", [])]
    return host in allowed


def is_offline() -> bool:
    return bool(CONFIG["network"].get("offline_mode", False))


async def safe_get(url: str, params: Optional[Dict[str, Any]] = None,
                   timeout: float = 15.0) -> Optional[Dict[str, Any]]:
    """GET a whitelisted URL and return parsed JSON, or None if blocked/offline/failed."""
    if is_offline():
        logger.info("[offline] blocked request to %s", url)
        return None
    if not _is_allowed(url):
        logger.warning("[whitelist] blocked non-whitelisted request to %s", url)
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(url, params=params)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning("HTTP fetch failed for %s: %s", url, e)
        return None
