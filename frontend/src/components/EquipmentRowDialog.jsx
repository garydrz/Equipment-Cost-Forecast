import { useEffect, useState } from "react";
import { api, CAT_LABELS, MAT_LABELS, FIELD_RULES, formatMoney } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AaceBadge } from "@/components/AaceBadge";
import { Warning } from "@phosphor-icons/react";
import { toast } from "sonner";

const CATEGORIES = Object.keys(CAT_LABELS);
const MATERIALS = Object.keys(MAT_LABELS);

const EMPTY = {
  tag: "", category: "column", subtype: "",
  size: "", weight_kg: "", power_kw: "",
  material: "carbon_steel",
  design_pressure_bar: "", design_temperature_c: "",
  quantity: 1,
};

export default function EquipmentRowDialog({ open, onOpenChange, project, row, onSaved }) {
  const [form, setForm] = useState(EMPTY);
  const [preview, setPreview] = useState(null);
  const [previewing, setPreviewing] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (row) {
      setForm({
        tag: row.tag || "", category: row.category, subtype: row.subtype || "",
        size: row.size ?? "", weight_kg: row.weight_kg ?? "", power_kw: row.power_kw ?? "",
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

  // Clear disallowed fields when category changes
  const onCategoryChange = (cat) => {
    const r = FIELD_RULES[cat] || FIELD_RULES.other;
    setForm((f) => ({
      ...f,
      category: cat,
      weight_kg: r.weight_kg ? f.weight_kg : "",
      power_kw: r.power_kw ? f.power_kw : "",
      design_pressure_bar: r.pressure ? f.design_pressure_bar : "",
      design_temperature_c: r.temperature ? f.design_temperature_c : "",
    }));
    setPreview(null);
  };

  const buildPayload = () => ({
    tag: form.tag || null,
    category: form.category,
    subtype: form.subtype || null,
    size: form.size === "" ? null : Number(form.size),
    size_unit: rules.unit === "m³" ? "m3" : rules.unit === "m²" ? "m2" : rules.unit === "m³/h" ? "m3/h" : rules.unit,
    weight_kg: rules.weight_kg && form.weight_kg !== "" ? Number(form.weight_kg) : null,
    power_kw: rules.power_kw && form.power_kw !== "" ? Number(form.power_kw) : null,
    material: form.material,
    design_pressure_bar: rules.pressure && form.design_pressure_bar !== "" ? Number(form.design_pressure_bar) : null,
    design_temperature_c: rules.temperature && form.design_temperature_c !== "" ? Number(form.design_temperature_c) : null,
    quantity: Number(form.quantity) || 1,
  });

  const runPreview = async () => {
    if (!form.size || Number(form.size) <= 0) { toast.error("Size must be > 0"); return; }
    setPreviewing(true);
    try {
      const p = buildPayload();
      const { data } = await api.post("/estimate", {
        category: p.category, subtype: p.subtype,
        size: p.size, weight_kg: p.weight_kg, power_kw: p.power_kw,
        material: p.material, design_pressure_bar: p.design_pressure_bar,
        target_year: project.target_year, output_currency: project.output_currency,
        quantity: p.quantity,
      });
      setPreview(data);
    } catch (e) {
      toast.error("Preview failed");
    } finally { setPreviewing(false); }
  };

  const save = async () => {
    if (!form.size || Number(form.size) <= 0) { toast.error("Size must be > 0"); return; }
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
      onOpenChange(false);
      onSaved();
    } catch (e) { toast.error("Save failed"); }
    finally { setSaving(false); }
  };

  const ccy = project.output_currency;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-none max-w-3xl">
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
            <Label className="text-xs uppercase tracking-wider">Material</Label>
            <Select value={form.material} onValueChange={(v) => setForm({ ...form, material: v })}>
              <SelectTrigger data-testid="row-material-select" className="rounded-none mt-1"><SelectValue /></SelectTrigger>
              <SelectContent>
                {MATERIALS.map((m) => <SelectItem key={m} value={m}>{MAT_LABELS[m]}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider">Subtype</Label>
            <Input data-testid="row-subtype-input" value={form.subtype} onChange={(e) => setForm({ ...form, subtype: e.target.value })} className="rounded-none mt-1" />
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider">{rules.size_label} ({rules.unit})</Label>
            <Input data-testid="row-size-input" type="number" value={form.size} onChange={(e) => setForm({ ...form, size: e.target.value })} className="rounded-none mt-1 font-mono-num" />
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider">Quantity</Label>
            <Input data-testid="row-quantity-input" type="number" min={1} value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} className="rounded-none mt-1 font-mono-num" />
          </div>

          {rules.weight_kg && (
            <div>
              <Label className="text-xs uppercase tracking-wider">Equipment Weight (kg)</Label>
              <Input data-testid="row-weight-input" type="number" value={form.weight_kg} onChange={(e) => setForm({ ...form, weight_kg: e.target.value })} className="rounded-none mt-1 font-mono-num" />
              <div className="text-[10px] text-slate-500 mt-1">Primary scaling variable for this category</div>
            </div>
          )}

          {rules.power_kw && (
            <div>
              <Label className="text-xs uppercase tracking-wider">Power (kW)</Label>
              <Input data-testid="row-power-input" type="number" value={form.power_kw} onChange={(e) => setForm({ ...form, power_kw: e.target.value })} className="rounded-none mt-1 font-mono-num" />
              <div className="text-[10px] text-slate-500 mt-1">Primary scaling variable</div>
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
              <div className="text-xs font-mono-num text-slate-500">Model {preview.model_version}</div>
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
                  <PreviewCell label="Expected" value={formatMoney(preview.total_expected, ccy)} highlight />
                  <PreviewCell label="Low" value={formatMoney(preview.total_low, ccy)} />
                  <PreviewCell label="High" value={formatMoney(preview.total_high, ccy)} />
                  <PreviewCell label="Refs (used/candidates)" value={`${preview.references_used}/${preview.candidate_references}`} />
                </div>
                <div className="grid grid-cols-3 gap-3 mt-3 text-xs">
                  <div>
                    <span className="text-slate-500 uppercase tracking-wider">Primary variable</span>
                    <div className="font-mono-num text-slate-900">{preview.scaling_variable} = {preview.scaling_variable_value} {preview.scaling_variable_unit} {preview.scaling_variable_is_fallback && <span className="text-amber-600">(fallback)</span>}</div>
                  </div>
                  <div>
                    <span className="text-slate-500 uppercase tracking-wider">Eff. sample size</span>
                    <div className="font-mono-num text-slate-900">{preview.effective_sample_size}</div>
                  </div>
                  <div>
                    <span className="text-slate-500 uppercase tracking-wider">Escalation</span>
                    <div className="font-mono-num text-slate-900">{preview.escalation_factor}</div>
                  </div>
                </div>
                {preview.warnings?.length > 0 && (
                  <div className="mt-2 text-[11px] text-amber-700 space-y-0.5">
                    {preview.warnings.slice(0, 3).map((w, i) => <div key={i}>⚠ {w}</div>)}
                  </div>
                )}
              </>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" className="rounded-none" onClick={runPreview} disabled={previewing} data-testid="preview-btn">
            {previewing ? "Estimating…" : "Preview Estimate"}
          </Button>
          <Button variant="outline" className="rounded-none" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button className="rounded-none bg-[#002FA7] hover:bg-[#002480] text-white" onClick={save} disabled={saving} data-testid="save-row-btn">
            {saving ? "Saving…" : (row ? "Save Changes" : "Add Row")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PreviewCell({ label, value, highlight }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest text-slate-500">{label}</div>
      <div className={`font-mono-num text-sm ${highlight ? "text-[#002FA7] font-semibold" : "text-slate-900"}`}>{value}</div>
    </div>
  );
}
