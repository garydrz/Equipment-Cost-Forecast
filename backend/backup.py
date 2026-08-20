"""Local backup / restore of the SQLite database file.

Backups are stored under `data/backups/` with a timestamped filename.
The active DB path is read from `local_config.CONFIG`.
"""
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from local_config import BACKUP_DIR, CONFIG


def _db_path() -> Path:
    return Path(CONFIG["database"]["_resolved_path"])


def list_backups() -> List[Dict[str, Any]]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    out: List[Dict[str, Any]] = []
    for f in sorted(BACKUP_DIR.glob("*.db"), reverse=True):
        st = f.stat()
        out.append({
            "filename": f.name,
            "size_bytes": st.st_size,
            "created_at": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        })
    return out


def create_backup() -> Dict[str, Any]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    src = _db_path()
    if not src.exists():
        raise FileNotFoundError(f"database file does not exist: {src}")
    ts = time.strftime("%Y%m%d-%H%M%S")
    dst = BACKUP_DIR / f"epc_backup_{ts}.db"
    shutil.copy2(src, dst)
    _prune()
    return {"filename": dst.name, "size_bytes": dst.stat().st_size,
            "created_at": datetime.now().isoformat(timespec="seconds")}


def restore_backup(filename: str) -> Dict[str, Any]:
    src = BACKUP_DIR / filename
    if not src.exists() or ".." in filename or "/" in filename or "\\" in filename:
        raise FileNotFoundError(f"backup not found: {filename}")
    dst = _db_path()
    # Safety: back up the current DB before overwriting
    if dst.exists():
        ts = time.strftime("%Y%m%d-%H%M%S")
        pre = BACKUP_DIR / f"epc_pre_restore_{ts}.db"
        shutil.copy2(dst, pre)
    shutil.copy2(src, dst)
    return {"restored_from": filename, "target": str(dst)}


def delete_backup(filename: str) -> None:
    src = BACKUP_DIR / filename
    if ".." in filename or "/" in filename or "\\" in filename:
        raise FileNotFoundError("invalid filename")
    if src.exists():
        src.unlink()


def _prune() -> None:
    keep = int(CONFIG["backup"].get("keep_last", 20))
    if keep <= 0:
        return
    files = sorted(BACKUP_DIR.glob("epc_backup_*.db"), reverse=True)
    for f in files[keep:]:
        try:
            f.unlink()
        except OSError:
            pass
