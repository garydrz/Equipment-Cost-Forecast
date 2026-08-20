# EPC Equipment Parametric Cost Estimator

Fully local, self-contained web application for parametric cost estimation
of industrial (EPC) equipment. All data stays on your PC — no database
server, no cloud service, no account required.

## Requirements

Only two things:

- **Python 3.10+** (Windows, macOS, Linux)
- The libraries listed in `requirements.txt`

No MongoDB / PostgreSQL / Docker / Node.js at runtime. The frontend is
shipped pre-built and served by the same FastAPI process.

## Quick start

```bash
git clone <this repo>
cd <this repo>
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

`python main.py`:

1. verifies the Python version and required libraries,
2. creates `data/`, `data/cache/`, `data/backups/`, `logs/`, `config/`
   if missing,
3. creates the SQLite database (`data/epc_estimator.db`) on first run
   and seeds a small demo dataset,
4. starts the backend + serves the built frontend on
   [http://localhost:8000](http://localhost:8000),
5. opens your default browser at that URL.

Stop with `Ctrl+C`.

## Configuration

`config/app_config.json` is created automatically on first launch. Edit
freely. You can also set the FRED key via the environment variable
`EPC_FRED_API_KEY` if you prefer to keep secrets outside the repo.

## Data location

Everything is stored under the project folder:

```
data/
  epc_estimator.db         SQLite database
  cache/                   FRED + FX response caches
  backups/                 On-demand DB snapshots
logs/                      startup.log + rotating backend.log
config/app_config.json     Local configuration
```

Nothing is written or transmitted anywhere else.

## Network policy

Only two hosts may ever be contacted (enforced by a runtime whitelist):

- `api.stlouisfed.org` — FRED indices
- `api.frankfurter.dev` / `api.frankfurter.app` — FX rates

Turn **Offline mode** on from *System Status* to block every outbound
call — the app keeps working using the local caches and fallback values.

## Import / Export / Backup

From the **System Status** page you can:

- Export the historical repository as CSV or Excel.
- Import equipment CSV files.
- Export any project as CSV or Excel (rows + totals).
- Create, restore, and delete database snapshots.

## Development

Backend hot-reload:

```bash
cd backend
uvicorn server:app --reload --port 8001
```

Frontend dev server + prod build:

```bash
cd frontend
yarn install
yarn start           # dev
yarn build           # produces frontend/build served by main.py
```

## Tests

```bash
cd backend
pytest tests/
```
