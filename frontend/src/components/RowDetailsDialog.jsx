import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { formatMoney, formatNum, CAT_LABELS, MAT_LABELS } from "@/lib/api";
import { Warning } from "@phosphor-icons/react";

export default function RowDetailsDialog({ open, onOpenChange, row, currency }) {
  if (!row) return null;
  const used = row.references_detail || [];
  const excluded = row.references_excluded || [];
  const b = row.estimation_breakdown || {};

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-none max-w-6xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-heading flex items-center gap-3">
            <span>{row.tag || "—"}</span>
            <span className="text-slate-400 text-sm font-normal">·</span>
            <span className="text-sm font-normal text-slate-600">{CAT_LABELS[row.category] || row.category} · {row.subtype || ""}</span>
          </DialogTitle>
        </DialogHeader>

        {/* Estimation basis */}
        <Section title="Estimation basis">
          <Grid cols={4}>
            <Field label="Primary variable" value={`${row.scaling_variable} = ${formatNum(row.scaling_variable_value)} ${row.scaling_variable_unit || ""}`} accent={row.scaling_variable_is_fallback ? "warn" : "info"} />
            <Field label="Status" value={row.scaling_variable_is_fallback ? "Fallback" : "Primary"} />
            <Field label="Scale exponent n" value={formatNum(b.scale_exponent_n, 3)} />
            <Field label="Target material" value={MAT_LABELS[row.material] || row.material} />
            <Field label="Target pressure" value={row.design_pressure_bar != null ? `${row.design_pressure_bar} barg` : "—"} />
            <Field label="Target year" value={b.target_year} />
            <Field label="Output currency" value={b.output_currency} />
            <Field label="Refs used / candidates" value={`${row.references_used} / ${row.references_candidate}`} />
            <Field label="Effective sample size" value={formatNum(row.effective_sample_size, 2)} />
            <Field label="Data quality" value={b.data_quality || "—"} />
            <Field label="Weighted σ" value={formatMoney(b.weighted_sigma, currency)} />
            <Field label="CoV" value={b.coefficient_of_variation != null ? `${(b.coefficient_of_variation * 100).toFixed(1)}%` : "—"} />
          </Grid>
          {row.warnings?.length > 0 && (
            <div className="mt-2 text-xs text-amber-700 space-y-0.5">
              {row.warnings.map((w, i) => <div key={i} className="flex items-start gap-1"><Warning size={12} className="mt-0.5" /> {w}</div>)}
            </div>
          )}
        </Section>

        {/* Calculation factors */}
        <Section title="Calculation factors">
          <Grid cols={3}>
            <Field label="Size scaling" value={`C × (X_t/X_r)^n`} />
            <Field label="Material factor" value={`MF_target / MF_ref`} />
            <Field label="Pressure factor" value={b.pressure_enabled ? `(P_abs_t / P_abs_r)^${formatNum(b.pressure_exponent, 2)}` : "disabled"} />
            <Field label="Escalation" value={`steel_w × Δ%_steel + oil_w × Δ%_oil`} />
            <Field label="Currency" value="Frankfurter FX historical & current" />
            <Field label="Similarity" value={`α=${b.similarity_configuration?.alpha}, β=${b.similarity_configuration?.beta}, γ=${b.similarity_configuration?.gamma}`} />
          </Grid>
        </Section>

        {/* References used */}
        <Section title={`Historical references used (${used.length})`}>
          <div className="border border-border bg-white overflow-x-auto">
            <table className="w-full data-table" data-testid="refs-used-table">
              <thead>
                <tr>
                  <th className="text-left px-3 py-2">Ref subtype</th>
                  <th className="text-right px-3 py-2">Year</th>
                  <th className="text-right px-3 py-2">Hist. size</th>
                  <th className="text-right px-3 py-2">Hist. cost</th>
                  <th className="text-right px-3 py-2">F_size</th>
                  <th className="text-right px-3 py-2">F_material</th>
                  <th className="text-right px-3 py-2">F_pressure</th>
                  <th className="text-right px-3 py-2">Escal.</th>
                  <th className="text-right px-3 py-2">FX</th>
                  <th className="text-right px-3 py-2">Adjusted cost</th>
                  <th className="text-right px-3 py-2">S_size</th>
                  <th className="text-right px-3 py-2">S_total</th>
                  <th className="text-right px-3 py-2">Weight</th>
                  <th className="text-right px-3 py-2">Contribution</th>
                </tr>
              </thead>
              <tbody>
                {used.map((u) => (
                  <tr key={u.historical_equipment_id}>
                    <td className="px-3 py-2 text-xs text-slate-600">{u.subtype || "—"}</td>
                    <td className="px-3 py-2 text-right font-mono-num text-xs">{u.year}</td>
                    <td className="px-3 py-2 text-right font-mono-num text-xs">{formatNum(u.historical_scaling_variable_value)} <span className="text-slate-400">{u.scaling_variable_unit}</span></td>
                    <td className="px-3 py-2 text-right font-mono-num text-xs">{formatMoney(u.original_cost, u.original_currency)}</td>
                    <td className="px-3 py-2 text-right font-mono-num text-xs">{formatNum(u.size_scaling_factor, 3)}</td>
                    <td className="px-3 py-2 text-right font-mono-num text-xs">{formatNum(u.applied_material_factor, 3)}</td>
                    <td className="px-3 py-2 text-right font-mono-num text-xs">
                      {u.pressure_status === "disabled" ? <span className="text-slate-400">off</span> : formatNum(u.applied_pressure_factor, 3)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono-num text-xs">{formatNum(u.escalation_factor, 3)}</td>
                    <td className="px-3 py-2 text-right font-mono-num text-xs">{formatNum(u.fx_factor, 3)}</td>
                    <td className="px-3 py-2 text-right font-mono-num text-xs font-semibold">{formatMoney(u.adjusted_cost, currency)}</td>
                    <td className="px-3 py-2 text-right font-mono-num text-xs">{formatNum(u.size_similarity, 3)}</td>
                    <td className="px-3 py-2 text-right font-mono-num text-xs font-medium">{formatNum(u.total_similarity, 3)}</td>
                    <td className="px-3 py-2 text-right font-mono-num text-xs">{formatNum(u.normalized_weight, 3)}</td>
                    <td className="px-3 py-2 text-right font-mono-num text-xs text-[#002FA7]">{formatMoney(u.weighted_contribution, currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        {/* References excluded */}
        {excluded.length > 0 && (
          <Section title={`Historical references excluded (${excluded.length})`}>
            <div className="border border-border bg-white">
              <table className="w-full data-table" data-testid="refs-excluded-table">
                <thead>
                  <tr>
                    <th className="text-left px-3 py-2">Ref ID</th>
                    <th className="text-left px-3 py-2">Subtype</th>
                    <th className="text-left px-3 py-2">Exclusion reason</th>
                    <th className="text-right px-3 py-2">Similarity</th>
                  </tr>
                </thead>
                <tbody>
                  {excluded.map((e, i) => (
                    <tr key={i}>
                      <td className="px-3 py-2 text-xs text-slate-500 font-mono-num">{(e.historical_equipment_id || "").slice(0, 8)}</td>
                      <td className="px-3 py-2 text-xs">{e.subtype || "—"}</td>
                      <td className="px-3 py-2 text-xs text-amber-700">{e.exclusion_reason}</td>
                      <td className="px-3 py-2 text-right font-mono-num text-xs">{e.similarity != null ? formatNum(e.similarity, 3) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Section({ title, children }) {
  return (
    <div className="mt-4">
      <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-2 font-semibold">{title}</div>
      {children}
    </div>
  );
}

function Grid({ cols = 3, children }) {
  const cls = { 3: "grid-cols-3", 4: "grid-cols-4" }[cols] || "grid-cols-3";
  return <div className={`grid ${cls} gap-3 border border-border p-3 bg-slate-50`}>{children}</div>;
}

function Field({ label, value, accent }) {
  const cls = accent === "warn" ? "text-amber-700" : accent === "info" ? "text-slate-900" : "text-slate-900";
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest text-slate-500">{label}</div>
      <div className={`font-mono-num text-xs ${cls}`}>{value ?? "—"}</div>
    </div>
  );
}
