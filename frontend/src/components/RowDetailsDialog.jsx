import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { formatMoney, formatNum, CAT_LABELS, MAT_LABELS } from "@/lib/api";
import { Warning } from "@phosphor-icons/react";

export default function RowDetailsDialog({ open, onOpenChange, row, currency }) {
  if (!row) return null;
  const used = row.references_detail || [];
  const excluded = row.references_excluded || [];
  const b = row.estimation_breakdown || {};
  const report = row.calculation_report || {};
  const outlier = row.outlier_summary || {};
  const isPump = row.category === "pump";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-none max-w-6xl max-h-[92vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-heading flex items-center gap-3">
            <span>{row.tag || "—"}</span>
            <span className="text-slate-400 text-sm font-normal">·</span>
            <span className="text-sm font-normal text-slate-600">{CAT_LABELS[row.category] || row.category} · {row.subtype || ""}</span>
          </DialogTitle>
        </DialogHeader>

        {/* HOW THE ESTIMATE WAS CALCULATED (human-readable) */}
        {report?.equation_used && (
          <Section title="How the estimate was calculated">
            <div className="border border-border bg-slate-50 p-4 space-y-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">Equipment Description</div>
                  <ul className="text-xs text-slate-700 space-y-0.5">
                    <li>Category: <span className="font-mono-num">{report.equipment_description?.category}</span></li>
                    <li>Subtype: <span className="font-mono-num">{report.equipment_description?.subtype}</span></li>
                    <li>Material: <span className="font-mono-num">{MAT_LABELS[report.equipment_description?.material]}</span></li>
                    <li>Pressure: <span className="font-mono-num">{report.equipment_description?.design_pressure_barg ?? "—"} barg</span></li>
                    <li>Primary variable: <span className="font-mono-num">{report.equipment_description?.primary_variable} = {formatNum(report.equipment_description?.primary_variable_value)} {report.equipment_description?.primary_variable_unit}</span></li>
                  </ul>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">Historical Basis</div>
                  <ul className="text-xs text-slate-700 space-y-0.5">
                    <li>Total references found: <span className="font-mono-num">{report.historical_basis?.total_references_found}</span></li>
                    <li>References excluded: <span className="font-mono-num">{report.historical_basis?.references_excluded}</span></li>
                    <li>Outliers removed: <span className="font-mono-num">{report.historical_basis?.outliers_removed}</span></li>
                    <li>References used: <span className="font-mono-num font-semibold text-[#002FA7]">{report.historical_basis?.references_used}</span></li>
                  </ul>
                </div>
              </div>

              <div>
                <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">Estimation Method</div>
                <div className="text-xs text-slate-700 space-y-0.5">
                  <div>Method: <span className="font-mono-num">{report.estimation_method?.method}</span></div>
                  <div>Cost corrections applied:</div>
                  <ol className="list-decimal ml-5">
                    {(report.estimation_method?.cost_corrections_applied || []).map((c, i) => <li key={i}>{c}</li>)}
                  </ol>
                  <div>Outlier filtering: <span className="font-mono-num">{report.estimation_method?.outlier_filtering?.method} (k = {report.estimation_method?.outlier_filtering?.multiplier}, applied = {report.estimation_method?.outlier_filtering?.applied ? "yes" : "no"})</span></div>
                  <div>Reliability range: <span className="font-mono-num">Weighted mean ± {report.estimation_method?.reliability_range?.z_value} σ  ·  Confidence level {report.estimation_method?.reliability_range?.confidence_level_percent}%</span></div>
                </div>
              </div>

              <div>
                <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">Equation Used</div>
                <div className="font-mono-num text-xs text-slate-900 bg-white border border-border p-2">{report.equation_used}</div>
              </div>

              <div>
                <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">Most Influential Historical References</div>
                <div className="text-xs space-y-0.5">
                  {(report.most_influential_references || []).map((r, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <span className="font-mono-num text-slate-500 w-16">{r.tag}</span>
                      <span className="text-slate-700 flex-1">{r.subtype} · {r.original_year} · adj {formatMoney(r.adjusted_cost, currency)}</span>
                      <span className="font-mono-num text-[#002FA7] font-semibold">Weight = {r.weight_percent}%</span>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">Reliability Assessment</div>
                <div className="grid grid-cols-4 gap-2 text-xs">
                  <div><span className="text-slate-500">Neff</span><div className="font-mono-num">{report.reliability_assessment?.effective_sample_size}</div></div>
                  <div><span className="text-slate-500">Weighted σ</span><div className="font-mono-num">{report.reliability_assessment?.weighted_sigma_sample != null ? formatMoney(report.reliability_assessment.weighted_sigma_sample, currency) : "—"}</div></div>
                  <div><span className="text-slate-500">Confidence</span><div className="font-mono-num">{report.reliability_assessment?.confidence_level_percent}%</div></div>
                  <div><span className="text-slate-500">CoV</span><div className="font-mono-num">{report.reliability_assessment?.coefficient_of_variation != null ? `${(report.reliability_assessment.coefficient_of_variation * 100).toFixed(1)}%` : "—"}</div></div>
                </div>
              </div>

              {(report.warnings || []).length > 0 && (
                <div>
                  <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">Warnings</div>
                  <div className="text-xs text-amber-700 space-y-0.5">
                    {report.warnings.map((w, i) => <div key={i} className="flex items-start gap-1"><Warning size={12} className="mt-0.5" />{w}</div>)}
                  </div>
                </div>
              )}
            </div>
          </Section>
        )}

        <Section title="Estimation basis">
          <Grid cols={4}>
            <Field label="Primary variable" value={`${row.scaling_variable} = ${formatNum(row.scaling_variable_value)} ${row.scaling_variable_unit || ""}`} accent={row.scaling_variable_is_fallback ? "warn" : "info"} />
            <Field label="Status" value={row.scaling_variable_is_fallback ? "Fallback" : "Primary"} />
            <Field label="Scale exponent" value={isPump ? "—" : formatNum(b.scale_exponent_n, 3)} />
            <Field label="Target material" value={MAT_LABELS[row.material] || row.material} />
            <Field label="Refs used / candidates" value={`${row.references_used} / ${row.references_candidate}`} />
            <Field label="Effective sample size" value={formatNum(row.effective_sample_size, 2)} />
            <Field label="σ population" value={b.sigma_population != null ? formatMoney(b.sigma_population, currency) : "—"} />
            <Field label="σ sample (used)" value={b.sigma_used_for_range != null ? formatMoney(b.sigma_used_for_range, currency) : "—"} />
            <Field label="Confidence level" value={b.confidence_level ? `${b.confidence_level}% (z=${b.z_value})` : "—"} />
            <Field label="Range method" value={b.range_method || "—"} />
            <Field label="Low / High" value={row.unit_low != null && row.unit_high != null ? `${formatMoney(row.unit_low, currency)} — ${formatMoney(row.unit_high, currency)}` : "—"} />
            <Field label="CoV" value={b.coefficient_of_variation != null ? `${(b.coefficient_of_variation * 100).toFixed(1)}%` : "—"} />
          </Grid>
        </Section>

        {/* Outlier analysis */}
        <Section title="Outlier analysis">
          <Grid cols={4}>
            <Field label="Enabled" value={outlier.enabled ? "yes" : "no"} />
            <Field label="Applied" value={outlier.applied ? "yes" : "no"} />
            <Field label="IQR multiplier" value={outlier.iqr_multiplier} />
            <Field label="Min refs required" value={outlier.minimum_references_for_iqr} />
            <Field label="Refs before filter" value={outlier.references_before_filter} />
            <Field label="Q1" value={outlier.q1 != null ? formatMoney(outlier.q1, currency) : "—"} />
            <Field label="Q3" value={outlier.q3 != null ? formatMoney(outlier.q3, currency) : "—"} />
            <Field label="IQR" value={outlier.iqr != null ? formatMoney(outlier.iqr, currency) : "—"} />
            <Field label="Lower fence" value={outlier.lower_fence != null ? formatMoney(outlier.lower_fence, currency) : "—"} />
            <Field label="Upper fence" value={outlier.upper_fence != null ? formatMoney(outlier.upper_fence, currency) : "—"} />
            <Field label="Outliers removed" value={outlier.outliers_removed} accent={outlier.outliers_removed > 0 ? "warn" : undefined} />
            <Field label="Refs after filter" value={outlier.references_remaining_after_filter} />
          </Grid>
        </Section>

        {/* Pump scaling summary */}
        {isPump && row.pump_scaling_summary && (
          <Section title="Pump scaling configuration">
            <Grid cols={4}>
              <Field label="Subtype" value={row.pump_scaling_summary.subtype} />
              <Field label="Flow exponent a" value={row.pump_scaling_summary.flow_exponent_a} />
              <Field label="Head exponent b" value={row.pump_scaling_summary.head_exponent_b} />
              <Field label="Power exponent c" value={row.pump_scaling_summary.power_exponent_c} />
              <Field label="Power missing policy" value={row.pump_scaling_summary.power_missing_policy} />
              <Field label="Exp renormalization" value={String(row.pump_scaling_summary.exponent_renormalization)} />
              <Field label="Source" value={row.pump_scaling_summary.source} />
            </Grid>
          </Section>
        )}

        <Section title={`Historical references used (${used.length})`}>
          <div className="border border-border bg-white overflow-x-auto">
            <table className="w-full data-table" data-testid="refs-used-table">
              <thead>
                <tr>
                  <th className="text-left px-3 py-2">Ref</th>
                  <th className="text-right px-3 py-2">Yr</th>
                  <th className="text-right px-3 py-2">Hist. size/duty</th>
                  <th className="text-right px-3 py-2">Hist. cost</th>
                  {isPump ? (
                    <>
                      <th className="text-right px-3 py-2">F_flow</th>
                      <th className="text-right px-3 py-2">F_head</th>
                      <th className="text-right px-3 py-2">F_pow</th>
                    </>
                  ) : (
                    <th className="text-right px-3 py-2">F_size</th>
                  )}
                  <th className="text-right px-3 py-2">F_mat</th>
                  {!isPump && <th className="text-right px-3 py-2">F_p</th>}
                  <th className="text-right px-3 py-2">Escal.</th>
                  <th className="text-right px-3 py-2">FX</th>
                  <th className="text-right px-3 py-2">Adj. cost</th>
                  <th className="text-right px-3 py-2">S_total</th>
                  <th className="text-right px-3 py-2">W</th>
                  <th className="text-right px-3 py-2">Contribution</th>
                </tr>
              </thead>
              <tbody>
                {used.map((u) => {
                  const pb = u.pump_breakdown;
                  return (
                    <tr key={u.historical_equipment_id}>
                      <td className="px-3 py-2 text-xs text-slate-600 font-mono-num">{(u.historical_equipment_id || "").slice(0, 8)} <span className="text-slate-400">{u.subtype}</span></td>
                      <td className="px-3 py-2 text-right font-mono-num text-xs">{u.year}</td>
                      <td className="px-3 py-2 text-right font-mono-num text-xs">
                        {pb ? `Q=${formatNum(pb.flow_ref)} H=${formatNum(pb.head_ref)}` : `${formatNum(u.historical_scaling_variable_value)} ${u.scaling_variable_unit}`}
                      </td>
                      <td className="px-3 py-2 text-right font-mono-num text-xs">{formatMoney(u.original_cost, u.original_currency)}</td>
                      {isPump ? (
                        <>
                          <td className="px-3 py-2 text-right font-mono-num text-xs">{formatNum(pb?.F_flow, 3)}</td>
                          <td className="px-3 py-2 text-right font-mono-num text-xs">{formatNum(pb?.F_head, 3)}</td>
                          <td className="px-3 py-2 text-right font-mono-num text-xs">{pb?.power_used ? formatNum(pb?.F_power, 3) : <span className="text-slate-400">off</span>}</td>
                        </>
                      ) : (
                        <td className="px-3 py-2 text-right font-mono-num text-xs">{formatNum(u.size_scaling_factor, 3)}</td>
                      )}
                      <td className="px-3 py-2 text-right font-mono-num text-xs">{formatNum(u.applied_material_factor, 3)}</td>
                      {!isPump && (
                        <td className="px-3 py-2 text-right font-mono-num text-xs">
                          {u.pressure_status === "disabled" || u.pressure_status?.startsWith("skipped") ? <span className="text-slate-400">off</span> : formatNum(u.applied_pressure_factor, 3)}
                        </td>
                      )}
                      <td className="px-3 py-2 text-right font-mono-num text-xs">{formatNum(u.escalation_factor, 3)}</td>
                      <td className="px-3 py-2 text-right font-mono-num text-xs">{formatNum(u.fx_factor, 3)}</td>
                      <td className="px-3 py-2 text-right font-mono-num text-xs font-semibold">{formatMoney(u.adjusted_cost, currency)}</td>
                      <td className="px-3 py-2 text-right font-mono-num text-xs">{formatNum(u.total_similarity, 3)}</td>
                      <td className="px-3 py-2 text-right font-mono-num text-xs">{formatNum(u.normalized_weight, 3)}</td>
                      <td className="px-3 py-2 text-right font-mono-num text-xs text-[#002FA7]">{formatMoney(u.weighted_contribution, currency)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Section>

        {excluded.length > 0 && (
          <Section title={`Historical references excluded (${excluded.length})`}>
            <div className="border border-border bg-white">
              <table className="w-full data-table" data-testid="refs-excluded-table">
                <thead>
                  <tr>
                    <th className="text-left px-3 py-2">Ref ID</th>
                    <th className="text-left px-3 py-2">Subtype</th>
                    <th className="text-left px-3 py-2">Reason</th>
                    <th className="text-right px-3 py-2">Adjusted cost</th>
                    <th className="text-right px-3 py-2">Similarity</th>
                  </tr>
                </thead>
                <tbody>
                  {excluded.map((e, i) => (
                    <tr key={i}>
                      <td className="px-3 py-2 text-xs text-slate-500 font-mono-num">{(e.historical_equipment_id || "").slice(0, 8)}</td>
                      <td className="px-3 py-2 text-xs">{e.subtype || "—"}</td>
                      <td className="px-3 py-2 text-xs text-amber-700">{e.exclusion_reason}</td>
                      <td className="px-3 py-2 text-right font-mono-num text-xs">{e.adjusted_cost != null ? formatMoney(e.adjusted_cost, currency) : "—"}</td>
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
  const cls = accent === "warn" ? "text-amber-700" : "text-slate-900";
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest text-slate-500">{label}</div>
      <div className={`font-mono-num text-xs ${cls}`}>{value ?? "—"}</div>
    </div>
  );
}
