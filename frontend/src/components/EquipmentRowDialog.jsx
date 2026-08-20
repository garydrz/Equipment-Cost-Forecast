import { useEffect, useState } from "react";
import { api, CAT_LABELS, MAT_LABELS, FIELD_RULES, formatMoney, getMeta } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Warning } from "@phosphor-icons/react";
import { toast } from "sonner";

const CATEGORIES = Object.keys(CAT_LABELS);
const MATERIALS = Object.keys(MAT_LABELS);

const EMPTY = {
  tag: "", category: "column", subtype: "",
  size: "", weight_kg: "", power_kw: "",
  flow_rate_m3_h: "", head_m: "", thermal_duty_kw: "", fuel_flow_kg_h: "",
  material: "carbon_steel",
  design_pressure_bar: "", design_temperature_c: "",
  quantity: 1,
};

export default function EquipmentRowDialog({ open, onOpenChange, project, row, onSaved }) {
  const [form, setForm] = useState(EMPTY);
  const [subtypesByCat, setSubtypesByCat] = useState({});
  const [preview, setPreview] = useState(null);
  const [previewing, setPreviewing] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => { getMeta().then((m) => setSubtypesByCat(m.subtypes || {})); }, []);

  useEffect(() => {
    if (row) {
      setForm({
        tag: row.tag || "", category: row.category, subtype: row.subtype || "",
        size: row.size ?? "", weight_kg: row.weight_kg ?? "", power_kw: row.power_kw ?? "",
        flow_rate_m3_h: row.flow_rate_m3_h ?? "", head_m: row.head_m ?? "",
        thermal_duty_kw: row.thermal_duty_kw ?? "", fuel_flow_kg_h: row.fuel_flow_kg_h ?? "",
        material: row.material,
        design_pressure_bar: row.design_pressure_bar ?? "",
        design_temperature_c: row.design_temperature_c ?? "",
        quantity: row.quantity || 1,
      });
    } else {
      setForm(EMPTY);
    }
    setPreview(null);
  }, [row, open]);

  const rules = FIELD_RULES[form.category] || FIELD_RULES.other;
  const subtypes = subtypesByCat[form.category] || [];

  const onCategoryChange = (cat) => {
    const r = FIELD_RULES[cat] || FIELD_RULES.other;
    setForm((f) => ({
      ...f, category: cat, subtype: "", // reset subtype
      weight_kg: r.weight_kg ? f.weight_kg : "",
      power_kw: r.power_kw ? f.power_kw : "",
      flow_rate_m3_h: r.flow_head ? f.flow_rate_m3_h : "",
      head_m: r.flow_head ? f.head_m : "",
      thermal_duty_kw: r.thermal_duty ? f.thermal_duty_kw : "",
      fuel_flow_kg_h: r.thermal_duty ? f.fuel_flow_kg_h : "",
      design_pressure_bar: r.pressure ? f.design_pressure_bar : "",
      design_temperature_c: r.temperature ? f.design_temperature_c : "",
    }));
    setPreview(null);
  };

  const buildPayload = () => {
    let size = form.size;
    // for pump, use flow_rate as size fallback; for burner, use thermal_duty
    if (rules.flow_head && !size && form.flow_rate_m3_h) size = form.flow_rate_m3_h;
    if (rules.thermal_duty && !size && form.thermal_duty_kw) size = form.thermal_duty_kw;
    return {
      tag: form.tag || null, category: form.category, subtype: form.subtype,
      size: size === "" ? null : Number(size),
      size_unit: rules.unit === "m³" ? "m3" : rules.unit === "m²" ? "m2" : rules.unit === "m³/h" ? "m3/h" : rules.unit,
      weight_kg: rules.weight_kg && form.weight_kg !== "" ? Number(form.weight_kg) : null,
      power_kw: rules.power_kw && form.power_kw !== "" ? Number(form.power_kw) : null,
      flow_rate_m3_h: rules.flow_head && form.flow_rate_m3_h !== "" ? Number(form.flow_rate_m3_h) : null,
      head_m: rules.flow_head && form.head_m !== "" ? Number(form.head_m) : null,
      thermal_duty_kw: rules.thermal_duty && form.thermal_duty_kw !== "" ? Number(form.thermal_duty_kw) : null,
      fuel_flow_kg_h: rules.thermal_duty && form.fuel_flow_kg_h !== "" ? Number(form.fuel_flow_kg_h) : null,
      material: form.material,
      design_pressure_bar: rules.pressure && form.design_pressure_bar !== "" ? Number(form.design_pressure_bar) : null,
      design_temperature_c: rules.temperature && form.design_temperature_c !== "" ? Number(form.design_temperature_c) : null,
      quantity: Number(form.quantity) || 1,
    };
  };

  const runPreview = async () => {
    if (!form.subtype) { toast.error("Subtype required"); return; }
    setPreviewing(true);
    try {
      const p = buildPayload();
      const { data } = await api.post("/estimate", {
        category: p.category, subtype: p.subtype,
        size: p.size, weight_kg: p.weight_kg, power_kw: p.power_kw,
        flow_rate_m3_h: p.flow_rate_m3_h, head_m: p.head_m,
        thermal_duty_kw: p.thermal_duty_kw,
        material: p.material, design_pressure_bar: p.design_pressure_bar,
        target_year: project.target_year, output_currency: project.output_currency,
        quantity: p.quantity,
      });
      setPreview(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Preview failed");
    } finally { setPreviewing(false); }
  };

  const save = async () => {
    if (!form.subtype) { toast.error("Subtype required"); return; }
    setSaving(true);
    try {
      const p = buildPayload();
      if (row) {
        await api.put(`/projects/${project.id}/rows/${row.id}`, p);
        toast.success("Row updated");
      } else {
        await api.post(`/projects/${project.id}/rows`, p);
        toast.success("Row added");
      }
      onOpenChange(false); onSaved();
    } catch (e) { toast.error(e?.response?.data?.detail || "Save failed"); }
    finally { setSaving(false); }
  };

  const ccy = project.output_currency;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-none max-w-3xl max-h-[92vh] overflow-y-auto">
        <DialogHeader><DialogTitle className="font-heading">{row ? "Edit Equipment" : "Add Equipment"}</DialogTitle></DialogHeader>

        <div className="grid grid-cols-3 gap-3 py-2">
          <div>
            <Label className="text-xs uppercase tracking-wider">Tag</Label>
            <Input data-testid="row-tag-input" value={form.tag} onChange={(e) => setForm({ ...form, tag: e.target.value })} className="rounded-none mt-1" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider">Category</Label>
            <Select value={form.category} onValueChange={onCategoryChange}>
              <SelectTrigger data-testid="row-category-select" className="rounded-none mt-1"><SelectValue /></SelectTrigger>
              <SelectContent>
                {CATEGORIES.map((c) => <SelectItem key={c} value={c}>{CAT_LABELS[c]}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider">Subtype *</Label>
            <Select value={form.subtype} onValueChange={(v) => setForm({ ...form, subtype: v })}>
              <SelectTrigger data-testid="row-subtype-select" className="rounded-none mt-1"><SelectValue placeholder="Select…" /></SelectTrigger>
              <SelectContent>
                {subtypes.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider">Material</Label>
            <Select value={form.material} onValueChange={(v) => setForm({ ...form, material: v })}>
              <SelectTrigger data-testid="row-material-select" className="rounded-none mt-1"><SelectValue /></SelectTrigger>
              <SelectContent>
                {MATERIALS.map((m) => <SelectItem key={m} value={m}>{MAT_LABELS[m]}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          {!rules.flow_head && !rules.thermal_duty && (
            <div>
              <Label className="text-xs uppercase tracking-wider">{rules.size_label} ({rules.unit})</Label>
              <Input data-testid="row-size-input" type="number" value={form.size} onChange={(e) => setForm({ ...form, size: e.target.value })} className="rounded-none mt-1 font-mono-num" />
            </div>
          )}

          <div>
            <Label className="text-xs uppercase tracking-wider">Quantity</Label>
            <Input data-testid="row-quantity-input" type="number" min={1} value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} className="rounded-none mt-1 font-mono-num" />
          </div>

          {rules.flow_head && (
            <>
              <div>
                <Label className="text-xs uppercase tracking-wider">Flow Rate (m³/h) *</Label>
                <Input data-testid="row-flow-input" type="number" value={form.flow_rate_m3_h} onChange={(e) => setForm({ ...form, flow_rate_m3_h: e.target.value })} className="rounded-none mt-1 font-mono-num" />
              </div>
              <div>
                <Label className="text-xs uppercase tracking-wider">Head (m) *</Label>
                <Input data-testid="row-head-input" type="number" value={form.head_m} onChange={(e) => setForm({ ...form, head_m: e.target.value })} className="rounded-none mt-1 font-mono-num" />
              </div>
              <div>
                <Label className="text-xs uppercase tracking-wider">Power (kW)</Label>
                <Input data-testid="row-power-input" type="number" value={form.power_kw} onChange={(e) => setForm({ ...form, power_kw: e.target.value })} className="rounded-none mt-1 font-mono-num" />
              </div>
            </>
          )}

          {rules.thermal_duty && (
            <>
              <div>
                <Label className="text-xs uppercase tracking-wider">Thermal Duty (kW) *</Label>
                <Input data-testid="row-duty-input" type="number" value={form.thermal_duty_kw} onChange={(e) => setForm({ ...form, thermal_duty_kw: e.target.value })} className="rounded-none mt-1 font-mono-num" />
              </div>
              <div>
                <Label className="text-xs uppercase tracking-wider">Fuel Flow (kg/h)</Label>
                <Input type="number" value={form.fuel_flow_kg_h} onChange={(e) => setForm({ ...form, fuel_flow_kg_h: e.target.value })} className="rounded-none mt-1 font-mono-num" />
              </div>
            </>
          )}

          {rules.weight_kg && (
            <div>
              <Label className="text-xs uppercase tracking-wider">Equipment Weight (kg)</Label>
              <Input data-testid="row-weight-input" type="number" value={form.weight_kg} onChange={(e) => setForm({ ...form, weight_kg: e.target.value })} className="rounded-none mt-1 font-mono-num" />
            </div>
          )}

          {rules.power_kw && !rules.flow_head && (
            <div>
              <Label className="text-xs uppercase tracking-wider">Power (kW)</Label>
              <Input data-testid="row-power-input" type="number" value={form.power_kw} onChange={(e) => setForm({ ...form, power_kw: e.target.value })} className="rounded-none mt-1 font-mono-num" />
            </div>
          )}

          {rules.pressure && (
            <div>
              <Label className="text-xs uppercase tracking-wider">Design Pressure (barg)</Label>
              <Input data-testid="row-pressure-input" type="number" value={form.design_pressure_bar} onChange={(e) => setForm({ ...form, design_pressure_bar: e.target.value })} className="rounded-none mt-1 font-mono-num" />
            </div>
          )}

          {rules.temperature && (
            <div>
              <Label className="text-xs uppercase tracking-wider">Design Temperature (°C)</Label>
              <Input data-testid="row-temp-input" type="number" value={form.design_temperature_c} onChange={(e) => setForm({ ...form, design_temperature_c: e.target.value })} className="rounded-none mt-1 font-mono-num" />
            </div>
          )}
        </div>

        {preview && (
          <div className="border border-border bg-slate-50 p-4 mt-2 max-h-72 overflow-y-auto" data-testid="preview-panel">
            <div className="flex items-center justify-between mb-3">
              <div className="text-xs uppercase tracking-widest text-slate-500">Estimate Preview</div>
              <div className="text-xs font-mono-num text-slate-500">{preview.model_version} · {preview.confidence_level}% CI</div>
            </div>
            {!preview.estimate_available ? (
              <div className="text-sm text-amber-700 flex items-start gap-2">
                <Warning size={16} className="mt-0.5" />
                <div>
                  <div className="font-medium">Estimate unavailable</div>
                  {(preview.errors || []).map((e, i) => <div key={i} className="text-xs">• {e}</div>)}
                </div>
              </div>
            ) : (
              <>
                <div className="grid grid-cols-4 gap-3">
                  <PC label="Expected" value={formatMoney(preview.total_expected, ccy)} highlight />
                  <PC label="Low" value={preview.total_low != null ? formatMoney(preview.total_low, ccy) : "—"} />
                  <PC label="High" value={preview.total_high != null ? formatMoney(preview.total_high, ccy) : "—"} />
                  <PC label="Refs used" value={`${preview.references_used}/${preview.candidate_references}`} />
                </div>
                <div className="grid grid-cols-3 gap-3 mt-3 text-xs">
                  <div><span className="text-slate-500 uppercase tracking-wider">Primary variable</span><div className="font-mono-num text-slate-900">{preview.scaling_variable} = {preview.scaling_variable_value} {preview.scaling_variable_unit}</div></div>
                  <div><span className="text-slate-500 uppercase tracking-wider">σ sample</span><div className="font-mono-num text-slate-900">{preview.sigma_sample != null ? formatMoney(preview.sigma_sample, ccy) : "—"}</div></div>
                  <div><span className="text-slate-500 uppercase tracking-wider">Neff</span><div className="font-mono-num text-slate-900">{preview.effective_sample_size}</div></div>
                </div>
                {preview.warnings?.length > 0 && (
                  <div className="mt-2 text-[11px] text-amber-700 space-y-0.5">
                    {preview.warnings.slice(0, 4).map((w, i) => <div key={i}>⚠ {w}</div>)}
                  </div>
                )}
              </>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" className="rounded-none" onClick={runPreview} disabled={previewing || !form.subtype} data-testid="preview-btn">
            {previewing ? "Estimating…" : "Preview Estimate"}
          </Button>
          <Button variant="outline" className="rounded-none" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button className="rounded-none bg-[#002FA7] hover:bg-[#002480] text-white" onClick={save} disabled={saving || !form.subtype} data-testid="save-row-btn">
            {saving ? "Saving…" : (row ? "Save Changes" : "Add Row")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PC({ label, value, highlight }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest text-slate-500">{label}</div>
      <div className={`font-mono-num text-sm ${highlight ? "text-[#002FA7] font-semibold" : "text-slate-900"}`}>{value}</div>
    </div>
  );
}
