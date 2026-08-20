# EPC Equipment Parametric Cost Estimation

## Original problem statement
Single-user desktop-style web application for EPC equipment cost
estimation using parametric scaling of a historical repository.

## Current state
Fully local, self-contained web app (`weighted_similarity_v3`). Runs on
Windows/macOS/Linux with only Python + `requirements.txt` — no MongoDB,
Docker, Node.js at runtime, no cloud services.

## Architecture
```
/app
├── main.py                    Local launcher (verifies deps, boots uvicorn, opens browser)
├── README.md
├── config/app_config.json     Editable local config (auto-created on first run)
├── data/
│   ├── epc_estimator.db       SQLite database
│   ├── cache/                 fred_cache.json / fx_cache.json
│   └── backups/               DB snapshots
├── logs/                      Rotating startup.log + backend.log
├── backend/
│   ├── server.py              FastAPI + estimation engine
│   ├── db.py                  SQLite ↔ Motor-compatible wrapper
│   ├── local_config.py        Config loader
│   ├── net.py                 Whitelist HTTP + persistent JSON cache
│   ├── backup.py              DB backup/restore
│   ├── importexport.py        CSV/Excel helpers
│   ├── requirements.txt       10 Python packages, no DB drivers
│   └── tests/                 pytest suite
└── frontend/
    └── src/pages/SystemStatus.jsx   New "System Status" page
```

## What's been implemented

### 2026-02-XX — Full local self-contained migration
- **SQLite storage**: replaced MongoDB/Motor with a two-column JSON-blob
  table per collection + a Motor-compatible async wrapper
  (`backend/db.py`). All existing route handlers unchanged.
- **Config**: `config/app_config.json` auto-created with defaults.
- **Network policy**: strict egress whitelist (FRED + Frankfurter only)
  in `backend/net.py`. Non-whitelisted requests are blocked and logged.
- **Offline mode**: toggle in System Status; blocks every outbound call
  and the app keeps working with local caches.
- **Persistent caches**: `data/cache/fred_cache.json`,
  `data/cache/fx_cache.json` (TTL configurable).
- **Backups**: create/restore/delete DB snapshots via
  `/api/system/backups*`. Restores automatically snapshot the current DB
  first.
- **Import/Export**: CSV import + CSV/Excel export for historical
  equipment; CSV/Excel export for whole projects with totals.
- **System Status page**: DB path/size, offline toggle, whitelist,
  backups, imports, cache status, FRED status, FX status.
- **Rotating file logs**: `logs/startup.log` + `logs/backend.log`.
- **Local launcher**: `python main.py` verifies deps, creates
  dirs/DB, starts uvicorn on port 8000, serves `frontend/build/`
  statically, opens browser.
- **Frontend served in-process**: React SPA served by FastAPI when
  `frontend/build/` exists; SPA client-side routing via catch-all.
- **API relative fallback**: frontend uses `/api` when
  `REACT_APP_BACKEND_URL` is empty (for local build).

### Prior work (`weighted_similarity_v3` — done before this session)
- Strict category+subtype dropdowns, IQR outlier removal, multivariate
  pump scaling (Q/H/P), burner category, project-level variance
  aggregation, human-readable calculation report.

## Test results (this session)
- 49/50 backend pytest cases pass in serial mode. The single failing
  case is a pre-existing assertion string mismatch
  (`"fewer than four"` vs actual `"fewer than 4"` in the warning).
- Backend endpoints smoke-tested via curl (status, backups, offline
  toggle, CSV/XLSX export, estimate, projects, meta).
- Frontend smoke-tested: Projects list and System Status render correctly.
- `python main.py` boots the backend on 8000 and creates all folders.

## Backlog (P1 → P3)
- **P1**: Branded PDF export of project estimates.
- **P2**: Excel bulk import for historical equipment (CSV already done).
- **P2**: Config-version stamp: flag rows recomputed with an older admin
  config than the current one.
- **P3**: Extract estimation engine from `server.py` into a
  `services/` module (>1600 lines currently).
- **Nice-to-have**: pack a Windows `.exe` via PyInstaller so users can
  double-click to launch.

## Test credentials
None. Single-user, no auth.
