"""
EPC Equipment Parametric Cost Estimation - Backend v3 (weighted_similarity_v3)

Key changes vs v2:
- Rigid category + subtype filter (no fallback to category-only)
- Controlled subtypes per category
- New "burner" category
- Range from weighted SAMPLE std (configurable confidence level z), NOT AACE
- IQR outlier removal on adjusted costs (configurable multiplier)
- Weights renormalized AFTER outlier removal
- Pump multivariate scaling F_pump = F_Q * F_H * F_P (Q & H mandatory, P policy)
- Pump similarity on Q, H, P (subtype removed from similarity)
- Project range from aggregated sigma with rho_quantity + rho_between_rows
- Human-readable "How the estimate was calculated" report
"""
from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import re
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

MODEL_VERSION = "weighted_similarity_v3"

app = FastAPI(title="EPC Cost Estimator", version="3.0")
api_router = APIRouter(prefix="/api")

# ============================================================
# CATEGORIES / SUBTYPES / META
# ============================================================
CATEGORIES = [
    "column", "reactor", "vessel", "heat_exchanger", "storage_tank",
    "pump", "compressor", "valve", "instrumentation", "burner", "other",
]

CATEGORY_SUBTYPES: Dict[str, List[str]] = {
    "column":          ["Tray", "Packed"],
    "reactor":         ["CSTR", "PFR"],
    "vessel":          ["2-Phase", "3-Phase"],
    "storage_tank":    ["Fixed Roof", "Floating Roof"],
    "heat_exchanger":  ["Shell and Tube", "Reboiler", "Air Cooler"],
    "pump":            ["Centrifugal", "Positive Displacement"],
    "compressor":      ["Centrifugal", "Reciprocating"],
    "valve":           ["Ball", "Gate", "Globe", "Butterfly", "Check", "PSV", "TRV", "SDV"],
    "instrumentation": ["General", "Flow", "Level", "Temperature", "Pressure", "Analyzer"],
    "burner":          ["Process Burner", "Boiler Burner", "Duct Burner", "Flare Burner"],
    "other":           ["User Defined"],
}

CATEGORY_META = {
    "column": {"label": "Distillation Column", "primary_variable": "weight_kg", "primary_unit_si": "kg",
        "fallback_variable": "size", "fallback_unit_si": "m³", "size_unit_symbol": "m³", "size_unit": "m3",
        "default_n": 0.65, "steel_w": 0.80, "oil_w": 0.20,
        "pressure_exp_default": 0.60, "pressure_enabled_default": True, "show_power": False,
        "allowed_fields": ["weight_kg", "size", "design_pressure_bar", "design_temperature_c", "material", "subtype"]},
    "reactor": {"label": "Reactor", "primary_variable": "weight_kg", "primary_unit_si": "kg",
        "fallback_variable": "size", "fallback_unit_si": "m³", "size_unit_symbol": "m³", "size_unit": "m3",
        "default_n": 0.65, "steel_w": 0.80, "oil_w": 0.20,
        "pressure_exp_default": 0.60, "pressure_enabled_default": True, "show_power": False,
        "allowed_fields": ["weight_kg", "size", "design_pressure_bar", "design_temperature_c", "material", "subtype"]},
    "vessel": {"label": "Vessel", "primary_variable": "weight_kg", "primary_unit_si": "kg",
        "fallback_variable": "size", "fallback_unit_si": "m³", "size_unit_symbol": "m³", "size_unit": "m3",
        "default_n": 0.62, "steel_w": 0.80, "oil_w": 0.20,
        "pressure_exp_default": 0.55, "pressure_enabled_default": True, "show_power": False,
        "allowed_fields": ["weight_kg", "size", "design_pressure_bar", "design_temperature_c", "material", "subtype"]},
    "storage_tank": {"label": "Storage Tank", "primary_variable": "weight_kg", "primary_unit_si": "kg",
        "fallback_variable": "size", "fallback_unit_si": "m³", "size_unit_symbol": "m³", "size_unit": "m3",
        "default_n": 0.62, "steel_w": 0.80, "oil_w": 0.20,
        "pressure_exp_default": 0.50, "pressure_enabled_default": True, "show_power": False,
        "allowed_fields": ["weight_kg", "size", "design_pressure_bar", "design_temperature_c", "material", "subtype"]},
    "heat_exchanger": {"label": "Heat Exchanger", "primary_variable": "weight_kg", "primary_unit_si": "kg",
        "fallback_variable": "size", "fallback_unit_si": "m²", "size_unit_symbol": "m²", "size_unit": "m2",
        "default_n": 0.65, "steel_w": 0.80, "oil_w": 0.20,
        "pressure_exp_default": 0.50, "pressure_enabled_default": True, "show_power": False,
        "allowed_fields": ["weight_kg", "size", "design_pressure_bar", "design_temperature_c", "material", "subtype"]},
    "pump": {"label": "Pump", "primary_variable": "flow_rate_m3_h", "primary_unit_si": "m³/h",
        "fallback_variable": None, "fallback_unit_si": None,
        "size_unit_symbol": "m³/h", "size_unit": "m3/h",
        "default_n": 0.60, "steel_w": 0.40, "oil_w": 0.60,
        # Pressure factor DISABLED for pump - head is captured in F_H
        "pressure_exp_default": 0.0, "pressure_enabled_default": False, "show_power": True,
        "allowed_fields": ["flow_rate_m3_h", "head_m", "power_kw", "pump_efficiency", "fluid_density_kg_m3", "size", "material", "subtype"]},
    "compressor": {"label": "Compressor", "primary_variable": "power_kw", "primary_unit_si": "kW",
        "fallback_variable": "size", "fallback_unit_si": "m³/h", "size_unit_symbol": "m³/h", "size_unit": "m3/h",
        "default_n": 0.75, "steel_w": 0.40, "oil_w": 0.60,
        "pressure_exp_default": 0.0, "pressure_enabled_default": False, "show_power": True,
        "allowed_fields": ["power_kw", "size", "design_pressure_bar", "material", "subtype", "weight_kg"]},
    "valve": {"label": "Valve", "primary_variable": "size", "primary_unit_si": "mm",
        "fallback_variable": None, "fallback_unit_si": None,
        "size_unit_symbol": "mm", "size_unit": "mm",
        "default_n": 0.40, "steel_w": 0.60, "oil_w": 0.40,
        "pressure_exp_default": 0.30, "pressure_enabled_default": True, "show_power": False,
        "allowed_fields": ["size", "design_pressure_bar", "design_temperature_c", "material", "subtype"]},
    "instrumentation": {"label": "Instrumentation", "primary_variable": "size", "primary_unit_si": "unit",
        "fallback_variable": None, "fallback_unit_si": None,
        "size_unit_symbol": "unit", "size_unit": "unit",
        "default_n": 0.30, "steel_w": 0.60, "oil_w": 0.40,
        "pressure_exp_default": 0.0, "pressure_enabled_default": False, "show_power": False,
        "allowed_fields": ["size", "material", "subtype"]},
    "burner": {"label": "Burner", "primary_variable": "thermal_duty_kw", "primary_unit_si": "kW",
        "fallback_variable": None, "fallback_unit_si": None,
        "size_unit_symbol": "kW", "size_unit": "kW",
        "default_n": 0.70, "steel_w": 0.50, "oil_w": 0.50,
        "pressure_exp_default": 0.0, "pressure_enabled_default": False, "show_power": True,
        "allowed_fields": ["thermal_duty_kw", "fuel_flow_kg_h", "power_kw", "size", "design_temperature_c", "material", "subtype"]},
    "other": {"label": "Other", "primary_variable": "size", "primary_unit_si": "unit",
        "fallback_variable": None, "fallback_unit_si": None, "size_unit_symbol": "unit", "size_unit": "unit",
        "default_n": 0.60, "steel_w": 0.70, "oil_w": 0.30,
        "pressure_exp_default": 0.30, "pressure_enabled_default": False, "show_power": False,
        "allowed_fields": ["size", "material", "subtype", "weight_kg", "power_kw", "design_pressure_bar", "design_temperature_c"]},
}

MATERIALS = ["carbon_steel", "stainless_steel_304", "stainless_steel_316", "duplex", "alloy", "other"]

MATERIAL_FACTOR_DEFAULTS = {
    "carbon_steel":         {"factor": 1.00, "source": "reference material",        "notes": "Reference material (F=1.0)"},
    "stainless_steel_304":  {"factor": 1.70, "source": "preliminary configurable", "notes": "To be calibrated"},
    "stainless_steel_316":  {"factor": 2.10, "source": "preliminary configurable", "notes": "To be calibrated"},
    "duplex":               {"factor": 3.00, "source": "preliminary configurable", "notes": "To be calibrated"},
    "alloy":                {"factor": 4.50, "source": "preliminary configurable", "notes": "To be calibrated"},
    "other":                {"factor": 1.50, "source": "preliminary configurable", "notes": "Unknown material - to be reviewed"},
}
REFERENCE_MATERIAL = "carbon_steel"

# Z-values for standard confidence levels (two-sided, normal distribution)
CONFIDENCE_Z = {
    "68.27": 1.000, "80.00": 1.282, "90.00": 1.645, "95.00": 1.960, "99.00": 2.576,
}

# Pump default exponents (preliminary configurable defaults)
PUMP_DEFAULTS = {
    "Centrifugal":           {"a": 0.30, "b": 0.20, "c": 0.30},
    "Positive Displacement": {"a": 0.45, "b": 0.10, "c": 0.20},
}

SIMILARITY_DEFAULTS = {
    "alpha": 1.0,             # size distance decay
    "beta": 0.5,              # material distance decay
    "gamma": 0.5,             # pressure distance decay
    "w_size": 0.70,
    "w_material": 0.20,
    "w_pressure": 0.10,       # w_subtype removed - hard filter makes it redundant
    "min_similarity": 0.10,
    "max_references": 20,
    "min_references": 1,
    "max_extrapolation_ratio": 5.0,
    "atmospheric_pressure_bar": 1.01325,
    "missing_material_factor_policy": "exclude",
    "missing_pressure_policy": "exclude",
    # Reliability range
    "confidence_level": "90.00",
    "z_value": 1.645,
    "range_method": "weighted_mean_plus_minus_z_sigma",
    # Outlier
    "outlier_filter_enabled": True,
    "iqr_multiplier": 1.5,
    "minimum_references_for_iqr": 4,
    # Pump
    "pump_alpha_Q": 1.0, "pump_alpha_H": 1.0, "pump_alpha_P": 1.0,
    "pump_w_Q": 0.5, "pump_w_H": 0.3, "pump_w_P": 0.2,
    "pump_duty_weight": 0.80, "pump_material_weight": 0.20,
    "pump_power_missing_policy": "optional_and_renormalize",  # required / optional_and_renormalize / ignored
    "pump_exponent_renormalization": False,
    # Project uncertainty
    "rho_quantity": 1.0,
    "rho_between_rows": 0.0,
    "project_missing_sigma_policy": "partial_with_warning",  # or "block_project_range"
}

# ============================================================
# SUBTYPE MIGRATION MAP
# ============================================================
SUBTYPE_MIGRATION = {
    "column": {"distillation tray": "Tray", "tray": "Tray",
               "distillation packed": "Packed", "packed": "Packed"},
    "reactor": {"cstr": "CSTR", "pfr": "PFR", "pressure vessel": None},
    "vessel": {"horizontal separator": "3-Phase", "vertical ko drum": "2-Phase",
               "2-phase": "2-Phase", "3-phase": "3-Phase"},
    "storage_tank": {"atmospheric": "Fixed Roof", "fixed roof": "Fixed Roof",
                     "floating roof": "Floating Roof", "pressurized": None},
    "heat_exchanger": {"shell & tube": "Shell and Tube", "shell and tube": "Shell and Tube",
                       "plate": None, "reboiler": "Reboiler", "air cooler": "Air Cooler"},
    "pump": {"centrifugal": "Centrifugal", "centrifugal pump": "Centrifugal",
             "positive displacement": "Positive Displacement"},
    "compressor": {"centrifugal": "Centrifugal", "reciprocating": "Reciprocating"},
    "valve": {"ball": "Ball", "gate": "Gate", "globe": "Globe", "butterfly": "Butterfly",
              "check": "Check", "psv": "PSV", "trv": "TRV", "sdv": "SDV", "control": None},
    "instrumentation": {"general": "General", "flow": "Flow", "level": "Level",
                        "temperature": "Temperature", "pressure": "Pressure",
                        "analyzer": "Analyzer", "pressure transmitter": "Pressure"},
    "burner": {"process burner": "Process Burner", "boiler burner": "Boiler Burner",
               "duct burner": "Duct Burner", "flare burner": "Flare Burner"},
    "other": {"user defined": "User Defined"},
}

def canonical_subtype(category: str, raw: Optional[str]) -> Optional[str]:
    """Return the canonical subtype for a category or None if not mappable."""
    if not raw:
        return None
    allowed = CATEGORY_SUBTYPES.get(category, [])
    for a in allowed:
        if a.lower() == str(raw).strip().lower():
            return a
    mapping = SUBTYPE_MIGRATION.get(category, {})
    return mapping.get(str(raw).strip().lower())

def validate_subtype(category: str, subtype: str) -> str:
    """Return canonical subtype or raise HTTPException(400/422).
    Strict: only exact (case-insensitive) matches against CATEGORY_SUBTYPES are accepted.
    Legacy migration is handled separately via /api/equipment/migrate-subtypes."""
    if not subtype:
        raise HTTPException(422, "subtype is required")
    allowed = CATEGORY_SUBTYPES.get(category)
    if not allowed:
        raise HTTPException(400, f"category '{category}' has no subtypes defined")
    for a in allowed:
        if a.lower() == str(subtype).strip().lower():
            return a
    raise HTTPException(400, f"subtype '{subtype}' is not allowed for category '{category}'. Allowed: {allowed}")

# ============================================================
# MODELS
# ============================================================
class HistoricalEquipment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    category: str
    subtype: str
    size: float
    size_unit: str
    weight_kg: Optional[float] = None
    material: str
    design_pressure_bar: Optional[float] = None
    design_temperature_c: Optional[float] = None
    power_kw: Optional[float] = None
    # Pump-specific
    flow_rate_m3_h: Optional[float] = None
    head_m: Optional[float] = None
    pump_efficiency: Optional[float] = None
    fluid_density_kg_m3: Optional[float] = None
    # Burner-specific
    thermal_duty_kw: Optional[float] = None
    fuel_flow_kg_h: Optional[float] = None
    year: int
    cost_original: float
    currency: Literal["EUR", "USD"]
    vendor_country: Optional[str] = None
    install_country: Optional[str] = None
    notes: Optional[str] = None
    subtype_migration_required: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class HistoricalEquipmentCreate(BaseModel):
    category: str
    subtype: str
    size: float = Field(gt=0)
    size_unit: Optional[str] = None
    weight_kg: Optional[float] = Field(default=None, gt=0)
    material: str
    design_pressure_bar: Optional[float] = None
    design_temperature_c: Optional[float] = None
    power_kw: Optional[float] = Field(default=None, gt=0)
    flow_rate_m3_h: Optional[float] = Field(default=None, gt=0)
    head_m: Optional[float] = Field(default=None, gt=0)
    pump_efficiency: Optional[float] = Field(default=None, gt=0, le=1)
    fluid_density_kg_m3: Optional[float] = Field(default=None, gt=0)
    thermal_duty_kw: Optional[float] = Field(default=None, gt=0)
    fuel_flow_kg_h: Optional[float] = Field(default=None, gt=0)
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
    subtype: str
    size: float
    size_unit: str
    weight_kg: Optional[float] = None
    material: str
    design_pressure_bar: Optional[float] = None
    design_temperature_c: Optional[float] = None
    power_kw: Optional[float] = None
    flow_rate_m3_h: Optional[float] = None
    head_m: Optional[float] = None
    pump_efficiency: Optional[float] = None
    fluid_density_kg_m3: Optional[float] = None
    thermal_duty_kw: Optional[float] = None
    fuel_flow_kg_h: Optional[float] = None
    quantity: int = 1
    reference_ids: Optional[List[str]] = None
    # results
    unit_expected_cost: Optional[float] = 0.0
    unit_low: Optional[float] = None
    unit_high: Optional[float] = None
    unit_sigma: Optional[float] = None
    total_expected_cost: float = 0.0
    total_sigma: Optional[float] = None
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
    pump_scaling_summary: Optional[Dict[str, Any]] = None
    similarity_summary: Optional[Dict[str, Any]] = None
    estimation_breakdown: Optional[Dict[str, Any]] = None
    outlier_summary: Optional[Dict[str, Any]] = None
    references_detail: Optional[List[Dict[str, Any]]] = None
    references_excluded: Optional[List[Dict[str, Any]]] = None
    warnings: Optional[List[str]] = None
    errors: Optional[List[str]] = None
    calculation_report: Optional[Dict[str, Any]] = None
    estimate_available: bool = False
    model_version: str = MODEL_VERSION
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class EquipmentRowCreate(BaseModel):
    tag: Optional[str] = None
    category: str
    subtype: str
    size: Optional[float] = Field(default=None, gt=0)
    size_unit: Optional[str] = None
    weight_kg: Optional[float] = Field(default=None, gt=0)
    material: str
    design_pressure_bar: Optional[float] = None
    design_temperature_c: Optional[float] = None
    power_kw: Optional[float] = Field(default=None, gt=0)
    flow_rate_m3_h: Optional[float] = Field(default=None, gt=0)
    head_m: Optional[float] = Field(default=None, gt=0)
    pump_efficiency: Optional[float] = Field(default=None, gt=0, le=1)
    fluid_density_kg_m3: Optional[float] = Field(default=None, gt=0)
    thermal_duty_kw: Optional[float] = Field(default=None, gt=0)
    fuel_flow_kg_h: Optional[float] = Field(default=None, gt=0)
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

class PumpScalingConfig(BaseModel):
    subtype: str
    a: float = Field(ge=0)
    b: float = Field(ge=0)
    c: float = Field(ge=0)
    source: Optional[str] = None
    notes: Optional[str] = None

class SimilarityConfig(BaseModel):
    alpha: float
    beta: float
    gamma: float
    w_size: float
    w_material: float
    w_pressure: float
    min_similarity: float
    max_references: int
    min_references: int
    max_extrapolation_ratio: float
    atmospheric_pressure_bar: float
    missing_material_factor_policy: Literal["exclude", "block"] = "exclude"
    missing_pressure_policy: Literal["exclude", "block"] = "exclude"
    confidence_level: Literal["68.27", "80.00", "90.00", "95.00", "99.00"] = "90.00"
    outlier_filter_enabled: bool = True
    iqr_multiplier: float = 1.5
    minimum_references_for_iqr: int = 4
    pump_alpha_Q: float = 1.0
    pump_alpha_H: float = 1.0
    pump_alpha_P: float = 1.0
    pump_w_Q: float = 0.5
    pump_w_H: float = 0.3
    pump_w_P: float = 0.2
    pump_duty_weight: float = 0.80
    pump_material_weight: float = 0.20
    pump_power_missing_policy: Literal["required", "optional_and_renormalize", "ignored"] = "optional_and_renormalize"
    pump_exponent_renormalization: bool = False
    rho_quantity: float = 1.0
    rho_between_rows: float = 0.0
    project_missing_sigma_policy: Literal["partial_with_warning", "block_project_range"] = "partial_with_warning"

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
    default = {"category": category, "pressure_exponent": meta["pressure_exp_default"],
        "enabled": meta["pressure_enabled_default"],
        "minimum_factor": None, "maximum_factor": None,
        "source": "preliminary configurable defaults",
        "notes": "to be calibrated on company historical data"}
    if doc:
        default.update(doc)
    return default

async def get_pump_config(subtype: str) -> Dict[str, Any]:
    doc = await db.pump_configs.find_one({"subtype": subtype}, {"_id": 0})
    defaults = PUMP_DEFAULTS.get(subtype, {"a": 0.30, "b": 0.20, "c": 0.30})
    out = {"subtype": subtype, **defaults, "source": "preliminary configurable defaults",
           "notes": "to be calibrated on company historical data"}
    if doc:
        out.update(doc)
    return out

async def get_similarity_config() -> Dict[str, Any]:
    doc = await db.similarity_config.find_one({"_id": "singleton"}, {"_id": 0})
    cfg = dict(SIMILARITY_DEFAULTS)
    if doc:
        # whitelist v3 keys only - ignore stale v2 fields like w_subtype/subtype_mismatch
        allowed_keys = set(SIMILARITY_DEFAULTS.keys()) | {"z_value", "updated_at"}
        cfg.update({k: v for k, v in doc.items() if k in allowed_keys})
    z = CONFIDENCE_Z.get(str(cfg.get("confidence_level", "90.00")), 1.645)
    cfg["z_value"] = z
    return cfg

# ============================================================
# EXTERNAL INDICES (FRED) with in-process cache
# ============================================================
FALLBACK_STEEL = {y: v for y, v in zip(range(2005, 2027),
    [88, 96, 106, 128, 90, 108, 128, 118, 112, 111, 100, 96, 108, 128, 118, 114, 190, 220, 178, 172, 176, 180])}
FALLBACK_OIL = {y: v for y, v in zip(range(2005, 2027),
    [54, 65, 72, 97, 62, 80, 111, 112, 109, 99, 52, 44, 54, 71, 64, 42, 71, 100, 82, 80, 78, 78])}

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
        steel, oil = await asyncio.gather(fetch_fred_annual("WPU101706"), fetch_fred_annual("DCOILBRENTEU"))
        source = "FRED"
        if not steel: steel = FALLBACK_STEEL; source = "fallback"
        if not oil:   oil   = FALLBACK_OIL;   source = "fallback"
        _indices_cache.update({"steel": steel, "oil": oil, "ts": now, "source": source})
        return steel, oil, source

def _nearest_year_value(series: dict, year: int) -> float:
    if year in series: return series[year]
    years = sorted(series.keys())
    if not years: return 100.0
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
# FX
# ============================================================
_fx_cache: Dict[str, float] = {}

async def fx_rate(base: str, target: str, date: Optional[str] = None) -> Tuple[float, bool]:
    if base == target: return 1.0, False
    date_key = date or "latest"
    key = f"{base}-{target}-{date_key}"
    if key in _fx_cache: return _fx_cache[key], False
    url = f"https://api.frankfurter.dev/v1/{date_key}"
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(url, params={"base": base, "symbols": target}); r.raise_for_status()
            data = r.json()
        rate = float(data["rates"][target]); _fx_cache[key] = rate; return rate, False
    except Exception as e:
        logging.warning(f"FX fetch failed {base}->{target} {date_key}: {e}")
        return (1.08 if base == "EUR" and target == "USD" else 0.92), True

async def batch_fx_rates(pairs):
    unique = list(set(pairs))
    async def one(p):
        base, target, year = p
        date = f"{year}-06-15" if year else None
        rate, fb = await fx_rate(base, target, date)
        return p, rate, fb
    results = await asyncio.gather(*[one(p) for p in unique])
    return {p: (r, f) for p, r, f in results}

# ============================================================
# SCALING VARIABLE / IQR / STATS UTILITIES
# ============================================================
def get_scaling_variable(category: str, record: Dict[str, Any], force_use_fallback: bool = False) -> Optional[Dict[str, Any]]:
    meta = CATEGORY_META.get(category)
    if not meta: return None
    pv = meta["primary_variable"]
    fv = meta["fallback_variable"]

    def val(field):
        v = record.get(field)
        try: v = float(v) if v is not None else None
        except (TypeError, ValueError): v = None
        return v if (v is not None and v > 0) else None

    if not force_use_fallback:
        if pv == "weight_kg":
            w = val("weight_kg")
            if w is not None: return {"name": "weight_kg", "value": w, "unit": "kg", "is_fallback": False, "fallback_reason": None}
        elif pv == "power_kw":
            p = val("power_kw")
            if p is not None: return {"name": "power_kw", "value": p, "unit": "kW", "is_fallback": False, "fallback_reason": None}
        elif pv == "flow_rate_m3_h":
            q = val("flow_rate_m3_h")
            if q is not None: return {"name": "flow_rate_m3_h", "value": q, "unit": "m³/h", "is_fallback": False, "fallback_reason": None}
        elif pv == "thermal_duty_kw":
            d = val("thermal_duty_kw")
            if d is not None: return {"name": "thermal_duty_kw", "value": d, "unit": "kW", "is_fallback": False, "fallback_reason": None}
        elif pv == "size":
            s = val("size")
            if s is not None: return {"name": "size", "value": s, "unit": meta["primary_unit_si"], "is_fallback": False, "fallback_reason": None}

    if fv is None: return None
    if fv == "size":
        s = val("size")
        if s is not None:
            return {"name": "size", "value": s, "unit": meta["fallback_unit_si"], "is_fallback": True,
                    "fallback_reason": f"{pv} unavailable, using {meta['fallback_unit_si']}"}
    return None

def _quantile_linear(values: List[float], p: float) -> float:
    """NumPy-linear quantile method for a sorted list."""
    if not values: raise ValueError("empty values")
    xs = sorted(values); n = len(xs)
    if n == 1: return xs[0]
    idx = p * (n - 1)
    lo = math.floor(idx); hi = math.ceil(idx)
    if lo == hi: return xs[int(idx)]
    frac = idx - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac

def _iqr_filter(costs: List[float], k: float) -> Dict[str, Any]:
    """Return {q1, q3, iqr, lower, upper, outlier_indices}."""
    q1 = _quantile_linear(costs, 0.25)
    q3 = _quantile_linear(costs, 0.75)
    iqr = q3 - q1
    lower = q1 - k * iqr
    upper = q3 + k * iqr
    idx = [i for i, c in enumerate(costs) if c < lower or c > upper]
    return {"q1": q1, "q3": q3, "iqr": iqr, "lower": lower, "upper": upper, "outlier_indices": idx}

def weighted_stats(costs: List[float], weights: List[float]) -> Dict[str, Optional[float]]:
    """Compute weighted mean, population sigma, unbiased sample sigma, Neff.
    Weights must be positive; will be normalized to sum=1 internally."""
    if not costs: return {"mean": None, "sigma_population": None, "sigma_sample": None, "n_eff": 0.0}
    tot = sum(weights)
    if tot <= 0: return {"mean": None, "sigma_population": None, "sigma_sample": None, "n_eff": 0.0}
    w = [wi / tot for wi in weights]
    mean = sum(wi * ci for wi, ci in zip(w, costs))
    var_pop = sum(wi * (ci - mean) ** 2 for wi, ci in zip(w, costs))
    sig_pop = math.sqrt(max(var_pop, 0.0))
    sw2 = sum(wi ** 2 for wi in w)
    denom = 1.0 - sw2
    sig_sample: Optional[float] = None
    if len(costs) >= 2 and denom > 1e-12:
        var_sample = var_pop / denom
        sig_sample = math.sqrt(max(var_sample, 0.0))
    n_eff = 1.0 / sw2 if sw2 > 0 else 0.0
    return {"mean": mean, "sigma_population": sig_pop, "sigma_sample": sig_sample, "n_eff": n_eff}

# ============================================================
# CORE ESTIMATION
# ============================================================
def _classify_confidence(n_eff: float) -> str:
    if n_eff >= 4: return "High"
    if n_eff >= 2: return "Medium"
    return "Low"

def _unavailable(errors, warnings, candidates=None, excluded=None, category=None, subtype=None):
    return {
        "estimate_available": False,
        "expected": None, "low": None, "high": None,
        "sigma_population": None, "sigma_sample": None, "sigma_used_for_range": None,
        "candidate_references": len(candidates) if candidates else 0,
        "references_used": 0, "effective_sample_size": 0.0,
        "scaling_variable": None, "scaling_variable_value": None,
        "scaling_variable_unit": None, "scaling_variable_is_fallback": False,
        "material_factor_summary": None, "pressure_factor_summary": None,
        "pump_scaling_summary": None,
        "similarity_summary": None, "outlier_summary": None,
        "references_detail": [], "references_excluded": excluded or [],
        "estimation_breakdown": None, "calculation_report": None,
        "warnings": list(dict.fromkeys(warnings or [])), "errors": errors or [],
        "escalation_factor": 0.0,
        "quantity": 1,
        "total_expected": None, "total_low": None, "total_high": None, "total_sigma": None,
        "category": category, "subtype": subtype,
        "confidence_level": None, "z_value": None,
        "range_method": "weighted_mean_plus_minus_z_sigma",
        "calculation_method": None, "calculation_formula": None,
        "model_version": MODEL_VERSION,
    }

async def estimate_full(
    *, category: str, target_size: Optional[float], target_weight_kg: Optional[float],
    target_power_kw: Optional[float], target_material: str, target_pressure_barg: Optional[float],
    subtype: Optional[str], target_year: int, output_currency: str,
    target_flow_rate: Optional[float] = None, target_head: Optional[float] = None,
    target_thermal_duty: Optional[float] = None,
    reference_ids: Optional[List[str]] = None, quantity: int = 1,
) -> Dict[str, Any]:
    warnings: List[str] = []; errors: List[str] = []
    meta = CATEGORY_META.get(category)
    if not meta:
        return _unavailable([f"unknown category {category}"], warnings, category=category, subtype=subtype)

    # Canonical subtype (required)
    if not subtype:
        return _unavailable(["subtype is required"], warnings, category=category, subtype=subtype)
    canonical_st = canonical_subtype(category, subtype)
    if canonical_st is None or canonical_st not in CATEGORY_SUBTYPES.get(category, []):
        return _unavailable([f"subtype '{subtype}' not allowed for category '{category}'"], warnings, category=category, subtype=subtype)
    subtype = canonical_st

    # Pump-specific requirements: Q and H mandatory (checked BEFORE generic primary-variable guard)
    if category == "pump":
        if not target_flow_rate or target_flow_rate <= 0:
            return _unavailable(["pump target flow_rate_m3_h is required"], warnings, category=category, subtype=subtype)
        if not target_head or target_head <= 0:
            return _unavailable(["pump target head_m is required"], warnings, category=category, subtype=subtype)

    # Target scaling variable
    target_record = {"size": target_size, "weight_kg": target_weight_kg, "power_kw": target_power_kw,
                     "flow_rate_m3_h": target_flow_rate, "thermal_duty_kw": target_thermal_duty}
    target_sv = get_scaling_variable(category, target_record)
    if not target_sv:
        return _unavailable([f"target primary variable ({meta['primary_variable']}) unavailable"], warnings, category=category, subtype=subtype)
    if target_sv["is_fallback"]:
        warnings.append(f"Fallback variable used for target: {target_sv['fallback_reason']}")

    # Load config
    n_exp = await get_scale_exponent(category)
    steel_w, oil_w = await get_escalation_weights(category)
    mfs = await get_material_factors_map()
    pset = await get_pressure_setting(category)
    sim = await get_similarity_config()
    atm = float(sim["atmospheric_pressure_bar"])
    z = float(sim["z_value"]); conf = str(sim["confidence_level"])
    steel, oil, idx_src = await get_indices()
    if idx_src != "FRED":
        warnings.append("Escalation indices are using fallback data (FRED unavailable)")

    # Pump config (if applicable)
    pump_cfg = await get_pump_config(subtype) if category == "pump" else None

    # Target absolute pressure
    p_target_abs = None
    if target_pressure_barg is not None:
        try:
            p_target_abs = float(target_pressure_barg) + atm
            if p_target_abs <= 0: p_target_abs = None
        except (TypeError, ValueError):
            p_target_abs = None

    target_mf_doc = mfs.get(target_material)
    if not target_mf_doc:
        errors.append(f"Material factor for target material '{target_material}' not configured")
        return _unavailable(errors, warnings, category=category, subtype=subtype)
    target_mf = float(target_mf_doc["factor"])

    # ---- Fetch candidates with RIGID category+subtype filter ----
    q: Dict[str, Any] = {"category": category, "subtype": subtype}
    manual_refs = None
    if reference_ids:
        manual_refs = await db.equipment_historical.find({"id": {"$in": reference_ids}}, {"_id": 0}).to_list(1000)
    candidates = manual_refs if manual_refs is not None else await db.equipment_historical.find(q, {"_id": 0}).to_list(1000)
    if not candidates:
        return _unavailable(
            ["No historical references available for the selected category and subtype"],
            warnings, category=category, subtype=subtype,
        )

    fx_pairs = [(r["currency"], output_currency, int(r["year"])) for r in candidates if r.get("currency") and r.get("year")]
    fx_map = await batch_fx_rates(fx_pairs)

    used = []
    excluded = []

    for ref in candidates:
        ref_id = ref.get("id")
        # Enforce rigid subtype match, even for manually-supplied refs
        if ref.get("category") != category:
            excluded.append({"historical_equipment_id": ref_id, "exclusion_reason": f"category mismatch (ref={ref.get('category')}, target={category})", "similarity": None})
            continue
        if ref.get("subtype") != subtype:
            excluded.append({"historical_equipment_id": ref_id, "exclusion_reason": f"subtype mismatch (ref={ref.get('subtype')}, target={subtype})", "similarity": None})
            continue

        rec = {"size": ref.get("size"), "weight_kg": ref.get("weight_kg"), "power_kw": ref.get("power_kw"),
               "flow_rate_m3_h": ref.get("flow_rate_m3_h"), "thermal_duty_kw": ref.get("thermal_duty_kw")}
        ref_sv = get_scaling_variable(category, rec, force_use_fallback=target_sv["is_fallback"])
        if not ref_sv or ref_sv["name"] != target_sv["name"]:
            excluded.append({"historical_equipment_id": ref_id,
                "exclusion_reason": "incompatible scaling variable",
                "available_values": rec, "similarity": None})
            continue

        # ---- Size scaling ----
        pump_breakdown = None
        if category == "pump":
            # Multivariate: F_pump = F_Q * F_H * F_P
            q_r = ref.get("flow_rate_m3_h")
            h_r = ref.get("head_m")
            if not q_r or q_r <= 0 or not h_r or h_r <= 0:
                excluded.append({"historical_equipment_id": ref_id, "exclusion_reason": "Missing pump flow rate or head", "available_values": rec, "similarity": None})
                continue
            a = float(pump_cfg["a"]); b_e = float(pump_cfg["b"]); c_e = float(pump_cfg["c"])
            F_flow = (target_flow_rate / q_r) ** a
            F_head = (target_head / h_r) ** b_e
            # Power term policy
            power_policy = sim["pump_power_missing_policy"]
            p_r = ref.get("power_kw"); p_t = target_power_kw
            power_used = False; F_power = 1.0
            renorm_note = None
            if p_r and p_t and p_r > 0 and p_t > 0:
                F_power = (p_t / p_r) ** c_e
                power_used = True
            else:
                if power_policy == "required":
                    excluded.append({"historical_equipment_id": ref_id, "exclusion_reason": "pump power required by policy", "similarity": None})
                    continue
                warn_msg = "Power term excluded because comparable power data are unavailable"
                if warn_msg not in warnings: warnings.append(warn_msg)
                if power_policy == "ignored":
                    F_power = 1.0
                elif power_policy == "optional_and_renormalize" and sim["pump_exponent_renormalization"]:
                    # rescale a, b to preserve sum
                    total_e = a + b_e + c_e
                    if (a + b_e) > 0:
                        scale = total_e / (a + b_e)
                        F_flow = (target_flow_rate / q_r) ** (a * scale)
                        F_head = (target_head / h_r) ** (b_e * scale)
                        renorm_note = f"exponents renormalized a→{a*scale:.3f}, b→{b_e*scale:.3f}"
            f_size = F_flow * F_head * F_power
            c_after_size = float(ref["cost_original"]) * f_size
            pump_breakdown = {
                "flow_target": target_flow_rate, "flow_ref": q_r, "flow_ratio": target_flow_rate / q_r,
                "flow_exponent_a": a, "F_flow": F_flow,
                "head_target": target_head, "head_ref": h_r, "head_ratio": target_head / h_r,
                "head_exponent_b": b_e, "F_head": F_head,
                "power_target": p_t, "power_ref": p_r,
                "power_ratio": (p_t / p_r) if power_used else None,
                "power_exponent_c": c_e, "F_power": F_power,
                "power_used": power_used, "power_policy": power_policy,
                "renormalization_note": renorm_note,
                "F_pump": f_size,
            }
            ratio_hi = max(target_flow_rate / q_r, q_r / target_flow_rate)
        elif category == "burner":
            # F = (Duty_t/Duty_r)^n
            duty_r = ref.get("thermal_duty_kw")
            if not duty_r or duty_r <= 0:
                excluded.append({"historical_equipment_id": ref_id, "exclusion_reason": "reference thermal_duty_kw missing", "similarity": None})
                continue
            f_size = (target_sv["value"] / duty_r) ** n_exp
            c_after_size = float(ref["cost_original"]) * f_size
            ratio_hi = max(target_sv["value"] / duty_r, duty_r / target_sv["value"])
        else:
            x_t = target_sv["value"]; x_r = ref_sv["value"]
            if x_r <= 0 or x_t <= 0:
                excluded.append({"historical_equipment_id": ref_id, "exclusion_reason": "invalid scaling values", "similarity": None})
                continue
            f_size = (x_t / x_r) ** n_exp
            c_after_size = float(ref["cost_original"]) * f_size
            ratio_hi = max(x_t / x_r, x_r / x_t)

        extrap_flag = ratio_hi > float(sim["max_extrapolation_ratio"])

        # ---- Material factor ----
        ref_material = ref.get("material")
        ref_mf_doc = mfs.get(ref_material)
        if not ref_mf_doc:
            if sim["missing_material_factor_policy"] == "block":
                errors.append(f"Missing material factor for ref material {ref_material}")
                return _unavailable(errors, warnings, candidates, excluded, category, subtype)
            excluded.append({"historical_equipment_id": ref_id, "exclusion_reason": f"missing material factor for '{ref_material}'", "similarity": None})
            continue
        ref_mf = float(ref_mf_doc["factor"])
        f_material = target_mf / ref_mf
        c_after_material = c_after_size * f_material

        # ---- Pressure factor (skipped for pump) ----
        p_ref_barg = ref.get("design_pressure_bar")
        p_ref_abs = None
        try:
            if p_ref_barg is not None:
                p_ref_abs = float(p_ref_barg) + atm
                if p_ref_abs <= 0: p_ref_abs = None
        except (TypeError, ValueError):
            p_ref_abs = None

        p_exp = float(pset["pressure_exponent"]); p_enabled = bool(pset["enabled"])
        f_pressure = 1.0; f_pressure_unbounded = 1.0; pressure_limited = False
        pressure_status = "disabled"
        if p_enabled and p_exp > 0 and category != "pump":
            if p_target_abs is None:
                pressure_status = "skipped-target-pressure-missing"
                if "target design pressure missing; pressure factor not applied" not in warnings:
                    warnings.append("target design pressure missing; pressure factor not applied")
            elif p_ref_abs is None:
                if sim["missing_pressure_policy"] == "block":
                    errors.append("Missing reference pressure with block policy")
                    return _unavailable(errors, warnings, candidates, excluded, category, subtype)
                excluded.append({"historical_equipment_id": ref_id, "exclusion_reason": "reference pressure missing", "similarity": None})
                continue
            else:
                f_pressure_unbounded = (p_target_abs / p_ref_abs) ** p_exp
                f_pressure = f_pressure_unbounded
                mn = pset.get("minimum_factor"); mx = pset.get("maximum_factor")
                if mn is not None and f_pressure < mn: f_pressure = mn; pressure_limited = True
                if mx is not None and f_pressure > mx: f_pressure = mx; pressure_limited = True
                pressure_status = "limited" if pressure_limited else "applied"
        c_after_pressure = c_after_material * f_pressure

        # ---- Escalation ----
        try:
            esc = compute_escalation_sync(int(ref["year"]), int(target_year), steel_w, oil_w, steel, oil)
        except Exception:
            esc = 1.0
        c_after_esc = c_after_pressure * esc

        # ---- Currency ----
        fx_key = (ref["currency"], output_currency, int(ref["year"]))
        fx, fx_fb = fx_map.get(fx_key, (1.0, False))
        if fx_fb: warnings.append(f"FX fallback used for {ref['currency']}->{output_currency} @ {ref['year']}")
        c_adjusted = c_after_esc * fx
        if c_adjusted <= 0:
            excluded.append({"historical_equipment_id": ref_id, "exclusion_reason": "adjusted cost non-positive", "similarity": None})
            continue

        # ---- Similarity ----
        comps = []  # list of (name, weight, value)
        if category == "pump":
            # pump duty similarity
            alpha_Q = float(sim["pump_alpha_Q"]); alpha_H = float(sim["pump_alpha_H"]); alpha_P = float(sim["pump_alpha_P"])
            S_Q = math.exp(-alpha_Q * abs(math.log(pump_breakdown["flow_ratio"])))
            S_H = math.exp(-alpha_H * abs(math.log(pump_breakdown["head_ratio"])))
            duty_comps = [("Q", float(sim["pump_w_Q"]), S_Q), ("H", float(sim["pump_w_H"]), S_H)]
            S_P = None
            if pump_breakdown["power_used"]:
                S_P = math.exp(-alpha_P * abs(math.log(pump_breakdown["power_ratio"])))
                duty_comps.append(("P", float(sim["pump_w_P"]), S_P))
            wsum = sum(w for _, w, _ in duty_comps)
            S_duty = sum((w / wsum) * s for _, w, s in duty_comps) if wsum > 0 else 0.0
            comps.append(("duty", float(sim["pump_duty_weight"]), S_duty))
            # material similarity for pump
            if target_mf > 0 and ref_mf > 0:
                s_material = math.exp(-float(sim["beta"]) * abs(math.log(target_mf / ref_mf)))
                comps.append(("material", float(sim["pump_material_weight"]), s_material))
            s_size = S_duty  # for reporting compatibility
            s_pressure = None
        else:
            # standard similarity
            if category == "burner":
                d_size = abs(math.log(target_sv["value"] / ref.get("thermal_duty_kw")))
            else:
                d_size = abs(math.log(target_sv["value"] / ref_sv["value"]))
            s_size = math.exp(-float(sim["alpha"]) * d_size)
            comps.append(("size", float(sim["w_size"]), s_size))
            if target_mf > 0 and ref_mf > 0:
                s_material = math.exp(-float(sim["beta"]) * abs(math.log(target_mf / ref_mf)))
                comps.append(("material", float(sim["w_material"]), s_material))
            s_pressure = None
            if p_target_abs and p_ref_abs and p_enabled and p_exp > 0:
                s_pressure = math.exp(-float(sim["gamma"]) * abs(math.log(p_target_abs / p_ref_abs)))
                comps.append(("pressure", float(sim["w_pressure"]), s_pressure))

        wsum = sum(w for _, w, _ in comps)
        s_total = sum((w / wsum) * s for _, w, s in comps) if wsum > 0 else 0.0

        if s_total < float(sim["min_similarity"]):
            excluded.append({"historical_equipment_id": ref_id, "exclusion_reason": "Excluded due to insufficient similarity",
                             "subtype": ref.get("subtype"), "similarity": round(s_total, 4)})
            continue

        ref_warnings: List[str] = []
        if extrap_flag: ref_warnings.append("Estimate based on extrapolation outside the validated historical range")

        used.append({
            "historical_equipment_id": ref_id, "category": ref.get("category"), "subtype": ref.get("subtype"), "year": ref.get("year"),
            "original_cost": float(ref["cost_original"]), "original_currency": ref.get("currency"),
            "scaling_variable_name": target_sv["name"],
            "historical_scaling_variable_value": pump_breakdown["flow_ref"] if pump_breakdown else (ref.get("thermal_duty_kw") if category == "burner" else ref_sv["value"]),
            "target_scaling_variable_value": target_sv["value"], "scaling_variable_unit": target_sv["unit"],
            "scale_exponent": n_exp if category != "pump" else None,
            "size_ratio": (target_sv["value"] / (pump_breakdown["flow_ref"] if pump_breakdown else (ref.get("thermal_duty_kw") if category == "burner" else ref_sv["value"]))),
            "size_scaling_factor": f_size,
            "reference_material": ref_material, "target_material": target_material,
            "reference_material_coefficient": ref_mf, "target_material_coefficient": target_mf,
            "applied_material_factor": f_material,
            "reference_design_pressure_barg": p_ref_barg, "target_design_pressure_barg": target_pressure_barg,
            "reference_absolute_pressure_bara": p_ref_abs, "target_absolute_pressure_bara": p_target_abs,
            "pressure_exponent": p_exp, "applied_pressure_factor": f_pressure,
            "pressure_factor_unbounded": f_pressure_unbounded, "pressure_status": pressure_status,
            "escalation_factor": esc, "fx_factor": fx,
            "cost_after_size_scaling": c_after_size, "cost_after_material_correction": c_after_material,
            "cost_after_pressure_correction": c_after_pressure, "cost_after_escalation": c_after_esc,
            "cost_after_currency_conversion": c_adjusted, "adjusted_cost": c_adjusted,
            "size_similarity": s_size, "material_similarity": next((v for n, _, v in comps if n == "material"), None),
            "pressure_similarity": s_pressure, "total_similarity": s_total,
            "unnormalized_weight": s_total,
            "pump_breakdown": pump_breakdown,
            "inclusion_status": "used", "warnings": ref_warnings,
            "outlier": False,
        })

    # Cap max_references
    used.sort(key=lambda x: x["total_similarity"], reverse=True)
    max_refs = int(sim["max_references"])
    if len(used) > max_refs:
        for extra in used[max_refs:]:
            excluded.append({"historical_equipment_id": extra["historical_equipment_id"],
                             "exclusion_reason": f"beyond max_references cap ({max_refs})",
                             "similarity": round(extra["total_similarity"], 4)})
        used = used[:max_refs]

    # ---- IQR OUTLIER FILTER on adjusted costs ----
    outlier_summary = {
        "enabled": bool(sim["outlier_filter_enabled"]),
        "iqr_multiplier": float(sim["iqr_multiplier"]),
        "minimum_references_for_iqr": int(sim["minimum_references_for_iqr"]),
        "references_before_filter": len(used),
        "applied": False, "outliers_removed": 0,
        "q1": None, "q3": None, "iqr": None, "lower_fence": None, "upper_fence": None,
    }
    if sim["outlier_filter_enabled"] and len(used) >= int(sim["minimum_references_for_iqr"]):
        costs = [u["adjusted_cost"] for u in used]
        iqr = _iqr_filter(costs, float(sim["iqr_multiplier"]))
        outlier_summary.update({"applied": True, "q1": iqr["q1"], "q3": iqr["q3"], "iqr": iqr["iqr"],
                                "lower_fence": iqr["lower"], "upper_fence": iqr["upper"]})
        keep = []
        for i, u in enumerate(used):
            if i in iqr["outlier_indices"]:
                u_out = dict(u)
                u_out.update({"exclusion_reason": "Adjusted cost outside IQR fences",
                              "Q1": iqr["q1"], "Q3": iqr["q3"], "IQR": iqr["iqr"],
                              "lower_fence": iqr["lower"], "upper_fence": iqr["upper"],
                              "IQR_multiplier": float(sim["iqr_multiplier"]),
                              "similarity": u["total_similarity"], "output_currency": output_currency})
                excluded.append(u_out); outlier_summary["outliers_removed"] += 1
            else:
                keep.append(u)
        used = keep
    else:
        if sim["outlier_filter_enabled"] and len(used) < int(sim["minimum_references_for_iqr"]):
            warnings.append(f"IQR outlier filtering not applied: fewer than {int(sim['minimum_references_for_iqr'])} valid references")

    outlier_summary["references_remaining_after_filter"] = len(used)

    n_candidate = len(candidates); n_used = len(used)
    if n_used == 0:
        return _unavailable(["all references were excluded"], warnings, candidates, excluded, category, subtype)

    # ---- Normalize weights & compute stats ----
    w_sum = sum(u["unnormalized_weight"] for u in used)
    for u in used:
        u["normalized_weight"] = u["unnormalized_weight"] / w_sum if w_sum > 0 else 0.0
    costs = [u["adjusted_cost"] for u in used]
    ws = [u["normalized_weight"] for u in used]
    stats = weighted_stats(costs, ws)
    expected = stats["mean"] or 0.0
    sigma_pop = stats["sigma_population"]
    sigma_sample = stats["sigma_sample"]
    n_eff = stats["n_eff"]

    for u in used:
        u["weighted_contribution"] = u["adjusted_cost"] * u["normalized_weight"]

    # Range: use sample sigma if available, otherwise None
    sigma_used = sigma_sample
    if sigma_used is not None and expected is not None:
        low = max(0.0, expected - z * sigma_used)
        high = expected + z * sigma_used
    else:
        low = None; high = None
        warnings.append("Insufficient independent historical references to calculate a reliability range")

    cov = (sigma_used / expected) if (sigma_used and expected and expected > 0) else None

    warnings = list(dict.fromkeys(warnings))

    # ---- Summaries ----
    material_factor_summary = {
        "target_material": target_material, "target_material_coefficient": target_mf,
        "reference_material_coefficients": {u["reference_material"]: u["reference_material_coefficient"] for u in used},
        "applied_material_factors_range": [min(u["applied_material_factor"] for u in used), max(u["applied_material_factor"] for u in used)],
    }
    pressure_factor_summary = {
        "target_design_pressure_barg": target_pressure_barg, "target_absolute_pressure_bara": p_target_abs,
        "pressure_exponent": pset["pressure_exponent"], "enabled": pset["enabled"] and category != "pump",
        "applied_pressure_factors": [u["applied_pressure_factor"] for u in used],
        "atmospheric_pressure_bar": atm,
    }
    pump_scaling_summary = None
    if category == "pump":
        pump_scaling_summary = {
            "subtype": subtype, "flow_exponent_a": pump_cfg["a"], "head_exponent_b": pump_cfg["b"], "power_exponent_c": pump_cfg["c"],
            "power_missing_policy": sim["pump_power_missing_policy"],
            "exponent_renormalization": sim["pump_exponent_renormalization"],
            "source": pump_cfg.get("source"), "notes": pump_cfg.get("notes"),
        }
    similarity_summary = {
        "alpha": sim["alpha"], "beta": sim["beta"], "gamma": sim["gamma"],
        "weights": {"size": sim["w_size"], "material": sim["w_material"], "pressure": sim["w_pressure"]},
        "min_similarity": sim["min_similarity"], "average_similarity": sum(u["total_similarity"] for u in used) / n_used,
    }

    # Calculation formula string
    if category == "pump":
        formula = "Cost = C_ref × (Q_target/Q_ref)^a × (H_target/H_ref)^b × (P_target/P_ref)^c × F_material × F_escalation × F_fx"
        if any(not u.get("pump_breakdown", {}).get("power_used") for u in used):
            formula += "  |  Power term excluded when comparable data unavailable"
    elif category == "burner":
        formula = "Cost = C_ref × (Duty_target/Duty_ref)^n × F_material × F_escalation × F_fx"
    else:
        formula = "Cost = C_ref × (X_target/X_ref)^n × F_material × F_pressure × F_escalation × F_fx"

    breakdown = {
        "category": category, "subtype": subtype, "target_material": target_material,
        "target_design_pressure_barg": target_pressure_barg, "target_absolute_pressure_bara": p_target_abs,
        "primary_scaling_variable": target_sv["name"], "scaling_variable_value": target_sv["value"],
        "scaling_variable_unit": target_sv["unit"], "fallback_status": target_sv["is_fallback"],
        "fallback_reason": target_sv["fallback_reason"],
        "scale_exponent_n": n_exp if category != "pump" else None,
        "pump_exponents": {"a": pump_cfg["a"], "b": pump_cfg["b"], "c": pump_cfg["c"]} if pump_cfg else None,
        "pressure_exponent": pset["pressure_exponent"], "pressure_enabled": pset["enabled"] and category != "pump",
        "escalation_weights": {"steel_weight": steel_w, "oil_weight": oil_w},
        "similarity_configuration": similarity_summary,
        "outlier": outlier_summary,
        "target_year": target_year, "output_currency": output_currency,
        "candidate_references": n_candidate, "references_used": n_used,
        "excluded_references_count": len(excluded),
        "expected_cost": expected, "low_estimate": low, "high_estimate": high,
        "sigma_population": sigma_pop, "sigma_sample": sigma_sample, "sigma_used_for_range": sigma_used,
        "coefficient_of_variation": cov, "effective_sample_size": n_eff,
        "confidence_level": conf, "z_value": z, "range_method": "weighted_mean_plus_minus_z_sigma",
        "calculation_method": "weighted historical scaling",
        "calculation_formula": formula,
        "data_quality": _classify_confidence(n_eff),
        "warnings": warnings, "model_version": MODEL_VERSION,
    }

    # ---- Human-readable calculation report ----
    top_refs = sorted(used, key=lambda u: u["normalized_weight"], reverse=True)[:5]
    report = {
        "equipment_description": {
            "category": category, "subtype": subtype, "material": target_material,
            "design_pressure_barg": target_pressure_barg, "primary_variable": target_sv["name"],
            "primary_variable_value": target_sv["value"], "primary_variable_unit": target_sv["unit"],
        },
        "historical_basis": {
            "total_references_found": n_candidate,
            "references_excluded": len(excluded),
            "outliers_removed": outlier_summary["outliers_removed"],
            "references_used": n_used,
        },
        "estimation_method": {
            "method": "weighted historical scaling",
            "category": meta["label"], "subtype": subtype,
            "primary_variable": {"name": target_sv["name"], "unit": target_sv["unit"]},
            "additional_variables": (
                [{"name": "Head", "unit": "m"}, {"name": "Power", "unit": "kW"}] if category == "pump" else []
            ),
            "cost_corrections_applied": (
                ["Dimensional scaling", "Material correction", "Escalation to target year",
                 "Currency conversion", "Similarity weighting"] if category == "pump"
                else ["Dimensional scaling", "Material correction", "Pressure correction",
                      "Escalation to target year", "Currency conversion", "Similarity weighting"]
            ),
            "outlier_filtering": {
                "method": "IQR", "multiplier": float(sim["iqr_multiplier"]),
                "applied": outlier_summary["applied"],
            },
            "reliability_range": {
                "method": "Weighted mean ± z × weighted sample sigma",
                "confidence_level_percent": conf, "z_value": z,
            },
        },
        "equation_used": formula,
        "most_influential_references": [
            {"tag": r.get("historical_equipment_id", "")[:8], "subtype": r["subtype"],
             "weight_percent": round(r["normalized_weight"] * 100, 1),
             "adjusted_cost": round(r["adjusted_cost"], 2),
             "original_year": r["year"], "similarity": round(r["total_similarity"], 3)}
            for r in top_refs
        ],
        "reliability_assessment": {
            "effective_sample_size": round(n_eff, 2),
            "weighted_sigma_sample": round(sigma_sample, 2) if sigma_sample is not None else None,
            "confidence_level_percent": conf, "coefficient_of_variation": round(cov, 4) if cov is not None else None,
            "data_quality": _classify_confidence(n_eff),
        },
        "warnings": warnings,
    }

    return {
        "estimate_available": True,
        "expected": round(expected, 2),
        "low": round(low, 2) if low is not None else None,
        "high": round(high, 2) if high is not None else None,
        "sigma_population": round(sigma_pop, 2) if sigma_pop is not None else None,
        "sigma_sample": round(sigma_sample, 2) if sigma_sample is not None else None,
        "sigma_used_for_range": round(sigma_used, 2) if sigma_used is not None else None,
        "cov": round(cov, 4) if cov is not None else None,
        "candidate_references": n_candidate, "references_used": n_used,
        "effective_sample_size": round(n_eff, 3),
        "scaling_variable": target_sv["name"], "scaling_variable_value": target_sv["value"],
        "scaling_variable_unit": target_sv["unit"], "scaling_variable_is_fallback": target_sv["is_fallback"],
        "material_factor_summary": material_factor_summary,
        "pressure_factor_summary": pressure_factor_summary,
        "pump_scaling_summary": pump_scaling_summary,
        "similarity_summary": similarity_summary,
        "outlier_summary": outlier_summary,
        "estimation_breakdown": breakdown,
        "calculation_report": report,
        "references_detail": used, "references_excluded": excluded,
        "warnings": warnings, "errors": errors,
        "escalation_factor": round(sum(u["escalation_factor"] for u in used) / n_used, 4) if used else 0.0,
        "quantity": max(quantity, 1),
        "total_expected": round(expected * max(quantity, 1), 2),
        "total_low": round(low * max(quantity, 1), 2) if low is not None else None,
        "total_high": round(high * max(quantity, 1), 2) if high is not None else None,
        "confidence_level": conf, "z_value": z,
        "range_method": "weighted_mean_plus_minus_z_sigma",
        "calculation_method": "weighted historical scaling",
        "calculation_formula": formula,
        "model_version": MODEL_VERSION,
    }

# Row estimate wrapper + project sigma aggregation
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
        target_flow_rate=float(row_data["flow_rate_m3_h"]) if row_data.get("flow_rate_m3_h") else None,
        target_head=float(row_data["head_m"]) if row_data.get("head_m") else None,
        target_thermal_duty=float(row_data["thermal_duty_kw"]) if row_data.get("thermal_duty_kw") else None,
        reference_ids=row_data.get("reference_ids"),
    )
    qty = int(row_data.get("quantity") or 1)
    common = {
        "aace_class": project_doc.get("aace_class", "Class 5"),
        "references_used": est.get("references_used", 0),
        "references_candidate": est.get("candidate_references", 0),
        "effective_sample_size": est.get("effective_sample_size", 0.0),
        "escalation_factor": est.get("escalation_factor", 0.0),
        "scaling_variable": est.get("scaling_variable"), "scaling_variable_value": est.get("scaling_variable_value"),
        "scaling_variable_unit": est.get("scaling_variable_unit"),
        "scaling_variable_is_fallback": est.get("scaling_variable_is_fallback", False),
        "material_factor_summary": est.get("material_factor_summary"),
        "pressure_factor_summary": est.get("pressure_factor_summary"),
        "pump_scaling_summary": est.get("pump_scaling_summary"),
        "similarity_summary": est.get("similarity_summary"),
        "outlier_summary": est.get("outlier_summary"),
        "estimation_breakdown": est.get("estimation_breakdown"),
        "calculation_report": est.get("calculation_report"),
        "references_detail": est.get("references_detail") or [],
        "references_excluded": est.get("references_excluded") or [],
        "warnings": est.get("warnings", []), "errors": est.get("errors", []),
        "model_version": MODEL_VERSION,
    }
    if not est.get("estimate_available"):
        return {**common, "unit_expected_cost": 0.0, "unit_low": None, "unit_high": None, "unit_sigma": None,
                "total_expected_cost": 0.0, "total_sigma": None, "estimate_available": False}
    return {
        **common, "unit_expected_cost": est["expected"],
        "unit_low": est["low"], "unit_high": est["high"],
        "unit_sigma": est["sigma_used_for_range"],
        "total_expected_cost": round(est["expected"] * qty, 2),
        # total_sigma computed at project aggregation using rho_quantity
        "total_sigma": est["sigma_used_for_range"] if est["sigma_used_for_range"] is not None else None,
        "estimate_available": True,
    }

# ============================================================
# ROUTES: meta & config
# ============================================================
@api_router.get("/")
async def root():
    return {"status": "ok", "service": "EPC Cost Estimator", "model_version": MODEL_VERSION}

@api_router.get("/meta/categories")
async def categories():
    return {"categories": CATEGORIES, "meta": CATEGORY_META, "materials": MATERIALS,
            "subtypes": CATEGORY_SUBTYPES,
            "confidence_levels": list(CONFIDENCE_Z.keys()), "confidence_z_map": CONFIDENCE_Z,
            "model_version": MODEL_VERSION}

# ============================================================
# ROUTES: historical equipment
# ============================================================
@api_router.get("/equipment", response_model=List[HistoricalEquipment])
async def list_equipment(category: Optional[str] = None, subtype: Optional[str] = None, q: Optional[str] = None):
    query = {}
    if category: query["category"] = category
    if subtype: query["subtype"] = subtype
    docs = await db.equipment_historical.find(query, {"_id": 0}).to_list(2000)
    if q:
        ql = q.lower()
        docs = [d for d in docs if ql in (d.get("subtype") or "").lower() or ql in (d.get("notes") or "").lower() or ql in (d.get("vendor_country") or "").lower()]
    return docs

@api_router.post("/equipment", response_model=HistoricalEquipment)
async def create_equipment(body: HistoricalEquipmentCreate):
    if body.category not in CATEGORY_META:
        raise HTTPException(400, "invalid category")
    canonical = validate_subtype(body.category, body.subtype)
    data = body.model_dump()
    data["subtype"] = canonical
    if not data.get("size_unit"):
        data["size_unit"] = CATEGORY_META[body.category]["size_unit"]
    obj = HistoricalEquipment(**data)
    doc = obj.model_dump(); doc["created_at"] = doc["created_at"].isoformat()
    await db.equipment_historical.insert_one(doc)
    return obj

@api_router.put("/equipment/{eq_id}", response_model=HistoricalEquipment)
async def update_equipment(eq_id: str, body: HistoricalEquipmentCreate):
    existing = await db.equipment_historical.find_one({"id": eq_id}, {"_id": 0})
    if not existing: raise HTTPException(404, "Not found")
    canonical = validate_subtype(body.category, body.subtype)
    updated = body.model_dump(); updated["subtype"] = canonical
    await db.equipment_historical.update_one({"id": eq_id}, {"$set": updated})
    return HistoricalEquipment(**{**existing, **updated})

@api_router.delete("/equipment/{eq_id}")
async def delete_equipment(eq_id: str):
    r = await db.equipment_historical.delete_one({"id": eq_id})
    if r.deleted_count == 0: raise HTTPException(404, "Not found")
    return {"deleted": True}

@api_router.post("/equipment/migrate-subtypes")
async def migrate_subtypes():
    """Utility: migrate legacy subtypes to canonical values. Returns list of records."""
    docs = await db.equipment_historical.find({}, {"_id": 0}).to_list(5000)
    updated = 0; needs_review = []
    for d in docs:
        cat = d.get("category"); raw = d.get("subtype")
        canonical = canonical_subtype(cat, raw)
        if canonical:
            if canonical != raw:
                await db.equipment_historical.update_one({"id": d["id"]}, {"$set": {"subtype": canonical, "subtype_migration_required": False}})
                updated += 1
        else:
            await db.equipment_historical.update_one({"id": d["id"]}, {"$set": {"subtype_migration_required": True}})
            needs_review.append({"id": d["id"], "category": cat, "subtype": raw})
    return {"updated": updated, "needs_review": needs_review}

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
    if not data.get("target_year"): data["target_year"] = datetime.now(timezone.utc).year
    if not data.get("aace_class"): data["aace_class"] = "Class 5"
    obj = Project(**data)
    doc = obj.model_dump(); doc["created_at"] = doc["created_at"].isoformat()
    await db.projects.insert_one(doc)
    return obj

def _aggregate_project(rows: List[Dict[str, Any]], sim: Dict[str, Any]) -> Dict[str, Any]:
    """Aggregate rows into project totals using rho_quantity + rho_between_rows."""
    z = float(sim["z_value"]); conf = str(sim["confidence_level"])
    rho_q = float(sim["rho_quantity"]); rho_r = float(sim["rho_between_rows"])
    total_expected = 0.0
    rows_with_sigma = []
    rows_without_sigma = []
    row_sigmas = []
    for r in rows:
        te = float(r.get("total_expected_cost") or 0.0)
        total_expected += te
        sig_unit = r.get("unit_sigma")
        qty = int(r.get("quantity") or 1)
        if sig_unit is None:
            rows_without_sigma.append(r.get("tag") or r.get("id"))
            row_sigmas.append(None)
        else:
            var_row = (sig_unit ** 2) * (qty + rho_q * qty * (qty - 1))
            sigma_row = math.sqrt(max(var_row, 0.0))
            rows_with_sigma.append({"tag": r.get("tag") or r.get("id"), "sigma_row": sigma_row})
            row_sigmas.append(sigma_row)

    warnings = []
    if rows_without_sigma:
        warnings.append(f"{len(rows_without_sigma)} row(s) have no computable sigma; project range is incomplete")

    if sim["project_missing_sigma_policy"] == "block_project_range" and rows_without_sigma:
        return {"expected": round(total_expected, 2), "sigma_project": None, "low": None, "high": None,
                "confidence_level": conf, "z_value": z,
                "range_method": "weighted_mean_plus_minus_z_sigma",
                "rho_quantity": rho_q, "rho_between_rows": rho_r,
                "rows_with_valid_sigma": len(rows_with_sigma),
                "rows_without_valid_sigma": len(rows_without_sigma),
                "aace_class": rows[0].get("aace_class") if rows else "Class 5",
                "warnings": warnings + ["Project range blocked by policy 'block_project_range'"],
                "sigma": None}

    # Compute variance
    valid_sigmas = [s for s in row_sigmas if s is not None]
    if not valid_sigmas:
        return {"expected": round(total_expected, 2), "sigma_project": None, "low": None, "high": None,
                "confidence_level": conf, "z_value": z,
                "range_method": "weighted_mean_plus_minus_z_sigma",
                "rho_quantity": rho_q, "rho_between_rows": rho_r,
                "rows_with_valid_sigma": 0, "rows_without_valid_sigma": len(rows_without_sigma),
                "aace_class": rows[0].get("aace_class") if rows else "Class 5",
                "warnings": warnings, "sigma": None}
    var_sum = sum(s * s for s in valid_sigmas)
    if abs(rho_r) > 1e-12:
        # add 2*rho*sum_{i<j} sigma_i*sigma_j
        cross = 0.0
        for i in range(len(valid_sigmas)):
            for j in range(i + 1, len(valid_sigmas)):
                cross += valid_sigmas[i] * valid_sigmas[j]
        var_sum += 2 * rho_r * cross
    sigma_project = math.sqrt(max(var_sum, 0.0))
    low = max(0.0, total_expected - z * sigma_project)
    high = total_expected + z * sigma_project
    return {
        "expected": round(total_expected, 2),
        "sigma_project": round(sigma_project, 2),
        "sigma": round(sigma_project, 2),  # legacy key
        "low": round(low, 2), "high": round(high, 2),
        "confidence_level": conf, "z_value": z,
        "range_method": "weighted_mean_plus_minus_z_sigma",
        "rho_quantity": rho_q, "rho_between_rows": rho_r,
        "rows_with_valid_sigma": len(rows_with_sigma),
        "rows_without_valid_sigma": len(rows_without_sigma),
        "aace_class": rows[0].get("aace_class") if rows else "Class 5",
        "warnings": warnings,
    }

@api_router.get("/projects/{pid}")
async def get_project(pid: str):
    p = await db.projects.find_one({"id": pid}, {"_id": 0})
    if not p: raise HTTPException(404, "Project not found")
    rows = await db.equipment_rows.find({"project_id": pid}, {"_id": 0}).sort("created_at", 1).to_list(2000)
    sim = await get_similarity_config()
    totals = _aggregate_project(rows, sim)
    totals["aace_class"] = p.get("aace_class", "Class 5")
    if isinstance(p.get("created_at"), str):
        p["created_at"] = datetime.fromisoformat(p["created_at"])
    return {"project": p, "rows": rows, "totals": totals}

@api_router.put("/projects/{pid}", response_model=Project)
async def update_project(pid: str, body: ProjectUpdate):
    existing = await db.projects.find_one({"id": pid}, {"_id": 0})
    if not existing: raise HTTPException(404, "Not found")
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
    if r.deleted_count == 0: raise HTTPException(404, "Not found")
    return {"deleted": True}

# ============================================================
# ROUTES: equipment rows
# ============================================================
def _sanitize_row_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    cat = data.get("category"); meta = CATEGORY_META.get(cat)
    if not meta: return data
    allowed = set(meta["allowed_fields"])
    field_map = {"power_kw": "power_kw", "weight_kg": "weight_kg",
                 "design_pressure_bar": "design_pressure_bar",
                 "design_temperature_c": "design_temperature_c",
                 "flow_rate_m3_h": "flow_rate_m3_h", "head_m": "head_m",
                 "pump_efficiency": "pump_efficiency",
                 "fluid_density_kg_m3": "fluid_density_kg_m3",
                 "thermal_duty_kw": "thermal_duty_kw", "fuel_flow_kg_h": "fuel_flow_kg_h"}
    for f in field_map:
        if f not in allowed:
            data[f] = None
    # size fallback
    if not data.get("size"):
        # if pump: use flow_rate_m3_h as size fallback for legacy
        if cat == "pump" and data.get("flow_rate_m3_h"):
            data["size"] = data["flow_rate_m3_h"]
        elif cat == "burner" and data.get("thermal_duty_kw"):
            data["size"] = data["thermal_duty_kw"]
    if not data.get("size_unit"):
        data["size_unit"] = meta["size_unit"]
    return data

@api_router.post("/projects/{pid}/rows", response_model=EquipmentRow)
async def add_row(pid: str, body: EquipmentRowCreate):
    p = await db.projects.find_one({"id": pid}, {"_id": 0})
    if not p: raise HTTPException(404, "Project not found")
    canonical = validate_subtype(body.category, body.subtype)
    data = body.model_dump(); data["subtype"] = canonical
    # size default if omitted
    if data.get("size") is None:
        if body.category == "pump" and data.get("flow_rate_m3_h"):
            data["size"] = data["flow_rate_m3_h"]
        elif body.category == "burner" and data.get("thermal_duty_kw"):
            data["size"] = data["thermal_duty_kw"]
        else:
            raise HTTPException(422, "size is required for this category")
    data = _sanitize_row_payload(data)
    est = await _compute_row_estimate(p, data)
    row = EquipmentRow(project_id=pid, **data, **est)
    doc = row.model_dump(); doc["created_at"] = doc["created_at"].isoformat()
    await db.equipment_rows.insert_one(doc)
    return row

@api_router.put("/projects/{pid}/rows/{rid}", response_model=EquipmentRow)
async def update_row(pid: str, rid: str, body: EquipmentRowCreate):
    p = await db.projects.find_one({"id": pid}, {"_id": 0})
    if not p: raise HTTPException(404, "Project not found")
    existing = await db.equipment_rows.find_one({"id": rid, "project_id": pid}, {"_id": 0})
    if not existing: raise HTTPException(404, "Row not found")
    canonical = validate_subtype(body.category, body.subtype)
    data = body.model_dump(); data["subtype"] = canonical
    if data.get("size") is None:
        if body.category == "pump" and data.get("flow_rate_m3_h"):
            data["size"] = data["flow_rate_m3_h"]
        elif body.category == "burner" and data.get("thermal_duty_kw"):
            data["size"] = data["thermal_duty_kw"]
        else:
            raise HTTPException(422, "size is required for this category")
    data = _sanitize_row_payload(data)
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
    if r.deleted_count == 0: raise HTTPException(404, "Not found")
    return {"deleted": True}

@api_router.post("/projects/{pid}/recompute")
async def recompute_project(pid: str):
    p = await db.projects.find_one({"id": pid}, {"_id": 0})
    if not p: raise HTTPException(404, "Project not found")
    rows = await db.equipment_rows.find({"project_id": pid}, {"_id": 0}).to_list(2000)
    for r in rows:
        try:
            # migrate legacy subtype to canonical if possible
            canonical = canonical_subtype(r["category"], r.get("subtype"))
            if canonical: r["subtype"] = canonical
            data = _sanitize_row_payload(dict(r))
            est = await _compute_row_estimate(p, data)
            await db.equipment_rows.update_one({"id": r["id"]}, {"$set": {**data, **est}})
        except Exception as e:
            logging.exception(f"recompute row {r.get('id')} failed: {e}")
    return {"ok": True, "updated": len(rows)}

# ============================================================
# ROUTES: estimate preview
# ============================================================
class EstimatePreview(BaseModel):
    category: str
    subtype: str
    size: Optional[float] = Field(default=None, gt=0)
    weight_kg: Optional[float] = Field(default=None, gt=0)
    power_kw: Optional[float] = Field(default=None, gt=0)
    flow_rate_m3_h: Optional[float] = Field(default=None, gt=0)
    head_m: Optional[float] = Field(default=None, gt=0)
    thermal_duty_kw: Optional[float] = Field(default=None, gt=0)
    material: str
    design_pressure_bar: Optional[float] = None
    target_year: int
    output_currency: Literal["EUR", "USD"] = "EUR"
    reference_ids: Optional[List[str]] = None
    quantity: int = Field(default=1, ge=1)

@api_router.post("/estimate")
async def estimate_preview(body: EstimatePreview):
    return await estimate_full(
        category=body.category, target_size=body.size,
        target_weight_kg=body.weight_kg, target_power_kw=body.power_kw,
        target_flow_rate=body.flow_rate_m3_h, target_head=body.head_m,
        target_thermal_duty=body.thermal_duty_kw,
        target_material=body.material, target_pressure_barg=body.design_pressure_bar,
        subtype=body.subtype, target_year=body.target_year,
        output_currency=body.output_currency, reference_ids=body.reference_ids,
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
        if item.n <= 0: raise HTTPException(400, f"scale exponent must be > 0 for {item.category}")
        await db.scale_exponents.update_one({"category": item.category},
            {"$set": {"n": item.n, "updated_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
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
        out.append({"material": mat, "factor": d.get("factor", default["factor"]),
                    "reference_material": d.get("reference_material", REFERENCE_MATERIAL),
                    "source": d.get("source", default["source"]), "notes": d.get("notes", default["notes"]),
                    "default_factor": default["factor"], "updated_at": d.get("updated_at")})
    return out

@api_router.put("/admin/material-factors")
async def set_material_factors(body: List[MaterialFactor]):
    for item in body:
        if item.factor <= 0: raise HTTPException(400, f"material factor must be > 0 for {item.material}")
        if item.material not in MATERIALS: raise HTTPException(400, f"unknown material {item.material}")
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
        out.append({"category": cat, "label": CATEGORY_META[cat]["label"],
                    "pressure_exponent": cfg["pressure_exponent"], "enabled": cfg["enabled"],
                    "minimum_factor": cfg.get("minimum_factor"), "maximum_factor": cfg.get("maximum_factor"),
                    "source": cfg.get("source"), "notes": cfg.get("notes"),
                    "default_exponent": CATEGORY_META[cat]["pressure_exp_default"],
                    "default_enabled": CATEGORY_META[cat]["pressure_enabled_default"]})
    return out

@api_router.put("/admin/pressure-factors")
async def set_pressure_factors(body: List[PressureSetting]):
    for item in body:
        if item.pressure_exponent < 0: raise HTTPException(400, f"pressure exponent must be >= 0 for {item.category}")
        upd = item.model_dump(); upd["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.pressure_settings.update_one({"category": item.category}, {"$set": upd}, upsert=True)
    return {"ok": True}

@api_router.get("/admin/pump-configs")
async def list_pump_configs():
    out = []
    for st in CATEGORY_SUBTYPES.get("pump", []):
        cfg = await get_pump_config(st)
        out.append({**cfg, "default_a": PUMP_DEFAULTS[st]["a"], "default_b": PUMP_DEFAULTS[st]["b"], "default_c": PUMP_DEFAULTS[st]["c"]})
    return out

@api_router.put("/admin/pump-configs")
async def set_pump_configs(body: List[PumpScalingConfig]):
    for item in body:
        if item.subtype not in CATEGORY_SUBTYPES.get("pump", []):
            raise HTTPException(400, f"invalid pump subtype: {item.subtype}")
        upd = item.model_dump(); upd["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.pump_configs.update_one({"subtype": item.subtype}, {"$set": upd}, upsert=True)
    return {"ok": True}

@api_router.get("/admin/similarity-settings")
async def get_similarity_settings():
    cfg = await get_similarity_config()
    return {**cfg, "defaults": SIMILARITY_DEFAULTS, "confidence_z_map": CONFIDENCE_Z}

@api_router.put("/admin/similarity-settings")
async def set_similarity_settings(body: SimilarityConfig):
    d = body.model_dump()
    if d["alpha"] <= 0: raise HTTPException(400, "alpha must be > 0")
    if d["beta"] < 0 or d["gamma"] < 0: raise HTTPException(400, "beta and gamma must be >= 0")
    ws = d["w_size"] + d["w_material"] + d["w_pressure"]
    if abs(ws - 1.0) > 0.01: raise HTTPException(400, "similarity weights (size+material+pressure) must sum to 1.0")
    if not (0 <= d["min_similarity"] <= 1): raise HTTPException(400, "min_similarity must be in [0,1]")
    if d["max_references"] < 1: raise HTTPException(400, "max_references must be >= 1")
    if d["atmospheric_pressure_bar"] <= 0: raise HTTPException(400, "atmospheric_pressure_bar must be > 0")
    if d["iqr_multiplier"] <= 0: raise HTTPException(400, "iqr_multiplier must be > 0")
    if d["minimum_references_for_iqr"] < 2: raise HTTPException(400, "minimum_references_for_iqr must be >= 2")
    pw = d["pump_w_Q"] + d["pump_w_H"] + d["pump_w_P"]
    if abs(pw - 1.0) > 0.01: raise HTTPException(400, "pump duty weights (Q+H+P) must sum to 1.0")
    if abs(d["pump_duty_weight"] + d["pump_material_weight"] - 1.0) > 0.01:
        raise HTTPException(400, "pump duty_weight + material_weight must sum to 1.0")
    if str(d["confidence_level"]) not in CONFIDENCE_Z:
        raise HTTPException(400, f"invalid confidence_level (allowed: {list(CONFIDENCE_Z.keys())})")
    d["z_value"] = CONFIDENCE_Z[str(d["confidence_level"])]
    if not (-1.0 <= d["rho_quantity"] <= 1.0): raise HTTPException(400, "rho_quantity must be in [-1,1]")
    if not (-1.0 <= d["rho_between_rows"] <= 1.0): raise HTTPException(400, "rho_between_rows must be in [-1,1]")
    d["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.similarity_config.update_one({"_id": "singleton"}, {"$set": d}, upsert=True)
    return {"ok": True}

# ============================================================
# INDICES DEBUG
# ============================================================
@api_router.get("/indices")
async def indices_endpoint():
    steel, oil, src = await get_indices()
    return {"steel_by_year": {int(k): v for k, v in steel.items()},
            "oil_by_year": {int(k): v for k, v in oil.items()}, "source": src}

# ============================================================
# SEED
# ============================================================
DUMMY_HISTORICAL = [
    # (category, subtype (canonical), size, unit, weight_kg, material, P, T, power, year, cost, ccy, notes, extra)
    ("column",         "Tray",     45,   "m3",   32000, "carbon_steel",        12,  180, None, 2018, 480000,  "EUR", "20-tray column", {}),
    ("column",         "Packed",   60,   "m3",   38000, "stainless_steel_316",  8,  160, None, 2019, 620000,  "EUR", "Packed column", {}),
    ("reactor",        "CSTR",     35,   "m3",   45000, "stainless_steel_316", 25,  220, None, 2020, 780000,  "EUR", "Batch reactor", {}),
    ("reactor",        "CSTR",     25,   "m3",   28000, "carbon_steel",        15,  200, None, 2017, 420000,  "EUR", "CSTR", {}),
    ("vessel",         "3-Phase",  40,   "m3",   22000, "carbon_steel",        15,  90,  None, 2018, 260000,  "EUR", "Horizontal 3-phase separator", {}),
    ("vessel",         "2-Phase",  25,   "m3",   16000, "stainless_steel_316", 20,  120, None, 2020, 240000,  "EUR", "Vertical KO drum", {}),
    ("heat_exchanger", "Shell and Tube", 120, "m2", 8500, "stainless_steel_304", 16, 250, None, 2019, 180000, "EUR", "S&T HX 120m2", {}),
    ("heat_exchanger", "Reboiler",       80,  "m2", 3500, "stainless_steel_316", 10, 200, None, 2020, 150000, "EUR", "Reboiler", {}),
    ("storage_tank",   "Fixed Roof",  500,  "m3", 35000, "carbon_steel",         1,  50,  None, 2016, 210000, "EUR", "Atm tank 500m3", {}),
    ("storage_tank",   "Fixed Roof",  200,  "m3", 28000, "carbon_steel",         6,  80,  None, 2019, 340000, "EUR", "Pressurized tank", {}),
    # Pumps: full multivariate data
    ("pump", "Centrifugal", 80, "m3/h", 1200, "stainless_steel_316", 10, 120, 55,  2020, 42000, "EUR", "Cent pump 55kW", {"flow_rate_m3_h": 80, "head_m": 40}),
    ("pump", "Centrifugal", 150, "m3/h", 1800, "stainless_steel_316", 15, 150, 110, 2021, 78000, "EUR", "Cent pump 110kW", {"flow_rate_m3_h": 150, "head_m": 55}),
    ("pump", "Centrifugal", 60, "m3/h", 1000, "carbon_steel", 8, 100, 45, 2019, 35000, "EUR", "Small cent pump", {"flow_rate_m3_h": 60, "head_m": 35}),
    ("pump", "Positive Displacement", 30, "m3/h", 900, "stainless_steel_316", 15, 100, 22, 2020, 38000, "EUR", "PD pump", {"flow_rate_m3_h": 30, "head_m": 60}),
    ("compressor",     "Centrifugal", 8000, "m3/h", 12000, "carbon_steel", 25, 180, 450, 2020, 950000, "EUR", "Cent compressor", {}),
    ("valve",          "Ball",        100,  "mm",     50,  "stainless_steel_316", 20, 150, None, 2020, 6500,   "EUR", "DN100 ball valve", {}),
    ("valve",          "Gate",        100,  "mm",     55,  "stainless_steel_316", 20, 150, None, 2019, 5800,   "EUR", "DN100 gate valve", {}),
    ("valve",          "Globe",       80,   "mm",     45,  "stainless_steel_316", 20, 150, None, 2020, 6200,   "EUR", "DN80 globe", {}),
    ("valve",          "Butterfly",   150,  "mm",     70,  "carbon_steel",         5,  80, None, 2020, 4200,   "EUR", "DN150 butterfly", {}),
    ("valve",          "Check",       100,  "mm",     50,  "carbon_steel",        10, 100, None, 2021, 3800,   "EUR", "Check valve", {}),
    ("instrumentation","Pressure",    1,    "unit",   2,   "stainless_steel_316", 40,  80, None, 2021, 1800,   "EUR", "PT smart", {}),
    ("instrumentation","Flow",        1,    "unit",   3,   "stainless_steel_316", 40,  80, None, 2020, 3200,   "EUR", "Flow transmitter", {}),
    ("burner",         "Process Burner", 5000, "kW", None, "carbon_steel",     None, None, None, 2020, 320000, "EUR", "Process burner", {"thermal_duty_kw": 5000, "fuel_flow_kg_h": 380}),
    ("burner",         "Process Burner", 8000, "kW", None, "carbon_steel",     None, None, None, 2021, 480000, "EUR", "Process burner large", {"thermal_duty_kw": 8000, "fuel_flow_kg_h": 610}),
]

DUMMY_ROWS = [
    # tag, category, subtype, size, unit, weight_kg, material, P, T, power, qty, extra
    ("C-101", "column",         "Packed",  50, "m3",   36000, "stainless_steel_316", 10, 170, None, 1, {}),
    ("R-201", "reactor",        "CSTR",    30, "m3",   32000, "stainless_steel_316", 20, 210, None, 1, {}),
    ("E-301", "heat_exchanger", "Shell and Tube", 150, "m2", 9500, "stainless_steel_304", 15, 240, None, 2, {}),
    ("T-401", "storage_tank",   "Fixed Roof", 600, "m3", 38000, "carbon_steel", 1, 50, None, 3, {}),
    ("P-501", "pump",           "Centrifugal", 100, "m3/h", None, "stainless_steel_316", None, None, 75, 4, {"flow_rate_m3_h": 100, "head_m": 45}),
    ("V-701", "valve",          "Ball",   100, "mm",   None, "stainless_steel_316", 20, 150, None, 25, {}),
    ("I-801", "instrumentation","Pressure", 1, "unit", None, "stainless_steel_316", None, None, None, 40, {}),
    ("B-901", "burner",         "Process Burner", 6000, "kW", None, "carbon_steel", None, None, None, 1, {"thermal_duty_kw": 6000}),
]

async def seed_data():
    count = await db.equipment_historical.count_documents({})
    if count == 0:
        logging.info("Seeding historical equipment...")
        for row in DUMMY_HISTORICAL:
            (cat, sub, size, unit, w, mat, p, t, pw, yr, cost, ccy, notes, extra) = row
            data = dict(category=cat, subtype=sub, size=size, size_unit=unit, weight_kg=w,
                        material=mat, design_pressure_bar=p, design_temperature_c=t, power_kw=pw,
                        year=yr, cost_original=cost, currency=ccy, notes=notes)
            data.update(extra or {})
            obj = HistoricalEquipment(**data)
            doc = obj.model_dump(); doc["created_at"] = doc["created_at"].isoformat()
            await db.equipment_historical.insert_one(doc)

    proj_count = await db.projects.count_documents({})
    if proj_count == 0:
        logging.info("Seeding dummy project...")
        proj = Project(name="DUMMY - Petrochemical Unit",
                       description="Sample project pre-populated for testing",
                       output_currency="EUR", target_year=datetime.now(timezone.utc).year, aace_class="Class 5")
        pdoc = proj.model_dump(); pdoc["created_at"] = pdoc["created_at"].isoformat()
        await db.projects.insert_one(pdoc)
        for r in DUMMY_ROWS:
            (tag, cat, sub, size, unit, w, mat, p, t, pw, qty, extra) = r
            data = {"tag": tag, "category": cat, "subtype": sub, "size": size, "size_unit": unit,
                    "weight_kg": w, "material": mat, "design_pressure_bar": p, "design_temperature_c": t,
                    "power_kw": pw, "quantity": qty}
            data.update(extra or {})
            data = _sanitize_row_payload(data)
            est = await _compute_row_estimate(pdoc, data)
            row_obj = EquipmentRow(project_id=proj.id, **data, **est)
            rdoc = row_obj.model_dump(); rdoc["created_at"] = rdoc["created_at"].isoformat()
            await db.equipment_rows.insert_one(rdoc)

# ============================================================
# APP SETUP
# ============================================================
app.include_router(api_router)
app.add_middleware(CORSMiddleware, allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','), allow_methods=["*"], allow_headers=["*"])

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def on_startup():
    try:
        # v3 migration: strip legacy v2 keys from similarity_config singleton
        try:
            legacy_keys = ["w_subtype", "subtype_mismatch"]
            doc = await db.similarity_config.find_one({"_id": "singleton"})
            if doc and any(k in doc for k in legacy_keys):
                await db.similarity_config.update_one(
                    {"_id": "singleton"},
                    {"$unset": {k: "" for k in legacy_keys}}
                )
                # if the stored weights don't sum to 1, reset to defaults
                ws = float(doc.get("w_size", 0) or 0) + float(doc.get("w_material", 0) or 0) + float(doc.get("w_pressure", 0) or 0)
                if abs(ws - 1.0) > 0.01:
                    await db.similarity_config.update_one(
                        {"_id": "singleton"},
                        {"$set": {"w_size": SIMILARITY_DEFAULTS["w_size"],
                                  "w_material": SIMILARITY_DEFAULTS["w_material"],
                                  "w_pressure": SIMILARITY_DEFAULTS["w_pressure"]}}
                    )
                logging.info("Migrated similarity_config: removed legacy v2 keys.")
        except Exception as e:
            logging.warning(f"similarity_config migration skipped: {e}")
        await seed_data()
    except Exception as e:
        logger.exception(f"Seed failed: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
