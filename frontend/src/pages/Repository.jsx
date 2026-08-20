import { useEffect, useState } from "react";
import { api, CAT_LABELS, MAT_LABELS, formatMoney, getMeta } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Plus, Trash, PencilSimple, MagnifyingGlass, ArrowsClockwise } from "@phosphor-icons/react";
import { toast } from "sonner";

const CATEGORIES = Object.keys(CAT_LABELS);
const MATERIALS = Object.keys(MAT_LABELS);
const UNIT_BY_CAT = {
  column: "m3", reactor: "m3", vessel: "m3", heat_exchanger: "m2", storage_tank: "m3",
  pump: "m3/h", compressor: "m3/h", valve: "mm", instrumentation: "unit", burner: "kW", other: "unit",
};
const POWER_CATS = ["pump", "compressor"];
const FLOW_HEAD_CATS = ["pump"];
const DUTY_CATS = ["burner"];

const EMPTY = {
  category: "column", subtype: "", size: "", size_unit: "m3",
  weight_kg: "", material: "carbon_steel",
  design_pressure_bar: "", design_temperature_c: "", power_kw: "",
  flow_rate_m3_h: "", head_m: "", pump_efficiency: "", fluid_density_kg_m3: "",
  thermal_duty_kw: "", fuel_flow_kg_h: "",
  year: new Date().getFullYear() - 1, cost_original: "", currency: "EUR",
  vendor_country: "", install_country: "", notes: "",
};

export default function Repository() {
  const [items, setItems] = useState([]);
  const [filterCat, setFilterCat] = useState("all");
  const [q, setQ] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [subtypesByCat, setSubtypesByCat] = useState({});

  useEffect(() => { getMeta().then((m) => setSubtypesByCat(m.subtypes || {})); }, []);

  const load = async () => {
    try {
      const params = {};
      if (filterCat !== "all") params.category = filterCat;
      if (q) params.q = q;
      const { data } = await api.get("/equipment", { params });
      setItems(data);
    } catch (e) {
      toast.error("Failed to load repository");
    }
  };

  useEffect(() => { load(); }, [filterCat, q]);

  const openAdd = () => {
    setEditing(null);
    setForm({ ...EMPTY });
    setDialogOpen(true);
  };

  const openEdit = (r) => {
    setEditing(r);
    setForm({
      category: r.category, subtype: r.subtype || "", size: r.size,
      size_unit: r.size_unit, weight_kg: r.weight_kg ?? "", material: r.material,
      design_pressure_bar: r.design_pressure_bar ?? "",
      design_temperature_c: r.design_temperature_c ?? "",
      power_kw: r.power_kw ?? "",
      flow_rate_m3_h: r.flow_rate_m3_h ?? "", head_m: r.head_m ?? "",
      pump_efficiency: r.pump_efficiency ?? "", fluid_density_kg_m3: r.fluid_density_kg_m3 ?? "",
      thermal_duty_kw: r.thermal_duty_kw ?? "", fuel_flow_kg_h: r.fuel_flow_kg_h ?? "",
      year: r.year, cost_original: r.cost_original,
      currency: r.currency, vendor_country: r.vendor_country || "",
      install_country: r.install_country || "", notes: r.notes || "",
    });
    setDialogOpen(true);
  };

  const save = async () => {
    if (!form.subtype) { toast.error("Subtype required"); return; }
    // For pump/burner, size can be derived from flow_rate/thermal_duty
    let sizeVal = form.size;
    if (FLOW_HEAD_CATS.includes(form.category) && !sizeVal && form.flow_rate_m3_h) sizeVal = form.flow_rate_m3_h;
    if (DUTY_CATS.includes(form.category) && !sizeVal && form.thermal_duty_kw) sizeVal = form.thermal_duty_kw;
    if (!sizeVal || Number(sizeVal) <= 0) { toast.error("Size (or Flow rate / Thermal duty) required"); return; }
    if (!form.cost_original || Number(form.cost_original) <= 0) { toast.error("Cost required"); return; }
    const payload = {
      category: form.category,
      subtype: form.subtype,
      size: Number(sizeVal),
      size_unit: form.size_unit || UNIT_BY_CAT[form.category] || "unit",
      weight_kg: form.weight_kg === "" ? null : Number(form.weight_kg),
      material: form.material,
      design_pressure_bar: form.design_pressure_bar === "" ? null : Number(form.design_pressure_bar),
      design_temperature_c: form.design_temperature_c === "" ? null : Number(form.design_temperature_c),
      power_kw: form.power_kw === "" ? null : Number(form.power_kw),
      flow_rate_m3_h: form.flow_rate_m3_h === "" ? null : Number(form.flow_rate_m3_h),
      head_m: form.head_m === "" ? null : Number(form.head_m),
      pump_efficiency: form.pump_efficiency === "" ? null : Number(form.pump_efficiency),
      fluid_density_kg_m3: form.fluid_density_kg_m3 === "" ? null : Number(form.fluid_density_kg_m3),
      thermal_duty_kw: form.thermal_duty_kw === "" ? null : Number(form.thermal_duty_kw),
      fuel_flow_kg_h: form.fuel_flow_kg_h === "" ? null : Number(form.fuel_flow_kg_h),
      year: Number(form.year),
      cost_original: Number(form.cost_original),
      currency: form.currency,
      vendor_country: form.vendor_country || null,
      install_country: form.install_country || null,
      notes: form.notes || null,
    };
    try {
      if (editing) {
        await api.put(`/equipment/${editing.id}`, payload);
        toast.success("Updated");
      } else {
        await api.post("/equipment", payload);
        toast.success("Added to repository");
      }
      setDialogOpen(false);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    }
  };

  const remove = async (rid) => {
    if (!window.confirm("Delete this equipment record?")) return;
    try {
      await api.delete(`/equipment/${rid}`);
      toast.success("Deleted");
      load();
    } catch (e) { toast.error("Delete failed"); }
  };

  const migrate = async () => {
    if (!window.confirm("Run subtype migration to canonical values?")) return;
    try {
      const { data } = await api.post("/equipment/migrate-subtypes");
      toast.success(`Migrated ${data.updated} record(s). ${data.needs_review.length} need review.`);
      load();
    } catch (e) { toast.error("Migration failed"); }
  };

  const onCategoryChange = (cat) => {
    setForm((f) => ({ ...f, category: cat, subtype: "", size_unit: UNIT_BY_CAT[cat] || "unit" }));
  };

  const showPower = POWER_CATS.includes(form.category);
  const showFlowHead = FLOW_HEAD_CATS.includes(form.category);
  const showDuty = DUTY_CATS.includes(form.category);
  const subtypes = subtypesByCat[form.category] || [];

  return (
    <div className="p-8 max-w-7xl">
      <div className="flex items-end justify-between mb-6">
        <div>
          <div className="text-xs uppercase tracking-[0.2em] text-slate-500 mb-2">Data</div>
          <h1 className="font-heading text-3xl font-semibold tracking-tight text-slate-900 klein-underline">Historical Repository</h1>
          <p className="text-sm text-slate-600 mt-3 max-w-2xl">Reference database used to generate parametric cost estimates via AACE capacity factor method.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={migrate} className="rounded-none h-10" data-testid="migrate-btn">
            <ArrowsClockwise size={14} className="mr-2" /> Migrate Subtypes
          </Button>
          <Button onClick={openAdd} className="rounded-none bg-[#002FA7] hover:bg-[#002480] text-white h-10 px-5" data-testid="add-equipment-record-btn">
            <Plus size={16} className="mr-2" /> Add Record
          </Button>
        </div>
      </div>

      <div className="flex gap-3 mb-4">
        <div className="w-64">
          <Select value={filterCat} onValueChange={setFilterCat}>
            <SelectTrigger className="rounded-none" data-testid="repo-cat-filter"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Categories</SelectItem>
              {CATEGORIES.map((c) => <SelectItem key={c} value={c}>{CAT_LABELS[c]}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="relative flex-1 max-w-md">
          <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search subtype, notes, vendor…" className="rounded-none pl-9" data-testid="repo-search-input" />
        </div>
      </div>

      <div className="border border-border bg-white overflow-x-auto">
        <table className="w-full data-table" data-testid="repo-table">
          <thead>
            <tr>
              <th className="text-left px-3 py-2.5">Category</th>
              <th className="text-left px-3 py-2.5">Subtype</th>
              <th className="text-right px-3 py-2.5">Size</th>
              <th className="text-left px-3 py-2.5">Material</th>
              <th className="text-right px-3 py-2.5">Power</th>
              <th className="text-right px-3 py-2.5">Year</th>
              <th className="text-right px-3 py-2.5">Cost</th>
              <th className="text-center px-3 py-2.5">Ccy</th>
              <th className="text-left px-3 py-2.5">Notes</th>
              <th className="px-2 py-2.5"></th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && <tr><td colSpan={10} className="text-center py-8 text-slate-500 text-sm">No records.</td></tr>}
            {items.map((r) => (
              <tr key={r.id} data-testid={`repo-row-${r.id}`}>
                <td className="px-3 py-2 text-slate-800">{CAT_LABELS[r.category]}</td>
                <td className="px-3 py-2 text-slate-600 text-xs">{r.subtype || "—"}</td>
                <td className="px-3 py-2 text-right font-mono-num text-slate-900">{r.size} <span className="text-slate-400 text-xs">{r.size_unit}</span></td>
                <td className="px-3 py-2 text-slate-600 text-xs">{MAT_LABELS[r.material]}</td>
                <td className="px-3 py-2 text-right font-mono-num text-xs">{r.power_kw ? `${r.power_kw} kW` : "—"}</td>
                <td className="px-3 py-2 text-right font-mono-num">{r.year}</td>
                <td className="px-3 py-2 text-right font-mono-num text-slate-900">{formatMoney(r.cost_original, r.currency)}</td>
                <td className="px-3 py-2 text-center font-mono-num text-xs">{r.currency}</td>
                <td className="px-3 py-2 text-xs text-slate-600 max-w-xs truncate">{r.notes || "—"}</td>
                <td className="px-2 py-2 text-right">
                  <button onClick={() => openEdit(r)} className="text-slate-400 hover:text-slate-900 mr-2" data-testid={`edit-repo-${r.id}`}><PencilSimple size={14} /></button>
                  <button onClick={() => remove(r.id)} className="text-slate-400 hover:text-red-600" data-testid={`delete-repo-${r.id}`}><Trash size={14} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="rounded-none max-w-3xl">
          <DialogHeader><DialogTitle className="font-heading">{editing ? "Edit" : "Add"} Historical Equipment</DialogTitle></DialogHeader>
          <div className="grid grid-cols-3 gap-3 py-2 max-h-[70vh] overflow-y-auto pr-1">
            <div>
              <Label className="text-xs uppercase tracking-wider">Category</Label>
              <Select value={form.category} onValueChange={onCategoryChange}>
                <SelectTrigger className="rounded-none mt-1" data-testid="repo-form-cat"><SelectValue /></SelectTrigger>
                <SelectContent>{CATEGORIES.map((c) => <SelectItem key={c} value={c}>{CAT_LABELS[c]}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider">Subtype *</Label>
              <Select value={form.subtype} onValueChange={(v) => setForm({ ...form, subtype: v })}>
                <SelectTrigger className="rounded-none mt-1" data-testid="repo-form-subtype"><SelectValue placeholder="Select…" /></SelectTrigger>
                <SelectContent>{subtypes.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider">Material</Label>
              <Select value={form.material} onValueChange={(v) => setForm({ ...form, material: v })}>
                <SelectTrigger className="rounded-none mt-1" data-testid="repo-form-material"><SelectValue /></SelectTrigger>
                <SelectContent>{MATERIALS.map((m) => <SelectItem key={m} value={m}>{MAT_LABELS[m]}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider">Size ({form.size_unit})</Label>
              <Input type="number" value={form.size} onChange={(e) => setForm({ ...form, size: e.target.value })} className="rounded-none mt-1 font-mono-num" data-testid="repo-form-size" />
            </div>
            {showFlowHead && (
              <>
                <div>
                  <Label className="text-xs uppercase tracking-wider">Flow Rate (m³/h) *</Label>
                  <Input type="number" value={form.flow_rate_m3_h} onChange={(e) => setForm({ ...form, flow_rate_m3_h: e.target.value })} className="rounded-none mt-1 font-mono-num" />
                </div>
                <div>
                  <Label className="text-xs uppercase tracking-wider">Head (m) *</Label>
                  <Input type="number" value={form.head_m} onChange={(e) => setForm({ ...form, head_m: e.target.value })} className="rounded-none mt-1 font-mono-num" />
                </div>
              </>
            )}
            {showDuty && (
              <>
                <div>
                  <Label className="text-xs uppercase tracking-wider">Thermal Duty (kW) *</Label>
                  <Input type="number" value={form.thermal_duty_kw} onChange={(e) => setForm({ ...form, thermal_duty_kw: e.target.value })} className="rounded-none mt-1 font-mono-num" />
                </div>
                <div>
                  <Label className="text-xs uppercase tracking-wider">Fuel Flow (kg/h)</Label>
                  <Input type="number" value={form.fuel_flow_kg_h} onChange={(e) => setForm({ ...form, fuel_flow_kg_h: e.target.value })} className="rounded-none mt-1 font-mono-num" />
                </div>
              </>
            )}
            <div>
              <Label className="text-xs uppercase tracking-wider">Weight (kg)</Label>
              <Input type="number" value={form.weight_kg} onChange={(e) => setForm({ ...form, weight_kg: e.target.value })} className="rounded-none mt-1 font-mono-num" />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider">Year</Label>
              <Input type="number" value={form.year} onChange={(e) => setForm({ ...form, year: e.target.value })} className="rounded-none mt-1 font-mono-num" data-testid="repo-form-year" />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider">Pressure (bar)</Label>
              <Input type="number" value={form.design_pressure_bar} onChange={(e) => setForm({ ...form, design_pressure_bar: e.target.value })} className="rounded-none mt-1 font-mono-num" />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider">Temp (°C)</Label>
              <Input type="number" value={form.design_temperature_c} onChange={(e) => setForm({ ...form, design_temperature_c: e.target.value })} className="rounded-none mt-1 font-mono-num" />
            </div>
            {showPower && (
              <div>
                <Label className="text-xs uppercase tracking-wider">Power (kW)</Label>
                <Input type="number" value={form.power_kw} onChange={(e) => setForm({ ...form, power_kw: e.target.value })} className="rounded-none mt-1 font-mono-num" />
              </div>
            )}
            <div>
              <Label className="text-xs uppercase tracking-wider">Cost</Label>
              <Input type="number" value={form.cost_original} onChange={(e) => setForm({ ...form, cost_original: e.target.value })} className="rounded-none mt-1 font-mono-num" data-testid="repo-form-cost" />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider">Currency</Label>
              <Select value={form.currency} onValueChange={(v) => setForm({ ...form, currency: v })}>
                <SelectTrigger className="rounded-none mt-1"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="EUR">EUR</SelectItem><SelectItem value="USD">USD</SelectItem></SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider">Vendor Country</Label>
              <Input value={form.vendor_country} onChange={(e) => setForm({ ...form, vendor_country: e.target.value })} className="rounded-none mt-1" />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider">Install Country</Label>
              <Input value={form.install_country} onChange={(e) => setForm({ ...form, install_country: e.target.value })} className="rounded-none mt-1" />
            </div>
            <div className="col-span-3">
              <Label className="text-xs uppercase tracking-wider">Notes</Label>
              <Textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} className="rounded-none mt-1" rows={2} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-none" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button className="rounded-none bg-[#002FA7] hover:bg-[#002480]" onClick={save} data-testid="repo-form-save">{editing ? "Save" : "Add"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
