import { useEffect, useState } from "react";
import { api, CAT_LABELS, MAT_LABELS, formatMoney } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AaceBadge } from "@/components/AaceBadge";
import { toast } from "sonner";

const CATEGORIES = Object.keys(CAT_LABELS);
const MATERIALS = Object.keys(MAT_LABELS);

const UNIT_BY_CAT = {
  column: "m3", reactor: "m3", heat_exchanger: "m2", storage_tank: "m3",
  pump: "m3/h", compressor: "m3/h", valve: "DN(mm)", instrumentation: "unit", other: "unit",
};

const POWER_CATS = ["pump", "compressor"];

export default function EquipmentRowDialog({ open, onOpenChange, project, row, onSaved }) {
  const [form, setForm] = useState({
    tag: "", category: "column", subtype: "", size: 0, size_unit: "m3",
    material: "carbon_steel", design_pressure_bar: "", design_temperature_c: "",
    power_kw: "", quantity: 1,
  });
  const [preview, setPreview] = useState(null);
  const [previewing, setPreviewing] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (row) {
      setForm({
        tag: row.tag || "", category: row.category, subtype: row.subtype || "",
        size: row.size, size_unit: row.size_unit, material: row.material,
        design_pressure_bar: row.design_pressure_bar ?? "",
        design_temperature_c: row.design_temperature_c ?? "",
        power_kw: row.power_kw ?? "", quantity: row.quantity || 1,
      });
    } else {
      setForm({
        tag: "", category: "column", subtype: "", size: 0, size_unit: "m3",
        material: "carbon_steel", design_pressure_bar: "", design_temperature_c: "",
        power_kw: "", quantity: 1,
      });
    }
    setPreview(null);
  }, [row, open]);

  const onCategoryChange = (cat) => {
    setForm((f) => ({ ...f, category: cat, size_unit: UNIT_BY_CAT[cat] || "unit" }));
  };

  const runPreview = async () => {
    if (!form.size || Number(form.size) <= 0) { toast.error("Size must be > 0"); return; }
    setPreviewing(true);
    try {
      const payload = {
        category: form.category,
        subtype: form.subtype || null,
        size: Number(form.size),
        material: form.material,
        power_kw: form.power_kw ? Number(form.power_kw) : null,
        target_year: project.target_year,
        output_currency: project.output_currency,
        quantity: Number(form.quantity) || 1,
      };
      const { data } = await api.post("/estimate", payload);
      setPreview(data);
    } catch (e) {
      toast.error("Preview failed");
    } finally {
      setPreviewing(false);
    }
  };

  const save = async () => {
    if (!form.size || Number(form.size) <= 0) { toast.error("Size must be > 0"); return; }
    setSaving(true);
    const payload = {
      tag: form.tag || null,
      category: form.category,
      subtype: form.subtype || null,
      size: Number(form.size),
      size_unit: form.size_unit,
      material: form.material,
      design_pressure_bar: form.design_pressure_bar === "" ? null : Number(form.design_pressure_bar),
      design_temperature_c: form.design_temperature_c === "" ? null : Number(form.design_temperature_c),
      power_kw: form.power_kw === "" ? null : Number(form.power_kw),
      quantity: Number(form.quantity) || 1,
    };
    try {
      if (row) {
        await api.put(`/projects/${project.id}/rows/${row.id}`, payload);
        toast.success("Row updated");
      } else {
        await api.post(`/projects/${project.id}/rows`, payload);
        toast.success("Row added");
      }
      onOpenChange(false);
      onSaved();
    } catch (e) {
      toast.error("Save failed");
    } finally {
      setSaving(false);
    }
  };

  const showPower = POWER_CATS.includes(form.category);
  const ccy = project.output_currency;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-none max-w-2xl">
        <DialogHeader>
          <DialogTitle className="font-heading">{row ? "Edit Equipment" : "Add Equipment"}</DialogTitle>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3 py-2">
          <div>
            <Label className="text-xs uppercase tracking-wider">Tag</Label>
            <Input data-testid="row-tag-input" value={form.tag} onChange={(e) => setForm({ ...form, tag: e.target.value })} placeholder="e.g., C-101" className="rounded-none mt-1" />
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
            <Label className="text-xs uppercase tracking-wider">Subtype</Label>
            <Input data-testid="row-subtype-input" value={form.subtype} onChange={(e) => setForm({ ...form, subtype: e.target.value })} placeholder="e.g., Shell & tube" className="rounded-none mt-1" />
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
            <Label className="text-xs uppercase tracking-wider">Size ({form.size_unit})</Label>
            <Input data-testid="row-size-input" type="number" value={form.size} onChange={(e) => setForm({ ...form, size: e.target.value })} className="rounded-none mt-1 font-mono-num" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider">Quantity</Label>
            <Input data-testid="row-quantity-input" type="number" min={1} value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} className="rounded-none mt-1 font-mono-num" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider">Design Pressure (bar)</Label>
            <Input data-testid="row-pressure-input" type="number" value={form.design_pressure_bar} onChange={(e) => setForm({ ...form, design_pressure_bar: e.target.value })} className="rounded-none mt-1 font-mono-num" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider">Design Temperature (°C)</Label>
            <Input data-testid="row-temp-input" type="number" value={form.design_temperature_c} onChange={(e) => setForm({ ...form, design_temperature_c: e.target.value })} className="rounded-none mt-1 font-mono-num" />
          </div>
          {showPower && (
            <div className="col-span-2">
              <Label className="text-xs uppercase tracking-wider">Power / HP (kW)</Label>
              <Input data-testid="row-power-input" type="number" value={form.power_kw} onChange={(e) => setForm({ ...form, power_kw: e.target.value })} className="rounded-none mt-1 font-mono-num" />
              <div className="text-[10px] text-slate-500 mt-1">For pumps/compressors, power is used as primary scaling variable if provided.</div>
            </div>
          )}
        </div>

        {preview && (
          <div className="border border-border bg-slate-50 p-4 mt-2" data-testid="preview-panel">
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs uppercase tracking-widest text-slate-500">Estimate Preview</div>
              <AaceBadge value={preview.aace_class} testId="preview-aace" />
            </div>
            {preview.no_reference ? (
              <div className="text-sm text-amber-700">No historical references match this category. Add reference equipment to the repository first.</div>
            ) : (
              <div className="grid grid-cols-4 gap-3">
                <PreviewCell label="Expected" value={formatMoney(preview.total_expected, ccy)} highlight />
                <PreviewCell label="Low" value={formatMoney(preview.total_low, ccy)} />
                <PreviewCell label="High" value={formatMoney(preview.total_high, ccy)} />
                <PreviewCell label="References" value={preview.references_used} />
              </div>
            )}
            <div className="text-[10px] text-slate-500 mt-2 font-mono-num">
              Escalation factor: {preview.escalation_factor} · Qty: {preview.quantity}
            </div>
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
