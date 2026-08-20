import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;
export const api = axios.create({ baseURL: API });

export const CAT_LABELS = {
  column: "Distillation Column", reactor: "Reactor", vessel: "Vessel",
  heat_exchanger: "Heat Exchanger", storage_tank: "Storage Tank",
  pump: "Pump", compressor: "Compressor", valve: "Valve",
  instrumentation: "Instrumentation", burner: "Burner", other: "Other",
};

export const MAT_LABELS = {
  carbon_steel: "Carbon Steel", stainless_steel_304: "SS 304",
  stainless_steel_316: "SS 316", duplex: "Duplex", alloy: "Alloy", other: "Other",
};

// Category-specific field rules (v3)
export const FIELD_RULES = {
  column:          { unit: "m³",   size_label: "Internal Volume",       weight_kg: true,  power_kw: false, pressure: true,  temperature: true,  flow_head: false, thermal_duty: false },
  reactor:         { unit: "m³",   size_label: "Internal Volume",       weight_kg: true,  power_kw: false, pressure: true,  temperature: true,  flow_head: false, thermal_duty: false },
  vessel:          { unit: "m³",   size_label: "Internal Volume",       weight_kg: true,  power_kw: false, pressure: true,  temperature: true,  flow_head: false, thermal_duty: false },
  storage_tank:    { unit: "m³",   size_label: "Internal Volume",       weight_kg: true,  power_kw: false, pressure: true,  temperature: true,  flow_head: false, thermal_duty: false },
  heat_exchanger:  { unit: "m²",   size_label: "Heat Transfer Area",    weight_kg: true,  power_kw: false, pressure: true,  temperature: true,  flow_head: false, thermal_duty: false },
  pump:            { unit: "m³/h", size_label: "Capacity",              weight_kg: false, power_kw: true,  pressure: false, temperature: false, flow_head: true,  thermal_duty: false },
  compressor:      { unit: "m³/h", size_label: "Gas Capacity",          weight_kg: false, power_kw: true,  pressure: true,  temperature: false, flow_head: false, thermal_duty: false },
  valve:           { unit: "mm",   size_label: "Nominal Diameter (DN)", weight_kg: false, power_kw: false, pressure: true,  temperature: true,  flow_head: false, thermal_duty: false },
  instrumentation: { unit: "unit", size_label: "Unit Count",            weight_kg: false, power_kw: false, pressure: false, temperature: false, flow_head: false, thermal_duty: false },
  burner:          { unit: "kW",   size_label: "Thermal Duty",          weight_kg: false, power_kw: false, pressure: false, temperature: true,  flow_head: false, thermal_duty: true  },
  other:           { unit: "unit", size_label: "Size",                  weight_kg: true,  power_kw: true,  pressure: true,  temperature: true,  flow_head: false, thermal_duty: false },
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
  if (["Class 3", "Class 2", "Class 1"].includes(cls)) return "badge-class-3";
  if (cls === "Class 4") return "badge-class-4";
  return "badge-class-5";
};

// Cache the categories/subtypes response
let _meta = null;
export async function getMeta() {
  if (_meta) return _meta;
  const { data } = await api.get("/meta/categories");
  _meta = data;
  return _meta;
}
