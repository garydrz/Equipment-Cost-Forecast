"""
EPC Equipment Parametric Cost Estimation - Backend v2 (weighted_similarity_v2)
- Explicit primary scaling variable per category with fallback
- Material factor (target_MF / reference_MF)
- Pressure factor on absolute pressures with per-category exponent
- Similarity index -> weighted average + weighted std
- Full breakdown + references detail (used & excluded)
"""
from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal, Any, Dict, Tuple
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

MODEL_VERSION = "weighted_similarity_v2"

app = FastAPI(title="EPC Cost Estimator", version="2.0")
api_router = APIRouter(prefix="/api")

# ============================================================
# CATEGORY META: primary scaling variable, allowed fields, units
# ============================================================
CATEGORIES = [
    "column", "reactor", "vessel", "heat_exchanger", "storage_tank",
    "pump", "compressor", "valve", "instrumentation", "other",
]

CATEGORY_META = {
    "column": {
        "label": "Distillation Column",
        "primary_variable": "weight_kg",
        "primary_unit_si": "kg",
        "fallback_variable": "size",
        "fallback_unit_si": "m³",
        "size_unit_symbol": "m³",
        "size_unit": "m3",
        "default_n": 0.65,
        "steel_w": 0.80, "oil_w": 0.20,
        "pressure_exp_default": 0.60,
        "pressure_enabled_default": True,
        "show_power": False,
        "allowed_fields": ["weight_kg", "size", "design_pressure_barg", "design_temperature_c", "material", "subtype"],
        "required_fields": ["size", "material"],
    },
    "reactor": {
        "label": "Reactor",
        "primary_variable": "weight_kg", "primary_unit_si": "kg",
        "fallback_variable": "size", "fallback_unit_si": "m³",
        "size_unit_symbol": "m³", "size_unit": "m3",
        "default_n": 0.65,
        "steel_w": 0.80, "oil_w": 0.20,
        "pressure_exp_default": 0.60, "pressure_enabled_default": True,
        "show_power": False,
        "allowed_fields": ["weight_kg", "size", "design_pressure_barg", "design_temperature_c", "material", "subtype"],
        "required_fields": ["size", "material"],
    },
    "vessel": {
        "label": "Vessel",
        "primary_variable": "weight_kg", "primary_unit_si": "kg",
        "fallback_variable": "size", "fallback_unit_si": "m³",
        "size_unit_symbol": "m³", "size_unit": "m3",
        "default_n": 0.62,
        "steel_w": 0.80, "oil_w": 0.20,
        "pressure_exp_default": 0.55, "pressure_enabled_default": True,
        "show_power": False,
        "allowed_fields": ["weight_kg", "size", "design_pressure_barg", "design_temperature_c", "material", "subtype"],
        "required_fields": ["size", "material"],
    },
    "storage_tank": {
        "label": "Storage Tank",
        "primary_variable": "weight_kg", "primary_unit_si": "kg",
        "fallback_variable": "size", "fallback_unit_si": "m³",
        "size_unit_symbol": "m³", "size_unit": "m3",
        "default_n": 0.62,
        "steel_w": 0.80, "oil_w": 0.20,
        "pressure_exp_default": 0.50, "pressure_enabled_default": True,
        "show_power": False,
        "allowed_fields": ["weight_kg", "size", "design_pressure_barg", "design_temperature_c", "material", "subtype"],
        "required_fields": ["size", "material"],
    },
    "heat_exchanger": {
        "label": "Heat Exchanger",
        "primary_variable": "weight_kg", "primary_unit_si": "kg",
        "fallback_variable": "size", "fallback_unit_si": "m²",
        "size_unit_symbol": "m²", "size_unit": "m2",
        "default_n": 0.65,
        "steel_w": 0.80, "oil_w": 0.20,
        "pressure_exp_default": 0.50, "pressure_enabled_default": True,
        "show_power": False,
        "allowed_fields": ["weight_kg", "size", "design_pressure_barg", "design_temperature_c", "material", "subtype"],
        "required_fields": ["size", "material"],
    },
    "pump": {
        "label": "Pump",
        "primary_variable": "power_kw", "primary_unit_si": "kW",
        "fallback_variable": "size", "fallback_unit_si": "m³/h",
        "size_unit_symbol": "m³/h", "size_unit": "m3/h",
        "default_n": 0.60,
        "steel_w": 0.40, "oil_w": 0.60,
        "pressure_exp_default": 0.0, "pressure_enabled_default": False,
        "show_power": True,
        "allowed_fields": ["power_kw", "size", "design_pressure_barg", "material", "subtype", "weight_kg"],
        "required_fields": ["material"],
    },
    "compressor": {
        "label": "Compressor",
        "primary_variable": "power_kw", "primary_unit_si": "kW",
        "fallback_variable": "size", "fallback_unit_si": "m³/h",
        "size_unit_symbol": "m³/h", "size_unit": "m3/h",
        "default_n": 0.75,
        "steel_w": 0.40, "oil_w": 0.60,
        "pressure_exp_default": 0.0, "pressure_enabled_default": False,
        "show_power": True,
        "allowed_fields": ["power_kw", "size", "design_pressure_barg", "material", "subtype", "weight_kg"],
        "required_fields": ["material"],
    },
    "valve": {
        "label": "Valve",
        "primary_variable": "size", "primary_unit_si": "mm",
        "fallback_variable": None, "fallback_unit_si": None,
        "size_unit_symbol": "mm", "size_unit": "mm",
        "default_n": 0.40,
        "steel_w": 0.60, "oil_w": 0.40,
        "pressure_exp_default": 0.30, "pressure_enabled_default": True,
        "show_power": False,
        "allowed_fields": ["size", "design_pressure_barg", "design_temperature_c", "material", "subtype"],
        "required_fields": ["size", "material"],
    },
    "instrumentation": {
        "label": "Instrumentation",
        "primary_variable": "size", "primary_unit_si": "unit",
        "fallback_variable": None, "fallback_unit_si": None,
        "size_unit_symbol": "unit", "size_unit": "unit",
        "default_n": 0.30,
        "steel_w": 0.60, "oil_w": 0.40,
        "pressure_exp_default": 0.0, "pressure_enabled_default": False,
        "show_power": False,
        "allowed_fields": ["size", "material", "subtype"],
        "required_fields": ["size"],
    },
    "other": {
        "label": "Other",
        "primary_variable": "size", "primary_unit_si": "unit",
        "fallback_variable": None, "fallback_unit_si": None,
        "size_unit_symbol": "unit", "size_unit": "unit",
        "default_n": 0.60,
        "steel_w": 0.70, "oil_w": 0.30,
        "pressure_exp_default": 0.30, "pressure_enabled_default": False,
        "show_power": False,
        "allowed_fields": ["size", "material", "subtype", "weight_kg", "power_kw", "design_pressure_barg", "design_temperature_c"],
        "required_fields": ["size"],
    },
}

MATERIALS = ["carbon_steel", "stainless_steel_304", "stainless_steel_316", "duplex", "alloy", "other"]

# Preliminary configurable defaults; NOT normative. To be calibrated on company data.
MATERIAL_FACTOR_DEFAULTS = {
    "carbon_steel":         {"factor": 1.00, "source": "reference material",         "notes": "Reference material (F=1.0)"},
    "stainless_steel_304":  {"factor": 1.70, "source": "preliminary configurable",  "notes": "To be calibrated"},
    "stainless_steel_316":  {"factor": 2.10, "source": "preliminary configurable",  "notes": "To be calibrated"},
    "duplex":               {"factor": 3.00, "source": "preliminary configurable",  "notes": "To be calibrated"},
    "alloy":                {"factor": 4.50, "source": "preliminary configurable",  "notes": "To be calibrated"},
    "other":                {"factor": 1.50, "source": "preliminary configurable",  "notes": "Unknown material - to be reviewed"},
}
REFERENCE_MATERIAL = "carbon_steel"

# Similarity defaults - user configurable via admin
SIMILARITY_DEFAULTS = {
    "alpha": 1.0,             # size distance decay
    "beta": 0.5,              # material distance decay
    "gamma": 0.5,             # pressure distance decay
    "w_size": 0.60,
    "w_subtype": 0.15,
    "w_material": 0.15,
    "w_pressure": 0.10,
    "subtype_mismatch": 0.5,  # value when subtype differs
    "min_similarity": 0.10,
    "max_references": 20,
    "min_references": 1,
    "max_extrapolation_ratio": 5.0,  # X_t/X_r or X_r/X_t limit
    "atmospheric_pressure_bar": 1.01325,
    "missing_material_factor_policy": "exclude",   # or "block"
    "missing_pressure_policy": "exclude",          # or "block"
}

# ============================================================
# MODELS
# ============================================================
class HistoricalEquipment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    category: str
    subtype: Optional[str] = None
    size: float
    size_unit: str
    weight_kg: Optional[float] = None
    material: str
    design_pressure_bar: Optional[float] = None  # barg (legacy field name kept)
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
    size: float = Field(gt=0)
    size_unit: str
    weight_kg: Optional[float] = Field(default=None, gt=0)
    material: str
    design_pressure_bar: Optional[float] = None
    design_temperature_c: Optional[float] = None
    power_kw: Optional[float] = Field(default=None, gt=0)
    year: int
    cost_original: float = Field(gt=0)
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
    aace_class: Literal["Class 5", "Class 4", "Class 3", "Class 2", "Class 1"] = "Class 5"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    output_currency: Literal["EUR", "USD"] = "EUR"
    target_year: Optional[int] = None
    aace_class: Optional[Literal["Class 5", "Class 4", "Class 3", "Class 2", "Class 1"]] = "Class 5"

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    output_currency: Optional[Literal["EUR", "USD"]] = None
    target_year: Optional[int] = None
    aace_class: Optional[Literal["Class 5", "Class 4", "Class 3", "Class 2", "Class 1"]] = None

class EquipmentRow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    tag: Optional[str] = None
    category: str
    subtype: Optional[str] = None
    size: float
    size_unit: str
    weight_kg: Optional[float] = None
    material: str
    design_pressure_bar: Optional[float] = None
    design_temperature_c: Optional[float] = None
    power_kw: Optional[float] = None
    quantity: int = 1
    reference_ids: Optional[List[str]] = None
    # results
    unit_expected_cost: float = 0.0
    unit_low: float = 0.0
    unit_high: float = 0.0
    total_expected_cost: float = 0.0
    total_sigma: float = 0.0
    aace_class: str = "Class 5"
    references_used: int = 0
    references_candidate: int = 0
    effective_sample_size: float = 0.0
    escalation_factor: float = 1.0
    scaling_variable: Optional[str] = None
    scaling_variable_value: Optional[float] = None
    scaling_variable_unit: Optional[str] = None
    scaling_variable_is_fallback: bool = False
    material_factor_summary: Optional[Dict[str, Any]] = None
    pressure_factor_summary: Optional[Dict[str, Any]] = None
    similarity_summary: Optional[Dict[str, Any]] = None
    estimation_breakdown: Optional[Dict[str, Any]] = None
    references_detail: Optional[List[Dict[str, Any]]] = None
    references_excluded: Optional[List[Dict[str, Any]]] = None
    warnings: Optional[List[str]] = None
    estimate_available: bool = False
    model_version: str = MODEL_VERSION
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class EquipmentRowCreate(BaseModel):
    tag: Optional[str] = None
    category: str
    subtype: Optional[str] = None
    size: float = Field(gt=0)
    size_unit: Optional[str] = None
    weight_kg: Optional[float] = Field(default=None, gt=0)
    material: str
    design_pressure_bar: Optional[float] = None
    design_temperature_c: Optional[float] = None
    power_kw: Optional[float] = Field(default=None, gt=0)
    quantity: int = Field(default=1, ge=1)
    reference_ids: Optional[List[str]] = None

class ScaleExponent(BaseModel):
    category: str
    n: float

class EscalationWeight(BaseModel):
    category: str
    steel_weight: float
    oil_weight: float

class MaterialFactor(BaseModel):
    material: str
    factor: float
    reference_material: str = REFERENCE_MATERIAL
    source: Optional[str] = None
    notes: Optional[str] = None

class PressureSetting(BaseModel):
    category: str
    pressure_exponent: float
    enabled: bool
    minimum_factor: Optional[float] = None
    maximum_factor: Optional[float] = None
    source: Optional[str] = None
    notes: Optional[str] = None

class SimilarityConfig(BaseModel):
    alpha: float
    beta: float
    gamma: float
    w_size: float
    w_subtype: float
    w_material: float
    w_pressure: float
    subtype_mismatch: float
    min_similarity: float
    max_references: int
    min_references: int
    max_extrapolation_ratio: float
    atmospheric_pressure_bar: float
    missing_material_factor_policy: Literal["exclude", "block"] = "exclude"
    missing_pressure_policy: Literal["exclude", "block"] = "exclude"

# ============================================================
# CONFIG ACCESSORS
# ============================================================
async def get_scale_exponent(category: str) -> float:
    doc = await db.scale_exponents.find_one({"category": category})
    if doc:
        return float(doc["n"])
    return CATEGORY_META.get(category, {}).get("default_n", 0.6)

async def get_escalation_weights(category: str) -> Tuple[float, float]:
    doc = await db.escalation_weights.find_one({"category": category})
    if doc:
        return float(doc["steel_weight"]), float(doc["oil_weight"])
    meta = CATEGORY_META.get(category, CATEGORY_META["other"])
    return float(meta["steel_w"]), float(meta["oil_w"])

async def get_material_factors_map() -> Dict[str, Dict[str, Any]]:
    docs = await db.material_factors.find({}, {"_id": 0}).to_list(1000)
    m = {d["material"]: d for d in docs}
    for mat, defaults in MATERIAL_FACTOR_DEFAULTS.items():
        if mat not in m:
            m[mat] = {"material": mat, **defaults, "reference_material": REFERENCE_MATERIAL}
    return m

async def get_pressure_setting(category: str) -> Dict[str, Any]:
    doc = await db.pressure_settings.find_one({"category": category}, {"_id": 0})
    meta = CATEGORY_META.get(category, CATEGORY_META["other"])
    default = {
        "category": category,
        "pressure_exponent": meta["pressure_exp_default"],
        "enabled": meta["pressure_enabled_default"],
        "minimum_factor": None,
        "maximum_factor": None,
        "source": "preliminary configurable defaults",
        "notes": "to be calibrated on company historical data",
    }
    if doc:
        default.update(doc)
    return default

async def get_similarity_config() -> Dict[str, Any]:
    doc = await db.similarity_config.find_one({"_id": "singleton"}, {"_id": 0})
    cfg = dict(SIMILARITY_DEFAULTS)
    if doc:
        cfg.update(doc)
    return cfg

# ============================================================
# EXTERNAL INDICES (FRED) with in-process cache
# ============================================================
FALLBACK_STEEL = {2005: 88, 2006: 96, 2007: 106, 2008: 128, 2009: 90, 2010: 108,
    2011: 128, 2012: 118, 2013: 112, 2014: 111, 2015: 100, 2016: 96,
    2017: 108, 2018: 128, 2019: 118, 2020: 114, 2021: 190, 2022: 220,
    2023: 178, 2024: 172, 2025: 176, 2026: 180}
FALLBACK_OIL = {2005: 54, 2006: 65, 2007: 72, 2008: 97, 2009: 62, 2010: 80,
    2011: 111, 2012: 112, 2013: 109, 2014: 99, 2015: 52, 2016: 44,
    2017: 54, 2018: 71, 2019: 64, 2020: 42, 2021: 71, 2022: 100,
    2023: 82, 2024: 80, 2025: 78, 2026: 78}

_indices_cache = {"steel": None, "oil": None, "ts": 0.0, "source": None}
_indices_lock = asyncio.Lock()

async def fetch_fred_annual(series_id: str) -> dict:
    if not FRED_API_KEY:
        return {}
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {"series_id": series_id, "api_key": FRED_API_KEY, "file_type": "json",
              "frequency": "a", "aggregation_method": "avg", "observation_start": "2000-01-01"}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, params=params); r.raise_for_status()
            data = r.json()
        out = {}
        for obs in data.get("observations", []):
            try:
                y = int(obs["date"][:4]); v = float(obs["value"]); out[y] = v
            except (ValueError, KeyError):
                continue
        return out
    except Exception as e:
        logging.warning(f"FRED fetch failed for {series_id}: {e}")
        return {}

async def get_indices():
    now = datetime.now(timezone.utc).timestamp()
    async with _indices_lock:
        if _indices_cache["steel"] and (now - _indices_cache["ts"] < 6 * 3600):
            return _indices_cache["steel"], _indices_cache["oil"], _indices_cache["source"]
        steel, oil = await asyncio.gather(
            fetch_fred_annual("WPU101706"),
            fetch_fred_annual("DCOILBRENTEU"),
        )
        source = "FRED"
        if not steel:
            steel = FALLBACK_STEEL; source = "fallback"
        if not oil:
            oil = FALLBACK_OIL; source = "fallback"
        _indices_cache["steel"] = steel; _indices_cache["oil"] = oil
        _indices_cache["ts"] = now; _indices_cache["source"] = source
        return steel, oil, source

def _nearest_year_value(series: dict, year: int) -> float:
    if year in series:
        return series[year]
    years = sorted(series.keys())
    if not years:
        return 100.0
    if year < years[0]: return series[years[0]]
    if year > years[-1]: return series[years[-1]]
    for i, y in enumerate(years):
        if y >= year:
            prev_y = years[i - 1] if i > 0 else y
            if prev_y == y: return series[y]
            frac = (year - prev_y) / (y - prev_y)
            return series[prev_y] + frac * (series[y] - series[prev_y])
    return series[years[-1]]

def compute_escalation_sync(from_year: int, to_year: int, steel_w: float, oil_w: float,
                            steel: dict, oil: dict) -> float:
    s_from = _nearest_year_value(steel, from_year); s_to = _nearest_year_value(steel, to_year)
    o_from = _nearest_year_value(oil, from_year); o_to = _nearest_year_value(oil, to_year)
    d_steel = (s_to - s_from) / s_from if s_from else 0.0
    d_oil = (o_to - o_from) / o_from if o_from else 0.0
    return 1.0 + steel_w * d_steel + oil_w * d_oil

# ============================================================
# FX (Frankfurter) with cache
# ============================================================
_fx_cache: Dict[str, float] = {}
_fx_lock = asyncio.Lock()

async def fx_rate(base: str, target: str, date: Optional[str] = None) -> Tuple[float, bool]:
    """Return (rate, is_fallback)."""
    if base == target:
        return 1.0, False
    date_key = date or "latest"
    cache_key = f"{base}-{target}-{date_key}"
    if cache_key in _fx_cache:
        return _fx_cache[cache_key], False
    url = f"https://api.frankfurter.dev/v1/{date_key}"
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(url, params={"base": base, "symbols": target}); r.raise_for_status()
            data = r.json()
        rate = float(data["rates"][target])
        _fx_cache[cache_key] = rate
        return rate, False
    except Exception as e:
        logging.warning(f"FX fetch failed {base}->{target} {date_key}: {e}")
        rate = 1.08 if base == "EUR" and target == "USD" else 0.92
        return rate, True

async def batch_fx_rates(pairs: List[Tuple[str, str, int]]) -> Dict[Tuple[str, str, int], Tuple[float, bool]]:
    """pairs = [(base, target, year)]; year None uses latest."""
    unique = list(set(pairs))
    async def one(p):
        base, target, year = p
        date = f"{year}-06-15" if year else None
        rate, fb = await fx_rate(base, target, date)
        return p, rate, fb
    results = await asyncio.gather(*[one(p) for p in unique])
    return {p: (r, f) for p, r, f in results}

# ============================================================
# SCALING VARIABLE LOGIC
# ============================================================
def get_scaling_variable(category: str, record: Dict[str, Any], force_use_fallback: bool = False) -> Optional[Dict[str, Any]]:
    """Choose scaling variable & value for a target or reference record.
    If force_use_fallback=True, skip the primary variable and use the fallback directly.
    Returns dict {name, value, unit, is_fallback, fallback_reason} or None if unavailable."""
    meta = CATEGORY_META.get(category)
    if not meta:
        return None
    pv = meta["primary_variable"]
    fv = meta["fallback_variable"]

    def val(field):
        v = record.get(field)
        try:
            v = float(v) if v is not None else None
        except (TypeError, ValueError):
            v = None
        return v if (v is not None and v > 0) else None

    if not force_use_fallback:
        if pv == "weight_kg":
            w = val("weight_kg")
            if w is not None:
                return {"name": "weight_kg", "value": w, "unit": "kg", "is_fallback": False, "fallback_reason": None}
        elif pv == "power_kw":
            p = val("power_kw")
            if p is not None:
                return {"name": "power_kw", "value": p, "unit": "kW", "is_fallback": False, "fallback_reason": None}
        elif pv == "size":
            s = val("size")
            if s is not None:
                return {"name": "size", "value": s, "unit": meta["primary_unit_si"], "is_fallback": False, "fallback_reason": None}

    if fv is None:
        return None
    if fv == "size":
        s = val("size")
        if s is not None:
            reason = f"{pv} unavailable, using {meta['fallback_unit_si']}"
            return {"name": "size", "value": s, "unit": meta["fallback_unit_si"], "is_fallback": True, "fallback_reason": reason}
    return None

# ============================================================
# CORE ESTIMATION
# ============================================================
def _classify_confidence(n_eff: float) -> str:
    """Informational data-quality label (not the AACE class of the project)."""
    if n_eff >= 4: return "High"
    if n_eff >= 2: return "Medium"
    return "Low"

def _unavailable(errors, warnings, candidates=None, excluded=None, category=None, subtype=None):
    return {
        "estimate_available": False,
        "expected": None, "low": None, "high": None,
        "sigma": None, "cov": None,
        "candidate_references": len(candidates) if candidates else 0,
        "references_used": 0,
        "effective_sample_size": 0.0,
        "scaling_variable": None, "scaling_variable_value": None,
        "scaling_variable_unit": None, "scaling_variable_is_fallback": False,
        "material_factor_summary": None, "pressure_factor_summary": None,
        "similarity_summary": None,
        "references_detail": [], "references_excluded": excluded or [],
        "estimation_breakdown": None,
        "warnings": list(dict.fromkeys(warnings or [])),
        "errors": errors or [],
        "escalation_factor": 0.0,
        "quantity": 1,
        "total_expected": None, "total_low": None, "total_high": None,
        "category": category, "subtype": subtype,
        "model_version": MODEL_VERSION,
    }

async def estimate_full(
    *,
    category: str,
    target_size: Optional[float],
    target_weight_kg: Optional[float],
    target_power_kw: Optional[float],
    target_material: str,
    target_pressure_barg: Optional[float],
    subtype: Optional[str],
    target_year: int,
    output_currency: str,
    reference_ids: Optional[List[str]] = None,
    quantity: int = 1,
) -> Dict[str, Any]:
    warnings: List[str] = []
    errors: List[str] = []
    meta = CATEGORY_META.get(category)
    if not meta:
        return _unavailable([f"unknown category {category}"], warnings, category=category, subtype=subtype)

    # --- 1) Target scaling variable
    target_record = {"size": target_size, "weight_kg": target_weight_kg, "power_kw": target_power_kw}
    target_sv = get_scaling_variable(category, target_record)
    if not target_sv:
        return _unavailable(
            [f"target scaling variable ({meta['primary_variable']}) unavailable and no fallback usable"],
            warnings, category=category, subtype=subtype,
        )
    if target_sv["is_fallback"]:
        warnings.append(f"Fallback variable used for target: {target_sv['fallback_reason']}")

    # --- 2) Load config
    n_exp = await get_scale_exponent(category)
    steel_w, oil_w = await get_escalation_weights(category)
    mfs = await get_material_factors_map()
    pset = await get_pressure_setting(category)
    sim = await get_similarity_config()
    atm = float(sim["atmospheric_pressure_bar"])
    steel, oil, idx_src = await get_indices()
    if idx_src != "FRED":
        warnings.append("Escalation indices are using fallback data (FRED unavailable)")

    # Target pressure absolute
    p_target_abs = None
    if target_pressure_barg is not None:
        try:
            p_target_abs = float(target_pressure_barg) + atm
            if p_target_abs <= 0:
                p_target_abs = None
                warnings.append("Target absolute pressure <= 0, ignoring pressure factor for target")
        except (TypeError, ValueError):
            p_target_abs = None

    target_mf_doc = mfs.get(target_material)
    if not target_mf_doc:
        errors.append(f"Material factor for target material '{target_material}' not configured")
        return _unavailable(errors, warnings, category=category, subtype=subtype)
    target_mf = float(target_mf_doc["factor"])

    # --- 3) Fetch candidate references
    q: Dict[str, Any] = {"category": category}
    if reference_ids:
        q = {"id": {"$in": reference_ids}}
    candidates = await db.equipment_historical.find(q, {"_id": 0}).to_list(1000)
    if not candidates:
        return _unavailable(["no historical references found for this category"], warnings, category=category, subtype=subtype)

    # Pre-batch FX rates (base=ref.currency, target=output_currency, year=ref.year)
    fx_pairs = [(r["currency"], output_currency, int(r["year"])) for r in candidates if r.get("currency") and r.get("year")]
    fx_map = await batch_fx_rates(fx_pairs)

    used = []
    excluded = []

    for ref in candidates:
        ref_id = ref.get("id")
        rec = {"size": ref.get("size"), "weight_kg": ref.get("weight_kg"), "power_kw": ref.get("power_kw")}
        # When the target is using fallback, force refs to also use the fallback variable (same name)
        ref_sv = get_scaling_variable(category, rec, force_use_fallback=target_sv["is_fallback"])
        if not ref_sv:
            excluded.append({
                "historical_equipment_id": ref_id, "subtype": ref.get("subtype"), "year": ref.get("year"),
                "exclusion_reason": "no scaling variable available",
                "available_values": rec, "similarity": None, "missing_or_invalid_fields": ["scaling_variable"],
            })
            continue

        # Compatibility: must match variable NAME (unit compatibility). Fallback flag can differ if
        # forced-fallback lookup succeeded with the same variable name.
        if ref_sv["name"] != target_sv["name"]:
            excluded.append({
                "historical_equipment_id": ref_id, "subtype": ref.get("subtype"), "year": ref.get("year"),
                "exclusion_reason": f"incompatible scaling variable (target={target_sv['name']}, ref={ref_sv['name']})",
                "available_values": rec, "similarity": None, "missing_or_invalid_fields": ["scaling_variable_mismatch"],
            })
            continue

        x_t = target_sv["value"]; x_r = ref_sv["value"]
        if x_r <= 0 or x_t <= 0:
            excluded.append({"historical_equipment_id": ref_id, "exclusion_reason": "invalid scaling values",
                             "available_values": {"target": x_t, "reference": x_r}, "similarity": None})
            continue

        # extrapolation check
        ratio_hi = max(x_t / x_r, x_r / x_t)
        extrap_flag = ratio_hi > float(sim["max_extrapolation_ratio"])
        # size scaling factor
        f_size = (x_t / x_r) ** n_exp
        c_after_size = float(ref["cost_original"]) * f_size

        # material factor
        ref_material = ref.get("material")
        ref_mf_doc = mfs.get(ref_material)
        if not ref_mf_doc:
            if sim["missing_material_factor_policy"] == "block":
                errors.append(f"Missing material factor for ref material {ref_material} (blocking policy)")
                return _unavailable(errors, warnings, candidates, excluded, category, subtype)
            excluded.append({
                "historical_equipment_id": ref_id, "exclusion_reason": f"missing material factor for '{ref_material}'",
                "reference_material": ref_material, "target_material": target_material, "similarity": None,
            })
            continue
        ref_mf = float(ref_mf_doc["factor"])
        f_material = target_mf / ref_mf
        c_after_material = c_after_size * f_material

        # pressure factor
        p_ref_barg = ref.get("design_pressure_bar")
        p_ref_abs = None
        try:
            if p_ref_barg is not None:
                p_ref_abs = float(p_ref_barg) + atm
                if p_ref_abs <= 0: p_ref_abs = None
        except (TypeError, ValueError):
            p_ref_abs = None

        p_exp = float(pset["pressure_exponent"]); p_enabled = bool(pset["enabled"])
        pressure_applied = False; pressure_status = "disabled"
        f_pressure_unbounded = 1.0; f_pressure = 1.0; pressure_limited = False
        pressure_warn: List[str] = []

        if p_enabled and p_exp > 0:
            if p_target_abs is None:
                # target pressure absent -> skip pressure factor (F=1) with a global warning once
                pressure_applied = False; pressure_status = "skipped-target-pressure-missing"
                f_pressure_unbounded = 1.0; f_pressure = 1.0
                if "target design pressure missing; pressure factor not applied" not in warnings:
                    warnings.append("target design pressure missing; pressure factor not applied")
            elif p_ref_abs is None:
                if sim["missing_pressure_policy"] == "block":
                    errors.append("Missing reference pressure with block policy")
                    return _unavailable(errors, warnings, candidates, excluded, category, subtype)
                excluded.append({
                    "historical_equipment_id": ref_id, "exclusion_reason": "reference pressure missing",
                    "reference_design_pressure_barg": p_ref_barg, "target_design_pressure_barg": target_pressure_barg,
                    "similarity": None,
                })
                continue
            else:
                f_pressure_unbounded = (p_target_abs / p_ref_abs) ** p_exp
                f_pressure = f_pressure_unbounded
                mn = pset.get("minimum_factor"); mx = pset.get("maximum_factor")
                if mn is not None and f_pressure < mn:
                    f_pressure = mn; pressure_limited = True
                if mx is not None and f_pressure > mx:
                    f_pressure = mx; pressure_limited = True
                pressure_applied = True
                pressure_status = "limited" if pressure_limited else "applied"
        else:
            pressure_status = "disabled"

        c_after_pressure = c_after_material * f_pressure

        # escalation
        try:
            esc = compute_escalation_sync(int(ref["year"]), int(target_year), steel_w, oil_w, steel, oil)
        except Exception:
            esc = 1.0
            pressure_warn.append("escalation fallback")
        c_after_esc = c_after_pressure * esc

        # currency (rate at ref.year, base=ref.currency -> output_currency)
        fx_key = (ref["currency"], output_currency, int(ref["year"]))
        fx, fx_fb = fx_map.get(fx_key, (1.0, False))
        if fx_fb: warnings.append(f"FX fallback used for {ref['currency']}->{output_currency} @ {ref['year']}")
        c_adjusted = c_after_esc * fx

        if c_adjusted <= 0:
            excluded.append({"historical_equipment_id": ref_id, "exclusion_reason": "adjusted cost non-positive",
                             "similarity": None})
            continue

        # similarity components
        d_size = abs(math.log(x_t / x_r))
        s_size = math.exp(-float(sim["alpha"]) * d_size)

        # subtype
        ref_subtype = (ref.get("subtype") or "").strip().lower()
        tgt_subtype = (subtype or "").strip().lower()
        if subtype and ref_subtype:
            s_subtype = 1.0 if ref_subtype == tgt_subtype else float(sim["subtype_mismatch"])
            subtype_used = True
        else:
            s_subtype = None; subtype_used = False

        # material similarity: exp(-beta * |ln(MF_t/MF_r)|)
        if target_mf > 0 and ref_mf > 0:
            s_material = math.exp(-float(sim["beta"]) * abs(math.log(target_mf / ref_mf)))
            material_used = True
        else:
            s_material = None; material_used = False

        # pressure similarity
        if p_target_abs and p_ref_abs and p_enabled and p_exp > 0:
            s_pressure = math.exp(-float(sim["gamma"]) * abs(math.log(p_target_abs / p_ref_abs)))
            pressure_used_sim = True
        else:
            s_pressure = None; pressure_used_sim = False

        # renormalize weights over available components
        comps = [("size", float(sim["w_size"]), s_size)]
        if subtype_used: comps.append(("subtype", float(sim["w_subtype"]), s_subtype))
        if material_used: comps.append(("material", float(sim["w_material"]), s_material))
        if pressure_used_sim: comps.append(("pressure", float(sim["w_pressure"]), s_pressure))
        wsum = sum(w for _, w, _ in comps)
        if wsum <= 0:
            s_total = s_size
        else:
            s_total = sum((w / wsum) * s for _, w, s in comps)

        if s_total < float(sim["min_similarity"]):
            excluded.append({
                "historical_equipment_id": ref_id, "exclusion_reason": "Excluded due to insufficient similarity",
                "subtype": ref.get("subtype"), "similarity": round(s_total, 4),
                "size_similarity": round(s_size, 4),
            })
            continue

        ref_warnings: List[str] = list(pressure_warn)
        if extrap_flag:
            ref_warnings.append("Estimate based on extrapolation outside the validated historical range")

        used.append({
            "historical_equipment_id": ref_id,
            "category": ref.get("category"), "subtype": ref.get("subtype"), "year": ref.get("year"),
            "original_cost": float(ref["cost_original"]), "original_currency": ref.get("currency"),
            "scaling_variable_name": ref_sv["name"],
            "historical_scaling_variable_value": x_r,
            "target_scaling_variable_value": x_t,
            "scaling_variable_unit": ref_sv["unit"],
            "scale_exponent": n_exp,
            "size_ratio": x_t / x_r,
            "size_scaling_factor": f_size,
            "reference_material": ref_material, "target_material": target_material,
            "reference_material_coefficient": ref_mf, "target_material_coefficient": target_mf,
            "applied_material_factor": f_material,
            "reference_design_pressure_barg": p_ref_barg,
            "target_design_pressure_barg": target_pressure_barg,
            "reference_absolute_pressure_bara": p_ref_abs,
            "target_absolute_pressure_bara": p_target_abs,
            "pressure_exponent": p_exp,
            "applied_pressure_factor": f_pressure,
            "pressure_factor_unbounded": f_pressure_unbounded,
            "pressure_status": pressure_status,
            "escalation_factor": esc,
            "fx_factor": fx,
            "cost_after_size_scaling": c_after_size,
            "cost_after_material_correction": c_after_material,
            "cost_after_pressure_correction": c_after_pressure,
            "cost_after_escalation": c_after_esc,
            "cost_after_currency_conversion": c_adjusted,
            "adjusted_cost": c_adjusted,
            "size_similarity": s_size,
            "subtype_similarity": s_subtype,
            "material_similarity": s_material,
            "pressure_similarity": s_pressure,
            "total_similarity": s_total,
            "unnormalized_weight": s_total,
            "inclusion_status": "used",
            "warnings": ref_warnings,
        })

    # apply cap on number of references (top by similarity)
    used.sort(key=lambda x: x["total_similarity"], reverse=True)
    max_refs = int(sim["max_references"])
    if len(used) > max_refs:
        for extra in used[max_refs:]:
            excluded.append({
                "historical_equipment_id": extra["historical_equipment_id"],
                "exclusion_reason": f"beyond max_references cap ({max_refs})",
                "similarity": round(extra["total_similarity"], 4),
            })
        used = used[:max_refs]

    n_candidate = len(candidates)
    n_used = len(used)
    if n_used == 0:
        return _unavailable(
            ["all references were excluded"], warnings, candidates, excluded, category, subtype
        )

    # weighted mean & std
    w_sum = sum(r["unnormalized_weight"] for r in used)
    for r in used:
        r["normalized_weight"] = r["unnormalized_weight"] / w_sum if w_sum > 0 else 0.0
        r["weighted_contribution"] = r["adjusted_cost"] * r["normalized_weight"]
    expected = sum(r["weighted_contribution"] for r in used)
    # weighted variance (biased)
    var_w = sum(r["normalized_weight"] * (r["adjusted_cost"] - expected) ** 2 for r in used)
    sigma_w = math.sqrt(max(var_w, 0.0))
    n_eff = 1.0 / sum(r["normalized_weight"] ** 2 for r in used) if used else 0.0
    cov = sigma_w / expected if expected > 0 else 0.0

    # consistency check
    delta = abs(expected - sum(r["weighted_contribution"] for r in used))
    if delta > 1e-6 * max(1.0, expected):
        warnings.append(f"internal consistency check delta={delta}")

    # confidence range (use 1.645 sigma bracket)
    low = expected - 1.645 * sigma_w
    high = expected + 1.645 * sigma_w
    if low < 0: low = 0.0

    if n_eff < float(sim["min_references"]):
        warnings.append("effective sample size below minimum")
    if any("extrapolation" in (w or "") for r in used for w in (r.get("warnings") or [])):
        warnings.append("some references are outside validated historical range")
    # de-duplicate global warnings preserving order
    warnings = list(dict.fromkeys(warnings))

    material_factor_summary = {
        "target_material": target_material,
        "target_material_coefficient": target_mf,
        "reference_material_coefficients": {r["reference_material"]: r["reference_material_coefficient"] for r in used},
        "applied_material_factors_range": [min(r["applied_material_factor"] for r in used), max(r["applied_material_factor"] for r in used)],
    }
    pressure_factor_summary = {
        "target_design_pressure_barg": target_pressure_barg,
        "target_absolute_pressure_bara": p_target_abs,
        "pressure_exponent": pset["pressure_exponent"],
        "enabled": pset["enabled"],
        "applied_pressure_factors": [r["applied_pressure_factor"] for r in used],
        "atmospheric_pressure_bar": atm,
    }
    similarity_summary = {
        "alpha": sim["alpha"], "beta": sim["beta"], "gamma": sim["gamma"],
        "weights": {"size": sim["w_size"], "subtype": sim["w_subtype"], "material": sim["w_material"], "pressure": sim["w_pressure"]},
        "min_similarity": sim["min_similarity"],
        "average_similarity": sum(r["total_similarity"] for r in used) / n_used,
    }
    breakdown = {
        "category": category, "subtype": subtype,
        "target_material": target_material,
        "target_design_pressure_barg": target_pressure_barg,
        "target_absolute_pressure_bara": p_target_abs,
        "primary_scaling_variable": target_sv["name"],
        "scaling_variable_value": target_sv["value"],
        "scaling_variable_unit": target_sv["unit"],
        "fallback_status": target_sv["is_fallback"],
        "fallback_reason": target_sv["fallback_reason"],
        "scale_exponent_n": n_exp,
        "pressure_exponent": pset["pressure_exponent"],
        "pressure_enabled": pset["enabled"],
        "escalation_weights": {"steel_weight": steel_w, "oil_weight": oil_w},
        "similarity_configuration": similarity_summary,
        "target_year": target_year, "output_currency": output_currency,
        "candidate_references": n_candidate, "references_used": n_used,
        "excluded_references_count": len(excluded),
        "expected_cost": expected, "low_estimate": low, "high_estimate": high,
        "weighted_sigma": sigma_w, "coefficient_of_variation": cov,
        "effective_sample_size": n_eff,
        "data_quality": _classify_confidence(n_eff),
        "warnings": warnings,
        "model_version": MODEL_VERSION,
    }

    return {
        "estimate_available": True,
        "expected": round(expected, 2), "low": round(low, 2), "high": round(high, 2),
        "sigma": round(sigma_w, 2), "cov": round(cov, 4),
        "candidate_references": n_candidate, "references_used": n_used,
        "effective_sample_size": round(n_eff, 3),
        "scaling_variable": target_sv["name"], "scaling_variable_value": target_sv["value"],
        "scaling_variable_unit": target_sv["unit"], "scaling_variable_is_fallback": target_sv["is_fallback"],
        "material_factor_summary": material_factor_summary,
        "pressure_factor_summary": pressure_factor_summary,
        "similarity_summary": similarity_summary,
        "estimation_breakdown": breakdown,
        "references_detail": used,
        "references_excluded": excluded,
        "warnings": warnings, "errors": errors,
        "escalation_factor": round(sum(r["escalation_factor"] for r in used) / n_used, 4),
        "quantity": max(quantity, 1),
        "total_expected": round(expected * max(quantity, 1), 2),
        "total_low": round(low * max(quantity, 1), 2),
        "total_high": round(high * max(quantity, 1), 2),
        "model_version": MODEL_VERSION,
    }

# Backwards-compat wrapper for existing rows
async def _compute_row_estimate(project_doc, row_data) -> Dict[str, Any]:
    est = await estimate_full(
        category=row_data["category"],
        target_size=float(row_data["size"]) if row_data.get("size") is not None else None,
        target_weight_kg=float(row_data["weight_kg"]) if row_data.get("weight_kg") else None,
        target_power_kw=float(row_data["power_kw"]) if row_data.get("power_kw") else None,
        target_material=row_data["material"],
        target_pressure_barg=float(row_data["design_pressure_bar"]) if row_data.get("design_pressure_bar") is not None else None,
        subtype=row_data.get("subtype"),
        target_year=int(project_doc["target_year"]),
        output_currency=project_doc["output_currency"],
        reference_ids=row_data.get("reference_ids"),
    )
    qty = int(row_data.get("quantity") or 1)
    if not est.get("estimate_available"):
        return {
            "unit_expected_cost": 0.0, "unit_low": 0.0, "unit_high": 0.0,
            "total_expected_cost": 0.0, "total_sigma": 0.0,
            "aace_class": project_doc.get("aace_class", "Class 5"),
            "references_used": est.get("references_used", 0),
            "references_candidate": est.get("candidate_references", 0),
            "effective_sample_size": 0.0,
            "escalation_factor": 0.0,
            "scaling_variable": None, "scaling_variable_value": None,
            "scaling_variable_unit": None, "scaling_variable_is_fallback": False,
            "material_factor_summary": None, "pressure_factor_summary": None,
            "similarity_summary": None,
            "estimation_breakdown": est.get("estimation_breakdown"),
            "references_detail": [], "references_excluded": est.get("references_excluded", []),
            "warnings": est.get("warnings", []) + est.get("errors", []),
            "estimate_available": False, "model_version": MODEL_VERSION,
        }
    return {
        "unit_expected_cost": est["expected"],
        "unit_low": est["low"], "unit_high": est["high"],
        "total_expected_cost": round(est["expected"] * qty, 2),
        "total_sigma": round(est["sigma"] * math.sqrt(qty), 2),
        "aace_class": project_doc.get("aace_class", "Class 5"),
        "references_used": est["references_used"],
        "references_candidate": est["candidate_references"],
        "effective_sample_size": est["effective_sample_size"],
        "escalation_factor": est["escalation_factor"],
        "scaling_variable": est["scaling_variable"],
        "scaling_variable_value": est["scaling_variable_value"],
        "scaling_variable_unit": est["scaling_variable_unit"],
        "scaling_variable_is_fallback": est["scaling_variable_is_fallback"],
        "material_factor_summary": est["material_factor_summary"],
        "pressure_factor_summary": est["pressure_factor_summary"],
        "similarity_summary": est["similarity_summary"],
        "estimation_breakdown": est["estimation_breakdown"],
        "references_detail": est["references_detail"],
        "references_excluded": est["references_excluded"],
        "warnings": est["warnings"],
        "estimate_available": True,
        "model_version": MODEL_VERSION,
    }

# ============================================================
# ROUTES: meta & config
# ============================================================
@api_router.get("/")
async def root():
    return {"status": "ok", "service": "EPC Cost Estimator", "model_version": MODEL_VERSION}

@api_router.get("/meta/categories")
async def categories():
    return {"categories": CATEGORIES, "meta": CATEGORY_META, "materials": MATERIALS}

# ============================================================
# ROUTES: historical equipment
# ============================================================
@api_router.get("/equipment", response_model=List[HistoricalEquipment])
async def list_equipment(category: Optional[str] = None, q: Optional[str] = None):
    query = {}
    if category: query["category"] = category
    docs = await db.equipment_historical.find(query, {"_id": 0}).to_list(2000)
    if q:
        ql = q.lower()
        docs = [d for d in docs if ql in (d.get("subtype") or "").lower() or ql in (d.get("notes") or "").lower() or ql in (d.get("vendor_country") or "").lower()]
    return docs

@api_router.post("/equipment", response_model=HistoricalEquipment)
async def create_equipment(body: HistoricalEquipmentCreate):
    if body.category not in CATEGORY_META:
        raise HTTPException(400, "invalid category")
    obj = HistoricalEquipment(**body.model_dump())
    doc = obj.model_dump(); doc["created_at"] = doc["created_at"].isoformat()
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

# ============================================================
# ROUTES: projects
# ============================================================
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
    if not data.get("aace_class"): data["aace_class"] = "Class 5"
    obj = Project(**data)
    doc = obj.model_dump(); doc["created_at"] = doc["created_at"].isoformat()
    await db.projects.insert_one(doc)
    return obj

@api_router.get("/projects/{pid}")
async def get_project(pid: str):
    p = await db.projects.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Project not found")
    rows = await db.equipment_rows.find({"project_id": pid}, {"_id": 0}).sort("created_at", 1).to_list(2000)
    total_expected = sum(r.get("total_expected_cost", 0.0) for r in rows)
    total_sigma_sq = sum(r.get("total_sigma", 0.0) ** 2 for r in rows)
    total_sigma = math.sqrt(total_sigma_sq)
    half_ranges = []
    for r in rows:
        te = r.get("total_expected_cost", 0.0)
        qty = r.get("quantity", 1)
        hr = max(abs(te - r.get("unit_low", 0.0) * qty), abs(r.get("unit_high", 0.0) * qty - te))
        half_ranges.append(hr)
    proj_half = math.sqrt(sum(h ** 2 for h in half_ranges))
    proj_low = total_expected - proj_half
    proj_high = total_expected + proj_half
    if isinstance(p.get("created_at"), str):
        p["created_at"] = datetime.fromisoformat(p["created_at"])
    return {
        "project": p, "rows": rows,
        "totals": {
            "expected": round(total_expected, 2),
            "low": round(proj_low, 2),
            "high": round(proj_high, 2),
            "sigma": round(total_sigma, 2),
            "aace_class": p.get("aace_class", "Class 5"),
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

# ============================================================
# ROUTES: equipment rows
# ============================================================
def _sanitize_row_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """Enforce per-category allowed fields: nullify fields not in allowed_fields."""
    cat = data.get("category")
    meta = CATEGORY_META.get(cat)
    if not meta:
        return data
    allowed = set(meta["allowed_fields"])
    # power_kw: allowed only if in allowed_fields
    if "power_kw" not in allowed:
        data["power_kw"] = None
    if "weight_kg" not in allowed:
        data["weight_kg"] = None
    if "design_pressure_barg" not in allowed and "design_pressure_bar" not in allowed:
        data["design_pressure_bar"] = None
    if "design_temperature_c" not in allowed:
        data["design_temperature_c"] = None
    # fix size_unit to category default if missing
    if not data.get("size_unit"):
        data["size_unit"] = meta["size_unit"]
    return data

@api_router.post("/projects/{pid}/rows", response_model=EquipmentRow)
async def add_row(pid: str, body: EquipmentRowCreate):
    p = await db.projects.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Project not found")
    data = _sanitize_row_payload(body.model_dump())
    est = await _compute_row_estimate(p, data)
    row = EquipmentRow(project_id=pid, **data, **est)
    doc = row.model_dump(); doc["created_at"] = doc["created_at"].isoformat()
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
    data = _sanitize_row_payload(body.model_dump())
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
    p = await db.projects.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Project not found")
    rows = await db.equipment_rows.find({"project_id": pid}, {"_id": 0}).to_list(2000)
    for r in rows:
        data = _sanitize_row_payload(dict(r))
        est = await _compute_row_estimate(p, data)
        await db.equipment_rows.update_one({"id": r["id"]}, {"$set": {**data, **est}})
    return {"ok": True, "updated": len(rows)}

# ============================================================
# ROUTES: estimate preview
# ============================================================
class EstimatePreview(BaseModel):
    category: str
    subtype: Optional[str] = None
    size: Optional[float] = Field(default=None, gt=0)
    weight_kg: Optional[float] = Field(default=None, gt=0)
    power_kw: Optional[float] = Field(default=None, gt=0)
    material: str
    design_pressure_bar: Optional[float] = None
    target_year: int
    output_currency: Literal["EUR", "USD"] = "EUR"
    reference_ids: Optional[List[str]] = None
    quantity: int = Field(default=1, ge=1)

@api_router.post("/estimate")
async def estimate_preview(body: EstimatePreview):
    return await estimate_full(
        category=body.category,
        target_size=body.size,
        target_weight_kg=body.weight_kg,
        target_power_kw=body.power_kw,
        target_material=body.material,
        target_pressure_barg=body.design_pressure_bar,
        subtype=body.subtype,
        target_year=body.target_year,
        output_currency=body.output_currency,
        reference_ids=body.reference_ids,
        quantity=body.quantity,
    )

# ============================================================
# ROUTES: admin params
# ============================================================
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
        if item.n <= 0:
            raise HTTPException(400, f"scale exponent must be > 0 for {item.category}")
        await db.scale_exponents.update_one({"category": item.category}, {"$set": {"n": item.n, "updated_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    return {"ok": True}

@api_router.get("/admin/escalation-weights")
async def get_esc_weights():
    out = []
    for cat in CATEGORIES:
        doc = await db.escalation_weights.find_one({"category": cat}, {"_id": 0})
        if doc: sw, ow = doc["steel_weight"], doc["oil_weight"]
        else: sw, ow = CATEGORY_META[cat]["steel_w"], CATEGORY_META[cat]["oil_w"]
        out.append({"category": cat, "label": CATEGORY_META[cat]["label"],
                    "steel_weight": sw, "oil_weight": ow,
                    "default_steel": CATEGORY_META[cat]["steel_w"], "default_oil": CATEGORY_META[cat]["oil_w"]})
    return out

@api_router.put("/admin/escalation-weights")
async def set_esc_weights(body: List[EscalationWeight]):
    for item in body:
        if abs(item.steel_weight + item.oil_weight - 1) > 0.01:
            raise HTTPException(400, f"weights must sum to 1.0 for {item.category}")
        await db.escalation_weights.update_one({"category": item.category},
            {"$set": {"steel_weight": item.steel_weight, "oil_weight": item.oil_weight, "updated_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    return {"ok": True}

@api_router.get("/admin/material-factors")
async def get_material_factors():
    mfs = await get_material_factors_map()
    out = []
    for mat in MATERIALS:
        d = mfs.get(mat, {})
        default = MATERIAL_FACTOR_DEFAULTS.get(mat, {"factor": 1.0, "source": "unknown", "notes": ""})
        out.append({
            "material": mat, "factor": d.get("factor", default["factor"]),
            "reference_material": d.get("reference_material", REFERENCE_MATERIAL),
            "source": d.get("source", default["source"]),
            "notes": d.get("notes", default["notes"]),
            "default_factor": default["factor"],
            "updated_at": d.get("updated_at"),
        })
    return out

@api_router.put("/admin/material-factors")
async def set_material_factors(body: List[MaterialFactor]):
    for item in body:
        if item.factor <= 0:
            raise HTTPException(400, f"material factor must be > 0 for {item.material}")
        if item.material not in MATERIALS:
            raise HTTPException(400, f"unknown material {item.material}")
        await db.material_factors.update_one({"material": item.material},
            {"$set": {"factor": item.factor, "reference_material": item.reference_material,
                      "source": item.source, "notes": item.notes,
                      "updated_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    return {"ok": True}

@api_router.get("/admin/pressure-factors")
async def get_pressure_factors():
    out = []
    for cat in CATEGORIES:
        cfg = await get_pressure_setting(cat)
        out.append({
            "category": cat, "label": CATEGORY_META[cat]["label"],
            "pressure_exponent": cfg["pressure_exponent"],
            "enabled": cfg["enabled"],
            "minimum_factor": cfg.get("minimum_factor"),
            "maximum_factor": cfg.get("maximum_factor"),
            "source": cfg.get("source"),
            "notes": cfg.get("notes"),
            "default_exponent": CATEGORY_META[cat]["pressure_exp_default"],
            "default_enabled": CATEGORY_META[cat]["pressure_enabled_default"],
        })
    return out

@api_router.put("/admin/pressure-factors")
async def set_pressure_factors(body: List[PressureSetting]):
    for item in body:
        if item.pressure_exponent < 0:
            raise HTTPException(400, f"pressure exponent must be >= 0 for {item.category}")
        upd = item.model_dump(); upd["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.pressure_settings.update_one({"category": item.category}, {"$set": upd}, upsert=True)
    return {"ok": True}

@api_router.get("/admin/similarity-settings")
async def get_similarity_settings():
    cfg = await get_similarity_config()
    return {**cfg, "defaults": SIMILARITY_DEFAULTS}

@api_router.put("/admin/similarity-settings")
async def set_similarity_settings(body: SimilarityConfig):
    d = body.model_dump()
    if d["alpha"] <= 0: raise HTTPException(400, "alpha must be > 0")
    if d["beta"] < 0 or d["gamma"] < 0: raise HTTPException(400, "beta and gamma must be >= 0")
    ws = d["w_size"] + d["w_subtype"] + d["w_material"] + d["w_pressure"]
    if abs(ws - 1.0) > 0.01:
        raise HTTPException(400, "similarity weights must sum to 1.0")
    if not (0 <= d["min_similarity"] <= 1):
        raise HTTPException(400, "min_similarity must be in [0,1]")
    if d["max_references"] < 1: raise HTTPException(400, "max_references must be >= 1")
    if d["atmospheric_pressure_bar"] <= 0: raise HTTPException(400, "atmospheric_pressure_bar must be > 0")
    d["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.similarity_config.update_one({"_id": "singleton"}, {"$set": d}, upsert=True)
    return {"ok": True}

# ============================================================
# INDICES DEBUG
# ============================================================
@api_router.get("/indices")
async def indices_endpoint():
    steel, oil, src = await get_indices()
    return {
        "steel_by_year": {int(k): v for k, v in steel.items()},
        "oil_by_year": {int(k): v for k, v in oil.items()},
        "source": src,
    }

# ============================================================
# SEED
# ============================================================
DUMMY_HISTORICAL = [
    ("column",         "Distillation tray",    45,   "m3",   32000, "carbon_steel",       12,  180, None, 2018, 480000,  "EUR", "20-tray column"),
    ("column",         "Distillation packed",  60,   "m3",   38000, "stainless_steel_316", 8,  160, None, 2019, 620000,  "EUR", "Packed column"),
    ("reactor",        "Pressure vessel",      35,   "m3",   45000, "stainless_steel_316", 25, 220, None, 2020, 780000,  "EUR", "Batch reactor"),
    ("reactor",        "CSTR",                 25,   "m3",   28000, "carbon_steel",       15,  200, None, 2017, 420000,  "EUR", "CSTR"),
    ("vessel",         "Horizontal separator", 40,   "m3",   22000, "carbon_steel",       15,  90,  None, 2018, 260000,  "EUR", "Horizontal 3-phase separator"),
    ("vessel",         "Vertical KO drum",     25,   "m3",   16000, "stainless_steel_316", 20, 120, None, 2020, 240000,  "EUR", "Vertical KO drum"),
    ("heat_exchanger", "Shell & tube",         120,  "m2",    8500, "stainless_steel_304", 16, 250, None, 2019, 180000,  "EUR", "S&T HX 120m2"),
    ("heat_exchanger", "Plate",                80,   "m2",    2500, "stainless_steel_316", 10, 150, None, 2020, 120000,  "EUR", "Plate HX"),
    ("storage_tank",   "Atmospheric",          500,  "m3",   35000, "carbon_steel",        1,  50,  None, 2016, 210000,  "EUR", "Atm tank 500m3"),
    ("storage_tank",   "Pressurized",          200,  "m3",   28000, "carbon_steel",        6,  80,  None, 2019, 340000,  "EUR", "Pressurized tank"),
    ("pump",           "Centrifugal",          80,   "m3/h",  1200, "stainless_steel_316", 10, 120, 55,   2020, 42000,   "EUR", "Centrifugal pump 55kW"),
    ("pump",           "Centrifugal",          150,  "m3/h",  1800, "stainless_steel_316", 15, 150, 110,  2021, 78000,   "EUR", "Centrifugal pump 110kW"),
    ("compressor",     "Centrifugal",          8000, "m3/h",  12000,"carbon_steel",       25, 180, 450,  2020, 950000,  "EUR", "Centrifugal compressor"),
    ("valve",          "Control",              100,  "mm",     50,  "stainless_steel_316", 20, 150, None, 2020, 6500,    "EUR", "DN100 control valve"),
    ("instrumentation","Pressure transmitter", 1,    "unit",   2,   "stainless_steel_316", 40, 80,  None, 2021, 1800,    "EUR", "PT smart"),
]

DUMMY_ROWS = [
    # tag, category, subtype, size, unit, weight_kg, material, P, T, power, qty
    ("C-101", "column",         "Distillation packed",  50,   "m3",    36000, "stainless_steel_316", 10, 170, None, 1),
    ("R-201", "reactor",        "CSTR",                 30,   "m3",    32000, "stainless_steel_316", 20, 210, None, 1),
    ("E-301", "heat_exchanger", "Shell & tube",         150,  "m2",     9500, "stainless_steel_304", 15, 240, None, 2),
    ("T-401", "storage_tank",   "Atmospheric",          600,  "m3",    38000, "carbon_steel",        1,  50,  None, 3),
    ("P-501", "pump",           "Centrifugal",          100,  "m3/h",   None, "stainless_steel_316", 12, 130, 75,   4),
    ("K-601", "compressor",     "Centrifugal",          10000,"m3/h",   None, "carbon_steel",        22, 170, 600,  1),
    ("V-701", "valve",          "Control",              100,  "mm",     None, "stainless_steel_316", 20, 150, None, 25),
    ("I-801", "instrumentation","Pressure transmitter", 1,    "unit",   None, "stainless_steel_316", 40, 80,  None, 40),
]

async def seed_data():
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
            doc = obj.model_dump(); doc["created_at"] = doc["created_at"].isoformat()
            await db.equipment_historical.insert_one(doc)

    proj_count = await db.projects.count_documents({})
    if proj_count == 0:
        logging.info("Seeding dummy project...")
        proj = Project(name="DUMMY - Petrochemical Unit",
                       description="Sample project pre-populated for testing",
                       output_currency="EUR",
                       target_year=datetime.now(timezone.utc).year,
                       aace_class="Class 5")
        pdoc = proj.model_dump(); pdoc["created_at"] = pdoc["created_at"].isoformat()
        await db.projects.insert_one(pdoc)
        for r in DUMMY_ROWS:
            (tag, cat, sub, size, unit, w, mat, p, t, pw, qty) = r
            data = {
                "tag": tag, "category": cat, "subtype": sub, "size": size, "size_unit": unit,
                "weight_kg": w, "material": mat,
                "design_pressure_bar": p, "design_temperature_c": t,
                "power_kw": pw, "quantity": qty,
            }
            data = _sanitize_row_payload(data)
            est = await _compute_row_estimate(pdoc, data)
            row_obj = EquipmentRow(project_id=proj.id, **data, **est)
            rdoc = row_obj.model_dump(); rdoc["created_at"] = rdoc["created_at"].isoformat()
            await db.equipment_rows.insert_one(rdoc)

# ============================================================
# APP SETUP
# ============================================================
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"], allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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
