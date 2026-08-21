import sqlite3
from pathlib import Path
DB_PATH = Path(__file__).resolve().parents[1] / "data" / "equipment_cost.db"

def connect():
    DB_PATH.parent.mkdir(exist_ok=True)
    con=sqlite3.connect(DB_PATH)
    con.row_factory=sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con

def init_db():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS historical_equipment(
          id TEXT PRIMARY KEY, category TEXT NOT NULL, subtype TEXT, size REAL NOT NULL,
          size_unit TEXT NOT NULL, weight_kg REAL, material TEXT NOT NULL,
          design_pressure_bar REAL, design_temperature_c REAL, power_kw REAL,
          year INTEGER NOT NULL, cost_original REAL NOT NULL, currency TEXT NOT NULL,
          vendor_country TEXT, install_country TEXT, notes TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS projects(
          id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
          output_currency TEXT NOT NULL, target_year INTEGER NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS equipment_rows(
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          tag TEXT, category TEXT NOT NULL, subtype TEXT, size REAL NOT NULL, size_unit TEXT NOT NULL,
          material TEXT NOT NULL, design_pressure_bar REAL, design_temperature_c REAL, power_kw REAL,
          quantity INTEGER NOT NULL, reference_ids TEXT, unit_expected_cost REAL, unit_low REAL,
          unit_high REAL, total_expected_cost REAL, total_sigma REAL, aace_class TEXT,
          references_used INTEGER, escalation_factor REAL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings(category TEXT PRIMARY KEY, scale_exponent REAL NOT NULL, steel_weight REAL NOT NULL, oil_weight REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS api_cache(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);
        """)
        from .estimation import CATEGORY_META
        for c,m in CATEGORY_META.items():
            con.execute("INSERT OR IGNORE INTO settings VALUES(?,?,?,?)",(c,m['default_n'],m['steel_w'],m['oil_w']))
