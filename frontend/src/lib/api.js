import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API });

export const CAT_LABELS = {
  column: "Distillation Column",
  reactor: "Reactor",
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

export const formatMoney = (val, ccy = "EUR") => {
  if (val === null || val === undefined || isNaN(val)) return "—";
  const symbol = ccy === "EUR" ? "€" : "$";
  return `${symbol} ${Number(val).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
};

export const aaceBadgeClass = (cls) => {
  if (cls === "Class 3") return "badge-class-3";
  if (cls === "Class 4") return "badge-class-4";
  return "badge-class-5";
};
