"""
EPC Equipment Parametric Cost Estimation - Backend
FastAPI + MongoDB
"""
from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal
import uuid
from datetime import datetime, timezone
import math
import httpx
import asyncio

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

FRED_API_KEY = os.environ.get('FRED_API_KEY', '')

app = FastAPI()
api_router = APIRouter(prefix="/api")

# -------------------- CATEGORY META --------------------
# Categories with default AACE exponents and default steel/oil weights.
CATEGORIES = [
    "column", "reactor", "heat_exchanger", "storage_tank",
    "pump", "compressor", "valve", "instrumentation", "other",
]

CATEGORY_META = {
    "column":          {"label": "Distillation Column",  "unit": "m3",       "power_field": False, "default_n": 0.65, "steel_w": 0.80, "oil_w": 0.20},
    "reactor":         {"label": "Reactor",              "unit": "m3",       "power_field": False, "default_n": 0.65, "steel_w": 0.80, "oil_w": 0.20},
    "heat_exchanger":  {"label": "Heat Exchanger",       "unit": "m2",       "power_field": False, "default_n": 0.65, "steel_w": 0.80, "oil_w": 0.20},
    "storage_tank":    {"label": "Storage Tank",         "unit": "m3",       "power_field": False, "default_n": 0.62, "steel_w": 0.80, "oil_w": 0.20},
    "pump":            {"label": "Pump",                 "unit": "m3/h",     "power_field": True,  "default_n": 0.60, "steel_w": 0.40, "oil_w": 0.60},
    "compressor":      {"label": "Compressor",           "unit": "m3/h",     "power_field": True,  "default_n": 0.75, "steel_w": 0.40, "oil_w": 0.60},
    "valve":           {"label": "Valve",                "unit": "DN(mm)",   "power_field": False, "default_n": 0.40, "steel_w": 0.60, "oil_w": 0.40},
    "instrumentation": {"label": "Instrumentation",      "unit": "unit",     "power_field": False, "default_n": 0.30, "steel_w": 0.60, "oil_w": 0.40},
    "other":           {"label": "Other",                "unit": "unit",     "power_field": False, "default_n": 0.60, "steel_w": 0.70, "oil_w": 0.30},
}

MATERIALS = ["carbon_steel", "stainless_steel_304", "stainless_steel_316", "duplex", "alloy", "other"]

# -------------------- MODELS --------------------
class HistoricalEquipment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    category: str
    subtype: Optional[str] = None
    size: float
    size_unit: str
    weight_kg: Optional[float] = None
    material: str
    design_pressure_bar: Optional[float] = None
    design_temperature_c: Optional[float] = None
    power_kw: Optional[float] = None
    year: int
    cost_original: float
    currency: Literal["EUR", "USD"]
    vendor_country: Optional[str] = None
    install_country: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class HistoricalEquipmentCreate(BaseModel):
    category: str
    subtype: Optional[str] = None
    size: float
    size_unit: str
    weight_kg: Optional[float] = None
    material: str
    design_pressure_bar: Optional[float] = None
    design_temperature_c: Optional[float] = None
    power_kw: Optional[float] = None
    year: int
    cost_original: float
    currency: Literal["EUR", "USD"]
    vendor_country: Optional[str] = None
    install_country: Optional[str] = None
    notes: Optional[str] = None

class Project(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: Optional[str] = None
    output_currency: Literal["EUR", "USD"] = "EUR"
    target_year: int = Field(default_factory=lambda: datetime.now(timezone.utc).year)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    output_currency: Literal["EUR", "USD"] = "EUR"
    target_year: Optional[int] = None

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    output_currency: Optional[Literal["EUR", "USD"]] = None
    target_year: Optional[int] = None

class EquipmentRow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    tag: Optional[str] = None
    category: str
    subtype: Optional[str] = None
    size: float
    size_unit: str
    material: str
    design_pressure_bar: Optional[float] = None
    design_temperature_c: Optional[float] = None
    power_kw: Optional[float] = None
    quantity: int = 1
    reference_ids: Optional[List[str]] = None  # optional manual reference historical equipment ids
    # cached results (recomputed each save)
    unit_expected_cost: float = 0.0
    unit_low: float = 0.0
    unit_high: float = 0.0
    total_expected_cost: float = 0.0
    total_sigma: float = 0.0
    aace_class: str = "Class 5"
    references_used: int = 0
    escalation_factor: float = 1.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class EquipmentRowCreate(BaseModel):
    tag: Optional[str] = None
    category: str
    subtype: Optional[str] = None
    size: float
    size_unit: str
    material: str
    design_pressure_bar: Optional[float] = None
    design_temperature_c: Optional[float] = None
    power_kw: Optional[float] = None
    quantity: int = 1
    reference_ids: Optional[List[str]] = None

class ScaleExponent(BaseModel):
    category: str
    n: float

class EscalationWeight(BaseModel):
    category: str
    steel_weight: float
    oil_weight: float

# -------------------- HELPERS: config --------------------
async def get_scale_exponent(category: str) -> float:
    doc = await db.scale_exponents.find_one({"category": category})
    if doc:
        return float(doc["n"])
    return CATEGORY_META.get(category, {}).get("default_n", 0.6)

async def get_escalation_weights(category: str):
    doc = await db.escalation_weights.find_one({"category": category})
    if doc:
        return float(doc["steel_weight"]), float(doc["oil_weight"])
    meta = CATEGORY_META.get(category, CATEGORY_META["other"])
    return float(meta["steel_w"]), float(meta["oil_w"])

# -------------------- HELPERS: external indices --------------------
# Fallback annual index values (indexed 100 = 2015), used if FRED unavailable
FALLBACK_STEEL = {
    2005: 88, 2006: 96, 2007: 106, 2008: 128, 2009: 90, 2010: 108,
    2011: 128, 2012: 118, 2013: 112, 2014: 111, 2015: 100, 2016: 96,
    2017: 108, 2018: 128, 2019: 118, 2020: 114, 2021: 190, 2022: 220,
    2023: 178, 2024: 172, 2025: 176, 2026: 180,
}
FALLBACK_OIL = {  # Brent avg USD/bbl
    2005: 54, 2006: 65, 2007: 72, 2008: 97, 2009: 62, 2010: 80,
    2011: 111, 2012: 112, 2013: 109, 2014: 99, 2015: 52, 2016: 44,
    2017: 54, 2018: 71, 2019: 64, 2020: 42, 2021: 71, 2022: 100,
    2023: 82, 2024: 80, 2025: 78, 2026: 78,
}

async def fetch_fred_annual(series_id: str) -> dict:
    """Fetch annual (frequency=a, avg) values from FRED. Returns dict year -> value."""
    if not FRED_API_KEY:
        return {}
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "frequency": "a",
        "aggregation_method": "avg",
        "observation_start": "2000-01-01",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, params=params)
            r.raise_for_status()
            data = r.json()
        out = {}
        for obs in data.get("observations", []):
            try:
                y = int(obs["date"][:4])
                v = float(obs["value"])
                out[y] = v
            except (ValueError, KeyError):
                continue
        return out
    except Exception as e:
        logging.warning(f"FRED fetch failed for {series_id}: {e}")
        return {}

# Cache in-process
_indices_cache = {"steel": None, "oil": None, "ts": 0.0}
_indices_lock = asyncio.Lock()

async def get_indices():
    """Returns (steel_by_year, oil_by_year). Uses in-memory cache 6h."""
    now = datetime.now(timezone.utc).timestamp()
    async with _indices_lock:
        if _indices_cache["steel"] and (now - _indices_cache["ts"] < 6 * 3600):
            return _indices_cache["steel"], _indices_cache["oil"]
        steel = await fetch_fred_annual("WPU101706")  # PPI Iron and Steel
        oil = await fetch_fred_annual("DCOILBRENTEU")
        if not steel:
            steel = FALLBACK_STEEL
        if not oil:
            oil = FALLBACK_OIL
        _indices_cache["steel"] = steel
        _indices_cache["oil"] = oil
        _indices_cache["ts"] = now
        return steel, oil

def _nearest_year_value(series: dict, year: int) -> float:
    if year in series:
        return series[year]
    years = sorted(series.keys())
    if not years:
        return 100.0
    # clamp
    if year < years[0]:
        return series[years[0]]
    if year > years[-1]:
        return series[years[-1]]
    # interpolate
    for i, y in enumerate(years):
        if y >= year:
            prev_y = years[i - 1] if i > 0 else y
            if prev_y == y:
                return series[y]
            frac = (year - prev_y) / (y - prev_y)
            return series[prev_y] + frac * (series[y] - series[prev_y])
    return series[years[-1]]

async def compute_escalation(from_year: int, to_year: int, steel_w: float, oil_w: float):
    steel, oil = await get_indices()
    s_from = _nearest_year_value(steel, from_year)
    s_to = _nearest_year_value(steel, to_year)
    o_from = _nearest_year_value(oil, from_year)
    o_to = _nearest_year_value(oil, to_year)
    d_steel = (s_to - s_from) / s_from if s_from else 0.0
    d_oil = (o_to - o_from) / o_from if o_from else 0.0
    return 1.0 + steel_w * d_steel + oil_w * d_oil

# -------------------- FX --------------------
_fx_cache = {}

async def fx_rate(base: str, target: str, date: Optional[str] = None) -> float:
    """Get EUR/USD or USD/EUR from Frankfurter (free). date=YYYY-MM-DD or 'latest'."""
    if base == target:
        return 1.0
    date_key = date or "latest"
    cache_key = f"{base}-{target}-{date_key}"
    if cache_key in _fx_cache:
        return _fx_cache[cache_key]
    url = f"https://api.frankfurter.dev/v1/{date_key}"
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(url, params={"base": base, "symbols": target})
            r.raise_for_status()
            data = r.json()
        rate = float(data["rates"][target])
    except Exception as e:
        logging.warning(f"FX fetch failed {base}->{target} {date_key}: {e}")
        # fallback approx
        rate = 1.08 if base == "EUR" and target == "USD" else 0.92
    _fx_cache[cache_key] = rate
    return rate

async def convert_currency(amount: float, from_ccy: str, to_ccy: str, year: Optional[int] = None) -> float:
    if from_ccy == to_ccy:
        return amount
    date = f"{year}-06-15" if year else None
    r = await fx_rate(from_ccy, to_ccy, date)
    return amount * r

# -------------------- ESTIMATION LOGIC --------------------
AACE_DEFAULTS = {
    # class -> (low_pct, high_pct)
    "Class 5": (-0.35, 0.65),
    "Class 4": (-0.22, 0.35),
    "Class 3": (-0.15, 0.20),
}

def classify_aace(n_refs: int) -> str:
    if n_refs >= 5:
        return "Class 3"
    if n_refs >= 3:
        return "Class 4"
    return "Class 5"

def project_aace(row_classes: list) -> str:
    """Worst class dominates the project class."""
    order = {"Class 3": 3, "Class 4": 4, "Class 5": 5}
    if not row_classes:
        return "Class 5"
    return max(row_classes, key=lambda c: order.get(c, 5))

async def find_candidates(category: str, subtype: Optional[str], material: Optional[str] = None):
    q = {"category": category}
    docs = await db.equipment_historical.find(q, {"_id": 0}).to_list(1000)
    # prefer subtype match
    if subtype:
        matched = [d for d in docs if (d.get("subtype") or "").lower() == subtype.lower()]
        if matched:
            docs = matched
    return docs

async def estimate_single(
    category: str,
    size: float,
    material: str,
    target_year: int,
    output_currency: str,
    subtype: Optional[str] = None,
    power_kw: Optional[float] = None,
    reference_ids: Optional[List[str]] = None,
):
    """Return dict with expected, low, high, sigma, references_used, aace_class, escalation, per-unit values."""
    n = await get_scale_exponent(category)
    steel_w, oil_w = await get_escalation_weights(category)

    # gather references
    if reference_ids:
        refs = await db.equipment_historical.find({"id": {"$in": reference_ids}}, {"_id": 0}).to_list(1000)
    else:
        refs = await find_candidates(category, subtype)

    # For pump/compressor, prefer scaling on power_kw if provided
    use_power_scaling = CATEGORY_META.get(category, {}).get("power_field") and power_kw
    scaled_costs = []  # in output_currency
    unit_norms = []  # normalized cost/size^n (for sigma) in EUR common

    for r in refs:
        try:
            size_r = float(r.get("power_kw") if use_power_scaling and r.get("power_kw") else r["size"])
            if size_r <= 0:
                continue
            target_size = power_kw if use_power_scaling else size
            if target_size <= 0:
                continue
            # scaling
            scaled_cost_orig = float(r["cost_original"]) * (target_size / size_r) ** n
            # escalation
            esc = await compute_escalation(int(r["year"]), target_year, steel_w, oil_w)
            escalated = scaled_cost_orig * esc
            # currency: convert historical currency at year, then to output currency
            in_common = await convert_currency(escalated, r["currency"], output_currency, target_year)
            scaled_costs.append(in_common)
            # normalized cost per capacity (for dispersion at same year & currency)
            unit_norms.append(in_common / (target_size ** n))
        except Exception as e:
            logging.warning(f"skip ref {r.get('id')}: {e}")
            continue

    n_refs = len(scaled_costs)
    aace = classify_aace(n_refs)

    if n_refs == 0:
        # no reference - can't estimate meaningfully; return zeros with warning
        return {
            "expected": 0.0, "low": 0.0, "high": 0.0, "sigma": 0.0,
            "references_used": 0, "aace_class": aace, "escalation_factor": 0.0,
            "no_reference": True,
        }

    expected = sum(scaled_costs) / n_refs

    # sigma & range
    if n_refs >= 3:
        mean = expected
        variance = sum((c - mean) ** 2 for c in scaled_costs) / (n_refs - 1) if n_refs > 1 else 0
        sigma = math.sqrt(variance)
        # confidence interval based on class defaults, but also compare with observed dispersion
        low_pct, high_pct = AACE_DEFAULTS[aace]
        # use max of observed 1-sigma vs default pct band
        low = min(expected * (1 + low_pct), expected - sigma)
        high = max(expected * (1 + high_pct), expected + sigma)
    else:
        low_pct, high_pct = AACE_DEFAULTS[aace]
        low = expected * (1 + low_pct)
        high = expected * (1 + high_pct)
        sigma = (high - low) / 2 / 1.645  # approx 90% CI back to sigma

    # last escalation for display
    avg_esc = 0.0
    if refs:
        try:
            avg_esc = sum([await compute_escalation(int(r["year"]), target_year, steel_w, oil_w) for r in refs]) / len(refs)
        except Exception:
            avg_esc = 0.0

    return {
        "expected": round(expected, 2),
        "low": round(low, 2),
        "high": round(high, 2),
        "sigma": round(sigma, 2),
        "references_used": n_refs,
        "aace_class": aace,
        "escalation_factor": round(avg_esc, 4),
        "no_reference": False,
    }

# -------------------- ROUTES: meta --------------------
@api_router.get("/")
async def root():
    return {"status": "ok", "service": "EPC Cost Estimator"}

@api_router.get("/meta/categories")
async def categories():
    return {"categories": CATEGORIES, "meta": CATEGORY_META, "materials": MATERIALS}

# -------------------- ROUTES: historical equipment --------------------
@api_router.get("/equipment", response_model=List[HistoricalEquipment])
async def list_equipment(category: Optional[str] = None, q: Optional[str] = None):
    query = {}
    if category:
        query["category"] = category
    docs = await db.equipment_historical.find(query, {"_id": 0}).to_list(2000)
    if q:
        ql = q.lower()
        docs = [d for d in docs if ql in (d.get("subtype") or "").lower() or ql in (d.get("notes") or "").lower() or ql in (d.get("vendor_country") or "").lower()]
    return docs

@api_router.post("/equipment", response_model=HistoricalEquipment)
async def create_equipment(body: HistoricalEquipmentCreate):
    obj = HistoricalEquipment(**body.model_dump())
    doc = obj.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    await db.equipment_historical.insert_one(doc)
    return obj

@api_router.put("/equipment/{eq_id}", response_model=HistoricalEquipment)
async def update_equipment(eq_id: str, body: HistoricalEquipmentCreate):
    existing = await db.equipment_historical.find_one({"id": eq_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Not found")
    updated = {**existing, **body.model_dump()}
    await db.equipment_historical.update_one({"id": eq_id}, {"$set": body.model_dump()})
    return HistoricalEquipment(**updated)

@api_router.delete("/equipment/{eq_id}")
async def delete_equipment(eq_id: str):
    r = await db.equipment_historical.delete_one({"id": eq_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"deleted": True}

# -------------------- ROUTES: projects --------------------
@api_router.get("/projects", response_model=List[Project])
async def list_projects():
    docs = await db.projects.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    for d in docs:
        if isinstance(d.get("created_at"), str):
            d["created_at"] = datetime.fromisoformat(d["created_at"])
    return docs

@api_router.post("/projects", response_model=Project)
async def create_project(body: ProjectCreate):
    data = body.model_dump()
    if not data.get("target_year"):
        data["target_year"] = datetime.now(timezone.utc).year
    obj = Project(**data)
    doc = obj.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    await db.projects.insert_one(doc)
    return obj

@api_router.get("/projects/{pid}")
async def get_project(pid: str):
    p = await db.projects.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Project not found")
    rows = await db.equipment_rows.find({"project_id": pid}, {"_id": 0}).sort("created_at", 1).to_list(2000)
    # totals
    total_expected = sum(r.get("total_expected_cost", 0.0) for r in rows)
    total_sigma_sq = sum(r.get("total_sigma", 0.0) ** 2 for r in rows)
    total_sigma = math.sqrt(total_sigma_sq)
    # project range: use worst-case per-row band as project band (sum in quadrature of half-ranges)
    half_ranges = []
    for r in rows:
        hr = max(abs(r.get("total_expected_cost", 0.0) - r.get("unit_low", 0.0) * r.get("quantity", 1)),
                 abs(r.get("unit_high", 0.0) * r.get("quantity", 1) - r.get("total_expected_cost", 0.0)))
        half_ranges.append(hr)
    proj_half = math.sqrt(sum(h ** 2 for h in half_ranges))
    proj_low = total_expected - proj_half
    proj_high = total_expected + proj_half
    project_class = project_aace([r.get("aace_class", "Class 5") for r in rows])
    if isinstance(p.get("created_at"), str):
        p["created_at"] = datetime.fromisoformat(p["created_at"])
    return {
        "project": p,
        "rows": rows,
        "totals": {
            "expected": round(total_expected, 2),
            "low": round(proj_low, 2),
            "high": round(proj_high, 2),
            "sigma": round(total_sigma, 2),
            "aace_class": project_class,
        },
    }

@api_router.put("/projects/{pid}", response_model=Project)
async def update_project(pid: str, body: ProjectUpdate):
    existing = await db.projects.find_one({"id": pid}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Not found")
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    await db.projects.update_one({"id": pid}, {"$set": upd})
    merged = {**existing, **upd}
    if isinstance(merged.get("created_at"), str):
        merged["created_at"] = datetime.fromisoformat(merged["created_at"])
    return Project(**merged)

@api_router.delete("/projects/{pid}")
async def delete_project(pid: str):
    await db.equipment_rows.delete_many({"project_id": pid})
    r = await db.projects.delete_one({"id": pid})
    if r.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"deleted": True}

# -------------------- ROUTES: equipment rows --------------------
async def _compute_row_estimate(project_doc, row_data):
    est = await estimate_single(
        category=row_data["category"],
        size=float(row_data["size"]),
        material=row_data["material"],
        target_year=int(project_doc["target_year"]),
        output_currency=project_doc["output_currency"],
        subtype=row_data.get("subtype"),
        power_kw=row_data.get("power_kw"),
        reference_ids=row_data.get("reference_ids"),
    )
    qty = int(row_data.get("quantity", 1) or 1)
    return {
        "unit_expected_cost": est["expected"],
        "unit_low": est["low"],
        "unit_high": est["high"],
        "total_expected_cost": round(est["expected"] * qty, 2),
        "total_sigma": round(est["sigma"] * math.sqrt(qty), 2),  # independent per-unit -> sqrt(qty)
        "aace_class": est["aace_class"],
        "references_used": est["references_used"],
        "escalation_factor": est["escalation_factor"],
    }

@api_router.post("/projects/{pid}/rows", response_model=EquipmentRow)
async def add_row(pid: str, body: EquipmentRowCreate):
    p = await db.projects.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Project not found")
    data = body.model_dump()
    est = await _compute_row_estimate(p, data)
    row = EquipmentRow(project_id=pid, **data, **est)
    doc = row.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    await db.equipment_rows.insert_one(doc)
    return row

@api_router.put("/projects/{pid}/rows/{rid}", response_model=EquipmentRow)
async def update_row(pid: str, rid: str, body: EquipmentRowCreate):
    p = await db.projects.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Project not found")
    existing = await db.equipment_rows.find_one({"id": rid, "project_id": pid}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Row not found")
    data = body.model_dump()
    est = await _compute_row_estimate(p, data)
    upd = {**data, **est}
    await db.equipment_rows.update_one({"id": rid}, {"$set": upd})
    merged = {**existing, **upd}
    if isinstance(merged.get("created_at"), str):
        merged["created_at"] = datetime.fromisoformat(merged["created_at"])
    return EquipmentRow(**merged)

@api_router.delete("/projects/{pid}/rows/{rid}")
async def delete_row(pid: str, rid: str):
    r = await db.equipment_rows.delete_one({"id": rid, "project_id": pid})
    if r.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"deleted": True}

@api_router.post("/projects/{pid}/recompute")
async def recompute_project(pid: str):
    """Re-estimate all rows (useful after changing admin params)."""
    p = await db.projects.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Project not found")
    rows = await db.equipment_rows.find({"project_id": pid}, {"_id": 0}).to_list(2000)
    for r in rows:
        est = await _compute_row_estimate(p, r)
        await db.equipment_rows.update_one({"id": r["id"]}, {"$set": est})
    return {"ok": True, "updated": len(rows)}

# -------------------- ROUTES: estimate preview --------------------
class EstimatePreview(BaseModel):
    category: str
    subtype: Optional[str] = None
    size: float
    material: str
    power_kw: Optional[float] = None
    target_year: int
    output_currency: Literal["EUR", "USD"] = "EUR"
    reference_ids: Optional[List[str]] = None
    quantity: int = 1

@api_router.post("/estimate")
async def estimate_preview(body: EstimatePreview):
    est = await estimate_single(
        category=body.category,
        size=body.size,
        material=body.material,
        target_year=body.target_year,
        output_currency=body.output_currency,
        subtype=body.subtype,
        power_kw=body.power_kw,
        reference_ids=body.reference_ids,
    )
    q = max(body.quantity, 1)
    return {
        **est,
        "quantity": q,
        "total_expected": round(est["expected"] * q, 2),
        "total_low": round(est["low"] * q, 2),
        "total_high": round(est["high"] * q, 2),
    }

# -------------------- ROUTES: admin params --------------------
@api_router.get("/admin/scale-exponents")
async def get_scale_exponents():
    out = []
    for cat in CATEGORIES:
        doc = await db.scale_exponents.find_one({"category": cat}, {"_id": 0})
        n = doc["n"] if doc else CATEGORY_META[cat]["default_n"]
        out.append({"category": cat, "label": CATEGORY_META[cat]["label"], "n": n, "default_n": CATEGORY_META[cat]["default_n"]})
    return out

@api_router.put("/admin/scale-exponents")
async def set_scale_exponents(body: List[ScaleExponent]):
    for item in body:
        await db.scale_exponents.update_one(
            {"category": item.category},
            {"$set": {"n": item.n}},
            upsert=True,
        )
    return {"ok": True}

@api_router.get("/admin/escalation-weights")
async def get_esc_weights():
    out = []
    for cat in CATEGORIES:
        doc = await db.escalation_weights.find_one({"category": cat}, {"_id": 0})
        if doc:
            sw, ow = doc["steel_weight"], doc["oil_weight"]
        else:
            sw, ow = CATEGORY_META[cat]["steel_w"], CATEGORY_META[cat]["oil_w"]
        out.append({
            "category": cat, "label": CATEGORY_META[cat]["label"],
            "steel_weight": sw, "oil_weight": ow,
            "default_steel": CATEGORY_META[cat]["steel_w"], "default_oil": CATEGORY_META[cat]["oil_w"],
        })
    return out

@api_router.put("/admin/escalation-weights")
async def set_esc_weights(body: List[EscalationWeight]):
    for item in body:
        await db.escalation_weights.update_one(
            {"category": item.category},
            {"$set": {"steel_weight": item.steel_weight, "oil_weight": item.oil_weight}},
            upsert=True,
        )
    return {"ok": True}

# -------------------- ROUTES: indices/fx debug --------------------
@api_router.get("/indices")
async def indices_endpoint():
    steel, oil = await get_indices()
    return {
        "steel_by_year": {int(k): v for k, v in steel.items()},
        "oil_by_year": {int(k): v for k, v in oil.items()},
        "source": "FRED" if FRED_API_KEY else "fallback",
    }

# -------------------- STARTUP: seed --------------------
DUMMY_HISTORICAL = [
    # (category, subtype, size, unit, weight_kg, material, P, T, power, year, cost, ccy, notes)
    ("column",         "Distillation tray",    45,   "m3",   32000, "carbon_steel",       12,  180, None, 2018, 480000,  "EUR", "20-tray column"),
    ("column",         "Distillation packed",  60,   "m3",   38000, "stainless_steel_316", 8,  160, None, 2019, 620000,  "EUR", "Packed column"),
    ("reactor",        "Pressure vessel",      35,   "m3",   45000, "stainless_steel_316", 25, 220, None, 2020, 780000,  "EUR", "Batch reactor"),
    ("reactor",        "CSTR",                 25,   "m3",   28000, "carbon_steel",       15,  200, None, 2017, 420000,  "EUR", "CSTR"),
    ("heat_exchanger", "Shell & tube",         120,  "m2",    8500, "stainless_steel_304", 16, 250, None, 2019, 180000,  "EUR", "S&T HX 120m2"),
    ("heat_exchanger", "Plate",                80,   "m2",    2500, "stainless_steel_316", 10, 150, None, 2020, 120000,  "EUR", "Plate HX"),
    ("storage_tank",   "Atmospheric",          500,  "m3",   35000, "carbon_steel",        1,  50,  None, 2016, 210000,  "EUR", "Atm tank 500m3"),
    ("storage_tank",   "Pressurized",          200,  "m3",   28000, "carbon_steel",        6,  80,  None, 2019, 340000,  "EUR", "Pressurized tank"),
    ("pump",           "Centrifugal",          80,   "m3/h",  1200, "stainless_steel_316", 10, 120, 55,   2020, 42000,   "EUR", "Centrifugal pump 55kW"),
    ("pump",           "Centrifugal",          150,  "m3/h",  1800, "stainless_steel_316", 15, 150, 110,  2021, 78000,   "EUR", "Centrifugal pump 110kW"),
    ("compressor",     "Centrifugal",          8000, "m3/h",  12000,"carbon_steel",       25, 180, 450,  2020, 950000,  "EUR", "Centrifugal compressor"),
    ("valve",          "Control",              100,  "DN(mm)", 50,  "stainless_steel_316", 20, 150, None, 2020, 6500,    "EUR", "DN100 control valve"),
    ("instrumentation","Pressure transmitter", 1,    "unit",   2,   "stainless_steel_316", 40, 80,  None, 2021, 1800,    "EUR", "PT smart"),
]

DUMMY_ROWS = [
    # (tag, category, subtype, size, unit, material, P, T, power, qty)
    ("C-101", "column",         "Distillation packed", 50,   "m3",     "stainless_steel_316", 10, 170, None, 1),
    ("R-201", "reactor",        "CSTR",                30,   "m3",     "stainless_steel_316", 20, 210, None, 1),
    ("E-301", "heat_exchanger", "Shell & tube",        150,  "m2",     "stainless_steel_304", 15, 240, None, 2),
    ("T-401", "storage_tank",   "Atmospheric",         600,  "m3",     "carbon_steel",        1,  50,  None, 3),
    ("P-501", "pump",           "Centrifugal",         100,  "m3/h",   "stainless_steel_316", 12, 130, 75,   4),
    ("K-601", "compressor",     "Centrifugal",         10000,"m3/h",   "carbon_steel",        22, 170, 600,  1),
    ("V-701", "valve",          "Control",             100,  "DN(mm)", "stainless_steel_316", 20, 150, None, 25),
    ("I-801", "instrumentation","Pressure transmitter",1,    "unit",   "stainless_steel_316", 40, 80,  None, 40),
]

async def seed_data():
    # seed historical if empty
    count = await db.equipment_historical.count_documents({})
    if count == 0:
        logging.info("Seeding historical equipment...")
        for row in DUMMY_HISTORICAL:
            (cat, sub, size, unit, w, mat, p, t, pw, yr, cost, ccy, notes) = row
            obj = HistoricalEquipment(
                category=cat, subtype=sub, size=size, size_unit=unit, weight_kg=w,
                material=mat, design_pressure_bar=p, design_temperature_c=t, power_kw=pw,
                year=yr, cost_original=cost, currency=ccy, notes=notes,
            )
            doc = obj.model_dump()
            doc["created_at"] = doc["created_at"].isoformat()
            await db.equipment_historical.insert_one(doc)

    # seed dummy project if no projects exist
    proj_count = await db.projects.count_documents({})
    if proj_count == 0:
        logging.info("Seeding dummy project...")
        proj = Project(name="DUMMY - Petrochemical Unit", description="Sample project pre-populated for testing", output_currency="EUR", target_year=datetime.now(timezone.utc).year)
        pdoc = proj.model_dump()
        pdoc["created_at"] = pdoc["created_at"].isoformat()
        await db.projects.insert_one(pdoc)
        for r in DUMMY_ROWS:
            (tag, cat, sub, size, unit, mat, p, t, pw, qty) = r
            data = {
                "tag": tag, "category": cat, "subtype": sub, "size": size,
                "size_unit": unit, "material": mat,
                "design_pressure_bar": p, "design_temperature_c": t,
                "power_kw": pw, "quantity": qty,
            }
            est = await _compute_row_estimate(pdoc, data)
            row_obj = EquipmentRow(project_id=proj.id, **data, **est)
            rdoc = row_obj.model_dump()
            rdoc["created_at"] = rdoc["created_at"].isoformat()
            await db.equipment_rows.insert_one(rdoc)

# -------------------- APP SETUP --------------------
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def on_startup():
    try:
        await seed_data()
    except Exception as e:
        logger.exception(f"Seed failed: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
