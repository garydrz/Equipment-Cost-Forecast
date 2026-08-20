import { useEffect, useState } from "react";
import { api, MAT_LABELS, CAT_LABELS } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";

export default function Admin() {
  return (
    <div className="p-8 max-w-6xl">
      <div className="mb-6">
        <div className="text-xs uppercase tracking-[0.2em] text-slate-500 mb-2">Configuration</div>
        <h1 className="font-heading text-3xl font-semibold tracking-tight text-slate-900 klein-underline">Admin Parameters</h1>
        <p className="text-sm text-slate-600 mt-3 max-w-3xl">
          Calibrate scaling exponents, material factors, pressure factor settings, escalation weights and similarity parameters. All values are preliminary and must be calibrated against your company historical data.
        </p>
      </div>

      <Tabs defaultValue="exponents" className="w-full">
        <TabsList className="rounded-none bg-slate-100 border border-border p-0 h-auto">
          <TabsTrigger value="exponents" className="rounded-none px-4 py-2 data-[state=active]:bg-white" data-testid="tab-exponents">Scale Exponents</TabsTrigger>
          <TabsTrigger value="materials" className="rounded-none px-4 py-2 data-[state=active]:bg-white" data-testid="tab-materials">Material Factors</TabsTrigger>
          <TabsTrigger value="pressure" className="rounded-none px-4 py-2 data-[state=active]:bg-white" data-testid="tab-pressure">Pressure Factors</TabsTrigger>
          <TabsTrigger value="escalation" className="rounded-none px-4 py-2 data-[state=active]:bg-white" data-testid="tab-escalation">Escalation Weights</TabsTrigger>
          <TabsTrigger value="similarity" className="rounded-none px-4 py-2 data-[state=active]:bg-white" data-testid="tab-similarity">Similarity</TabsTrigger>
        </TabsList>
        <TabsContent value="exponents" className="mt-4"><ScaleExponents /></TabsContent>
        <TabsContent value="materials" className="mt-4"><MaterialFactors /></TabsContent>
        <TabsContent value="pressure" className="mt-4"><PressureFactors /></TabsContent>
        <TabsContent value="escalation" className="mt-4"><EscalationWeights /></TabsContent>
        <TabsContent value="similarity" className="mt-4"><SimilaritySettings /></TabsContent>
      </Tabs>
    </div>
  );
}

// ---------- Scale Exponents ----------
function ScaleExponents() {
  const [rows, setRows] = useState([]);
  useEffect(() => { api.get("/admin/scale-exponents").then(r => setRows(r.data)); }, []);
  const save = async () => {
    try {
      await api.put("/admin/scale-exponents", rows.map(r => ({ category: r.category, n: Number(r.n) })));
      toast.success("Saved");
    } catch (e) { toast.error("Failed"); }
  };
  return (
    <Panel title="Scale Exponents (n)" onSave={save} testId="save-exponents-btn"
           note="Cost_new = Cost_hist × (Size_new / Size_hist)^n. Values are preliminary — calibrate on company data.">
      <table className="w-full data-table">
        <thead><tr>
          <th className="text-left px-3 py-2">Category</th>
          <th className="text-right px-3 py-2">Default</th>
          <th className="text-right px-3 py-2 w-40">Current n</th>
        </tr></thead>
        <tbody>{rows.map((row, i) => (
          <tr key={row.category}>
            <td className="px-3 py-2">{row.label}</td>
            <td className="px-3 py-2 text-right font-mono-num text-slate-500">{row.default_n}</td>
            <td className="px-3 py-2 text-right">
              <Input type="number" step="0.01" value={row.n} onChange={(e) => { const v = [...rows]; v[i] = { ...row, n: e.target.value }; setRows(v); }}
                     className="rounded-none font-mono-num text-right h-8" data-testid={`exp-input-${row.category}`} />
            </td>
          </tr>
        ))}</tbody>
      </table>
    </Panel>
  );
}

// ---------- Material Factors ----------
function MaterialFactors() {
  const [rows, setRows] = useState([]);
  useEffect(() => { api.get("/admin/material-factors").then(r => setRows(r.data)); }, []);
  const save = async () => {
    try {
      await api.put("/admin/material-factors", rows.map(r => ({
        material: r.material, factor: Number(r.factor),
        reference_material: r.reference_material || "carbon_steel",
        source: r.source, notes: r.notes,
      })));
      toast.success("Saved");
    } catch (e) { toast.error("Failed"); }
  };
  return (
    <Panel title="Material Factors (F_material = MF_target / MF_reference)" onSave={save} testId="save-materials-btn"
           note="Reference material is Carbon Steel (F=1.0). Values are preliminary configurable defaults — to be calibrated against your company historical data. Not normative factors.">
      <table className="w-full data-table">
        <thead><tr>
          <th className="text-left px-3 py-2">Material</th>
          <th className="text-right px-3 py-2">Default</th>
          <th className="text-right px-3 py-2 w-32">Factor</th>
          <th className="text-left px-3 py-2">Source</th>
          <th className="text-left px-3 py-2">Notes</th>
        </tr></thead>
        <tbody>{rows.map((row, i) => (
          <tr key={row.material}>
            <td className="px-3 py-2">{MAT_LABELS[row.material]}</td>
            <td className="px-3 py-2 text-right font-mono-num text-slate-500">{row.default_factor}</td>
            <td className="px-3 py-2 text-right">
              <Input type="number" step="0.05" min={0.01} value={row.factor} onChange={(e) => { const v = [...rows]; v[i] = { ...row, factor: e.target.value }; setRows(v); }}
                     className="rounded-none font-mono-num text-right h-8" data-testid={`mat-input-${row.material}`} />
            </td>
            <td className="px-3 py-2 text-xs">
              <Input value={row.source || ""} onChange={(e) => { const v = [...rows]; v[i] = { ...row, source: e.target.value }; setRows(v); }}
                     className="rounded-none h-8 text-xs" />
            </td>
            <td className="px-3 py-2 text-xs">
              <Input value={row.notes || ""} onChange={(e) => { const v = [...rows]; v[i] = { ...row, notes: e.target.value }; setRows(v); }}
                     className="rounded-none h-8 text-xs" />
            </td>
          </tr>
        ))}</tbody>
      </table>
    </Panel>
  );
}

// ---------- Pressure Factors ----------
function PressureFactors() {
  const [rows, setRows] = useState([]);
  useEffect(() => { api.get("/admin/pressure-factors").then(r => setRows(r.data)); }, []);
  const save = async () => {
    try {
      await api.put("/admin/pressure-factors", rows.map(r => ({
        category: r.category, pressure_exponent: Number(r.pressure_exponent),
        enabled: !!r.enabled,
        minimum_factor: r.minimum_factor === "" || r.minimum_factor == null ? null : Number(r.minimum_factor),
        maximum_factor: r.maximum_factor === "" || r.maximum_factor == null ? null : Number(r.maximum_factor),
        source: r.source, notes: r.notes,
      })));
      toast.success("Saved");
    } catch (e) { toast.error("Failed"); }
  };
  return (
    <Panel title="Pressure Factor Settings" onSave={save} testId="save-pressure-btn"
           note="F_pressure = (P_target_abs / P_ref_abs)^p. Pressures are converted from barg to bara internally. Preliminary values — calibrate on data.">
      <table className="w-full data-table">
        <thead><tr>
          <th className="text-left px-3 py-2">Category</th>
          <th className="text-center px-3 py-2 w-20">Enabled</th>
          <th className="text-right px-3 py-2 w-32">Exponent p</th>
          <th className="text-right px-3 py-2 w-32">Min factor</th>
          <th className="text-right px-3 py-2 w-32">Max factor</th>
          <th className="text-right px-3 py-2">Defaults</th>
        </tr></thead>
        <tbody>{rows.map((row, i) => (
          <tr key={row.category}>
            <td className="px-3 py-2">{row.label}</td>
            <td className="px-3 py-2 text-center">
              <Switch checked={!!row.enabled} onCheckedChange={(v) => { const rr = [...rows]; rr[i] = { ...row, enabled: v }; setRows(rr); }} data-testid={`p-enabled-${row.category}`} />
            </td>
            <td className="px-3 py-2 text-right">
              <Input type="number" step="0.05" value={row.pressure_exponent} onChange={(e) => { const rr = [...rows]; rr[i] = { ...row, pressure_exponent: e.target.value }; setRows(rr); }}
                     className="rounded-none font-mono-num text-right h-8" data-testid={`p-exp-${row.category}`} />
            </td>
            <td className="px-3 py-2 text-right">
              <Input type="number" step="0.05" value={row.minimum_factor ?? ""} onChange={(e) => { const rr = [...rows]; rr[i] = { ...row, minimum_factor: e.target.value }; setRows(rr); }}
                     className="rounded-none font-mono-num text-right h-8" placeholder="—" />
            </td>
            <td className="px-3 py-2 text-right">
              <Input type="number" step="0.05" value={row.maximum_factor ?? ""} onChange={(e) => { const rr = [...rows]; rr[i] = { ...row, maximum_factor: e.target.value }; setRows(rr); }}
                     className="rounded-none font-mono-num text-right h-8" placeholder="—" />
            </td>
            <td className="px-3 py-2 text-right font-mono-num text-xs text-slate-500">exp={row.default_exponent} · {row.default_enabled ? "on" : "off"}</td>
          </tr>
        ))}</tbody>
      </table>
    </Panel>
  );
}

// ---------- Escalation Weights ----------
function EscalationWeights() {
  const [rows, setRows] = useState([]);
  useEffect(() => { api.get("/admin/escalation-weights").then(r => setRows(r.data)); }, []);
  const save = async () => {
    for (const r of rows) {
      if (Math.abs(Number(r.steel_weight) + Number(r.oil_weight) - 1) > 0.01) {
        toast.error(`Weights for ${r.label} must sum to 1.0`); return;
      }
    }
    try {
      await api.put("/admin/escalation-weights", rows.map(r => ({ category: r.category, steel_weight: Number(r.steel_weight), oil_weight: Number(r.oil_weight) })));
      toast.success("Saved");
    } catch (e) { toast.error("Failed"); }
  };
  return (
    <Panel title="Escalation Weights (Steel / Oil)" onSave={save} testId="save-weights-btn"
           note="Esc = 1 + steel_w × Δ%_steel + oil_w × Δ%_oil. Weights per category must sum to 1.0.">
      <table className="w-full data-table">
        <thead><tr>
          <th className="text-left px-3 py-2">Category</th>
          <th className="text-right px-3 py-2">Default Steel / Oil</th>
          <th className="text-right px-3 py-2 w-32">Steel</th>
          <th className="text-right px-3 py-2 w-32">Oil</th>
        </tr></thead>
        <tbody>{rows.map((row, i) => (
          <tr key={row.category}>
            <td className="px-3 py-2">{row.label}</td>
            <td className="px-3 py-2 text-right font-mono-num text-slate-500 text-xs">{row.default_steel} / {row.default_oil}</td>
            <td className="px-3 py-2 text-right">
              <Input type="number" step="0.05" min={0} max={1} value={row.steel_weight} onChange={(e) => { const v = [...rows]; v[i] = { ...row, steel_weight: e.target.value }; setRows(v); }}
                     className="rounded-none font-mono-num text-right h-8" data-testid={`steel-input-${row.category}`} />
            </td>
            <td className="px-3 py-2 text-right">
              <Input type="number" step="0.05" min={0} max={1} value={row.oil_weight} onChange={(e) => { const v = [...rows]; v[i] = { ...row, oil_weight: e.target.value }; setRows(v); }}
                     className="rounded-none font-mono-num text-right h-8" data-testid={`oil-input-${row.category}`} />
            </td>
          </tr>
        ))}</tbody>
      </table>
    </Panel>
  );
}

// ---------- Similarity Settings ----------
function SimilaritySettings() {
  const [cfg, setCfg] = useState(null);
  useEffect(() => { api.get("/admin/similarity-settings").then(r => setCfg(r.data)); }, []);
  const save = async () => {
    const ws = Number(cfg.w_size) + Number(cfg.w_subtype) + Number(cfg.w_material) + Number(cfg.w_pressure);
    if (Math.abs(ws - 1) > 0.01) { toast.error("Similarity weights must sum to 1.0"); return; }
    try {
      await api.put("/admin/similarity-settings", {
        alpha: Number(cfg.alpha), beta: Number(cfg.beta), gamma: Number(cfg.gamma),
        w_size: Number(cfg.w_size), w_subtype: Number(cfg.w_subtype),
        w_material: Number(cfg.w_material), w_pressure: Number(cfg.w_pressure),
        subtype_mismatch: Number(cfg.subtype_mismatch), min_similarity: Number(cfg.min_similarity),
        max_references: Number(cfg.max_references), min_references: Number(cfg.min_references),
        max_extrapolation_ratio: Number(cfg.max_extrapolation_ratio),
        atmospheric_pressure_bar: Number(cfg.atmospheric_pressure_bar),
        missing_material_factor_policy: cfg.missing_material_factor_policy || "exclude",
        missing_pressure_policy: cfg.missing_pressure_policy || "exclude",
      });
      toast.success("Saved");
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };
  if (!cfg) return <div className="text-sm text-slate-500">Loading…</div>;
  const setF = (k, v) => setCfg({ ...cfg, [k]: v });
  return (
    <Panel title="Similarity & Estimation Settings" onSave={save} testId="save-similarity-btn"
           note="Configure the weighted average of historical references. All parameters are user-calibratable.">
      <div className="grid grid-cols-3 gap-4">
        <NumField label="α (size decay)" value={cfg.alpha} onChange={(v) => setF("alpha", v)} step="0.1" />
        <NumField label="β (material decay)" value={cfg.beta} onChange={(v) => setF("beta", v)} step="0.1" />
        <NumField label="γ (pressure decay)" value={cfg.gamma} onChange={(v) => setF("gamma", v)} step="0.1" />
        <NumField label="w_size" value={cfg.w_size} onChange={(v) => setF("w_size", v)} step="0.05" />
        <NumField label="w_subtype" value={cfg.w_subtype} onChange={(v) => setF("w_subtype", v)} step="0.05" />
        <NumField label="w_material" value={cfg.w_material} onChange={(v) => setF("w_material", v)} step="0.05" />
        <NumField label="w_pressure" value={cfg.w_pressure} onChange={(v) => setF("w_pressure", v)} step="0.05" />
        <NumField label="Subtype mismatch value" value={cfg.subtype_mismatch} onChange={(v) => setF("subtype_mismatch", v)} step="0.05" />
        <NumField label="Min similarity" value={cfg.min_similarity} onChange={(v) => setF("min_similarity", v)} step="0.05" />
        <NumField label="Max references" value={cfg.max_references} onChange={(v) => setF("max_references", v)} step="1" />
        <NumField label="Min references" value={cfg.min_references} onChange={(v) => setF("min_references", v)} step="1" />
        <NumField label="Max extrapolation ratio" value={cfg.max_extrapolation_ratio} onChange={(v) => setF("max_extrapolation_ratio", v)} step="0.5" />
        <NumField label="Atmospheric pressure (bar)" value={cfg.atmospheric_pressure_bar} onChange={(v) => setF("atmospheric_pressure_bar", v)} step="0.001" />
        <div>
          <label className="text-xs uppercase tracking-wider text-slate-500">Missing material factor policy</label>
          <select value={cfg.missing_material_factor_policy} onChange={(e) => setF("missing_material_factor_policy", e.target.value)}
                  className="w-full h-9 border border-border px-2 text-sm mt-1 rounded-none bg-white">
            <option value="exclude">Exclude reference</option>
            <option value="block">Block estimate</option>
          </select>
        </div>
        <div>
          <label className="text-xs uppercase tracking-wider text-slate-500">Missing pressure policy</label>
          <select value={cfg.missing_pressure_policy} onChange={(e) => setF("missing_pressure_policy", e.target.value)}
                  className="w-full h-9 border border-border px-2 text-sm mt-1 rounded-none bg-white">
            <option value="exclude">Exclude reference</option>
            <option value="block">Block estimate</option>
          </select>
        </div>
      </div>
    </Panel>
  );
}

// ---------- helpers ----------
function Panel({ title, onSave, testId, note, children }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="font-heading text-lg font-medium text-slate-900">{title}</h2>
          {note && <p className="text-xs text-slate-500 mt-1 max-w-2xl">{note}</p>}
        </div>
        <Button onClick={onSave} className="rounded-none bg-[#002FA7] hover:bg-[#002480]" data-testid={testId}>Save</Button>
      </div>
      <div className="border border-border bg-white">{children}</div>
    </div>
  );
}

function NumField({ label, value, onChange, step = "0.01" }) {
  return (
    <div>
      <label className="text-xs uppercase tracking-wider text-slate-500">{label}</label>
      <Input type="number" step={step} value={value} onChange={(e) => onChange(e.target.value)} className="rounded-none font-mono-num h-9 mt-1" />
    </div>
  );
}
