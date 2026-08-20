import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API });

export const CAT_LABELS = {
  column: "Distillation Column",
  reactor: "Reactor",
  vessel: "Vessel",
  heat_exchanger: "Heat Exchanger",
  storage_tank: "Storage Tank",
  pump: "Pump",
  compressor: "Compressor",
  valve: "Valve",
  instrumentation: "Instrumentation",
  other: "Other",
};

export const MAT_LABELS = {
  carbon_steel: "Carbon Steel",
  stainless_steel_304: "SS 304",
  stainless_steel_316: "SS 316",
  duplex: "Duplex",
  alloy: "Alloy",
  other: "Other",
};

// Per-category form field visibility rules (frontend enforcement)
// { size, size_unit, weight_kg, power_kw, pressure, temperature }
export const FIELD_RULES = {
  column:          { size: true,  unit: "m³",   size_label: "Internal Volume", weight_kg: true,  power_kw: false, pressure: true,  temperature: true },
  reactor:         { size: true,  unit: "m³",   size_label: "Internal Volume", weight_kg: true,  power_kw: false, pressure: true,  temperature: true },
  vessel:          { size: true,  unit: "m³",   size_label: "Internal Volume", weight_kg: true,  power_kw: false, pressure: true,  temperature: true },
  storage_tank:    { size: true,  unit: "m³",   size_label: "Internal Volume", weight_kg: true,  power_kw: false, pressure: true,  temperature: true },
  heat_exchanger:  { size: true,  unit: "m²",   size_label: "Heat Transfer Area", weight_kg: true,  power_kw: false, pressure: true,  temperature: true },
  pump:            { size: true,  unit: "m³/h", size_label: "Capacity",         weight_kg: true,  power_kw: true,  pressure: true,  temperature: false },
  compressor:      { size: true,  unit: "m³/h", size_label: "Gas Capacity (ref. cond.)", weight_kg: true, power_kw: true, pressure: true, temperature: false },
  valve:           { size: true,  unit: "mm",   size_label: "Nominal Diameter (DN)", weight_kg: false, power_kw: false, pressure: true, temperature: true },
  instrumentation: { size: true,  unit: "unit", size_label: "Unit Count",       weight_kg: false, power_kw: false, pressure: false, temperature: false },
  other:           { size: true,  unit: "unit", size_label: "Size",             weight_kg: true,  power_kw: true,  pressure: true,  temperature: true },
};

export const PRIMARY_VAR_LABEL = {
  weight_kg: "Equipment weight",
  power_kw: "Power",
  size: "Primary size",
};

export const formatMoney = (val, ccy = "EUR") => {
  if (val === null || val === undefined || isNaN(val)) return "—";
  const symbol = ccy === "EUR" ? "€" : "$";
  return `${symbol} ${Number(val).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
};

export const formatNum = (val, digits = 2) => {
  if (val === null || val === undefined || isNaN(val)) return "—";
  return Number(val).toLocaleString(undefined, { maximumFractionDigits: digits });
};

export const aaceBadgeClass = (cls) => {
  if (cls === "Class 3" || cls === "Class 2" || cls === "Class 1") return "badge-class-3";
  if (cls === "Class 4") return "badge-class-4";
  return "badge-class-5";
};
