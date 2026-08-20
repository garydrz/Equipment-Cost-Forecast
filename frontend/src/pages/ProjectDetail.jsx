import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api, formatMoney, formatNum, CAT_LABELS, MAT_LABELS } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AaceBadge } from "@/components/AaceBadge";
import { Plus, Trash, ArrowLeft, Warning, ArrowsClockwise, MagnifyingGlass, PencilSimple } from "@phosphor-icons/react";
import { toast } from "sonner";
import EquipmentRowDialog from "@/components/EquipmentRowDialog";
import RowDetailsDialog from "@/components/RowDetailsDialog";
import CostDriversChart from "@/components/CostDriversChart";

const AACE_CLASSES = ["Class 5", "Class 4", "Class 3", "Class 2", "Class 1"];

export default function ProjectDetail() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingRow, setEditingRow] = useState(null);
  const [detailsRow, setDetailsRow] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const res = await api.get(`/projects/${id}`);
      setData(res.data);
    } catch (e) { toast.error("Failed to load project"); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [id]);

  const openAdd = () => { setEditingRow(null); setDialogOpen(true); };
  const openEdit = (row) => { setEditingRow(row); setDialogOpen(true); };
  const openDetails = (row) => setDetailsRow(row);

  const removeRow = async (rid) => {
    if (!window.confirm("Delete this equipment row?")) return;
    try {
      await api.delete(`/projects/${id}/rows/${rid}`);
      toast.success("Row deleted"); load();
    } catch (e) { toast.error("Failed to delete"); }
  };

  const recompute = async () => {
    try {
      await api.post(`/projects/${id}/recompute`);
      toast.success("Project recomputed"); load();
    } catch (e) { toast.error("Recompute failed"); }
  };

  const setAaceClass = async (cls) => {
    try {
      await api.put(`/projects/${id}`, { aace_class: cls });
      toast.success(`Project set to ${cls}`); load();
    } catch (e) { toast.error("Failed"); }
  };

  const ccy = data?.project?.output_currency || "EUR";

  if (loading) return <div className="p-8 text-slate-500 text-sm">Loading…</div>;
  if (!data) return <div className="p-8 text-slate-500">Project not found</div>;

  const { project, rows, totals } = data;

  return (
    <div className="p-8 max-w-7xl">
      <Link to="/" className="inline-flex items-center gap-2 text-xs uppercase tracking-widest text-slate-500 hover:text-slate-900 mb-4" data-testid="back-to-projects">
        <ArrowLeft size={14} /> Projects
      </Link>

      <div className="flex items-end justify-between mb-6">
        <div>
          <div className="text-xs uppercase tracking-[0.2em] text-slate-500 mb-2">Project Dashboard</div>
          <h1 className="font-heading text-3xl font-semibold tracking-tight text-slate-900" data-testid="project-title">{project.name}</h1>
          {project.description && <p className="text-sm text-slate-600 mt-2 max-w-2xl">{project.description}</p>}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={recompute} className="rounded-none h-10" data-testid="recompute-btn">
            <ArrowsClockwise size={14} className="mr-2" /> Recompute
          </Button>
          <Button onClick={openAdd} className="rounded-none bg-[#002FA7] hover:bg-[#002480] text-white h-10 px-5" data-testid="add-equipment-btn">
            <Plus size={16} className="mr-2" /> Add Equipment
          </Button>
        </div>
      </div>

      {/* Summary bento */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-0 mb-8 border border-border">
        <SummaryTile label="Expected Cost" value={formatMoney(totals.expected, ccy)} highlight testId="stat-expected" />
        <SummaryTile label="Lower Bound" value={formatMoney(totals.low, ccy)} testId="stat-low" />
        <SummaryTile label="Upper Bound" value={formatMoney(totals.high, ccy)} testId="stat-high" />
        <div className="p-5 border-r border-b border-border last:border-r-0 bg-white" data-testid="stat-aace">
          <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-2">AACE Class</div>
          <Select value={project.aace_class} onValueChange={setAaceClass}>
            <SelectTrigger className="rounded-none h-9 w-full" data-testid="aace-class-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              {AACE_CLASSES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
          <div className="text-xs text-slate-500 font-mono-num mt-2">σ = {formatMoney(totals.sigma, ccy)}</div>
        </div>
      </div>

      {/* Cost drivers chart */}
      <CostDriversChart rows={rows} currency={ccy} />

      {/* Rows table */}
      <div className="border border-border bg-white overflow-x-auto">
        <table className="w-full data-table" data-testid="equipment-rows-table">
          <thead>
            <tr>
              <th className="text-left px-3 py-2.5">Tag</th>
              <th className="text-left px-3 py-2.5">Category</th>
              <th className="text-left px-3 py-2.5">Subtype</th>
              <th className="text-left px-3 py-2.5">Primary var</th>
              <th className="text-right px-3 py-2.5">Value</th>
              <th className="text-left px-3 py-2.5">Material</th>
              <th className="text-right px-3 py-2.5">Qty</th>
              <th className="text-right px-3 py-2.5">Unit Cost</th>
              <th className="text-right px-3 py-2.5">Total Cost</th>
              <th className="text-right px-3 py-2.5">Range</th>
              <th className="text-center px-3 py-2.5">Neff</th>
              <th className="text-center px-3 py-2.5">Refs</th>
              <th className="px-2 py-2.5"></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={13} className="text-center py-8 text-slate-500 text-sm">No equipment yet. Click "Add Equipment" to start.</td></tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className="cursor-pointer" onClick={() => openDetails(r)} data-testid={`row-${r.id}`}>
                <td className="px-3 py-2 font-mono-num text-slate-900">{r.tag || "—"}</td>
                <td className="px-3 py-2 text-slate-700">{CAT_LABELS[r.category] || r.category}</td>
                <td className="px-3 py-2 text-slate-600 text-xs">{r.subtype || "—"}</td>
                <td className="px-3 py-2 text-slate-600 text-xs">
                  {r.scaling_variable || "—"}
                  {r.scaling_variable_is_fallback && <span className="ml-1 text-amber-600" title="Fallback">*</span>}
                </td>
                <td className="px-3 py-2 text-right font-mono-num text-xs">
                  {r.scaling_variable_value != null ? formatNum(r.scaling_variable_value) : "—"}
                  <span className="text-slate-400 ml-1">{r.scaling_variable_unit || ""}</span>
                </td>
                <td className="px-3 py-2 text-slate-600 text-xs">{MAT_LABELS[r.material] || r.material}</td>
                <td className="px-3 py-2 text-right font-mono-num">{r.quantity}</td>
                <td className="px-3 py-2 text-right font-mono-num text-slate-900">{formatMoney(r.unit_expected_cost, ccy)}</td>
                <td className="px-3 py-2 text-right font-mono-num font-semibold text-slate-900">{formatMoney(r.total_expected_cost, ccy)}</td>
                <td className="px-3 py-2 text-right font-mono-num text-xs text-slate-500">
                  {formatMoney(r.unit_low * r.quantity, ccy)} — {formatMoney(r.unit_high * r.quantity, ccy)}
                </td>
                <td className="px-3 py-2 text-center font-mono-num text-xs">{formatNum(r.effective_sample_size, 1)}</td>
                <td className="px-3 py-2 text-center font-mono-num text-xs text-slate-600">
                  {r.references_used === 0 ? <span className="inline-flex items-center gap-1 text-amber-600"><Warning size={12} />0</span> : `${r.references_used}/${r.references_candidate}`}
                </td>
                <td className="px-2 py-2 text-right whitespace-nowrap">
                  <button onClick={(e) => { e.stopPropagation(); openDetails(r); }} className="text-slate-400 hover:text-slate-900 mr-2" title="Details" data-testid={`details-row-${r.id}`}><MagnifyingGlass size={14} /></button>
                  <button onClick={(e) => { e.stopPropagation(); openEdit(r); }} className="text-slate-400 hover:text-slate-900 mr-2" title="Edit" data-testid={`edit-row-${r.id}`}><PencilSimple size={14} /></button>
                  <button onClick={(e) => { e.stopPropagation(); removeRow(r.id); }} className="text-slate-400 hover:text-red-600" title="Delete" data-testid={`delete-row-${r.id}`}><Trash size={14} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-3 text-xs text-slate-500">
        Project confidence interval is calculated by propagation of independent uncertainties (sum in quadrature of per-row half-ranges). Click a row for the full estimation breakdown.
      </div>

      <EquipmentRowDialog open={dialogOpen} onOpenChange={setDialogOpen} project={project} row={editingRow} onSaved={load} />
      <RowDetailsDialog open={!!detailsRow} onOpenChange={(v) => !v && setDetailsRow(null)} row={detailsRow} currency={ccy} />
    </div>
  );
}

function SummaryTile({ label, value, sub, highlight, testId }) {
  return (
    <div className={`p-5 border-r border-b border-border last:border-r-0 ${highlight ? "bg-slate-50" : "bg-white"}`} data-testid={testId}>
      <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-2">{label}</div>
      <div className={`font-mono-num text-2xl ${highlight ? "text-[#002FA7] font-semibold" : "text-slate-900"}`}>{value}</div>
      {sub && <div className="text-xs text-slate-500 font-mono-num mt-1">{sub}</div>}
    </div>
  );
}
