import { useMemo } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { CAT_LABELS, formatMoney } from "@/lib/api";

const CAT_COLORS = {
  column: "#002FA7",
  reactor: "#1E40AF",
  heat_exchanger: "#0369A1",
  storage_tank: "#0891B2",
  pump: "#0D9488",
  compressor: "#65A30D",
  valve: "#CA8A04",
  instrumentation: "#DC2626",
  other: "#64748B",
};

export default function CostDriversChart({ rows, currency }) {
  const data = useMemo(() => {
    const totals = {};
    let grand = 0;
    for (const r of rows) {
      const t = Number(r.total_expected_cost) || 0;
      totals[r.category] = (totals[r.category] || 0) + t;
      grand += t;
    }
    return Object.entries(totals)
      .map(([cat, total]) => ({
        category: cat,
        label: CAT_LABELS[cat] || cat,
        total,
        share: grand > 0 ? (total / grand) * 100 : 0,
        color: CAT_COLORS[cat] || "#64748B",
      }))
      .sort((a, b) => b.total - a.total);
  }, [rows]);

  if (rows.length === 0) return null;

  const maxShare = data[0]?.share || 0;

  return (
    <div className="border border-border bg-white mb-6" data-testid="cost-drivers-chart">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-slate-50">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-slate-500">Analysis</div>
          <div className="font-heading text-sm font-semibold text-slate-900">Cost Drivers by Category</div>
        </div>
        <div className="text-xs text-slate-500 font-mono-num">
          Top: <span className="text-[#002FA7] font-semibold">{data[0]?.label}</span> · {maxShare.toFixed(1)}%
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-0">
        <div className="lg:col-span-3 p-4 border-r border-border">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data} margin={{ top: 10, right: 16, left: 8, bottom: 4 }}>
              <XAxis
                dataKey="label"
                tick={{ fontSize: 10, fill: "#64748B" }}
                interval={0}
                angle={-15}
                textAnchor="end"
                height={50}
              />
              <YAxis
                tick={{ fontSize: 10, fill: "#64748B", fontFamily: "IBM Plex Mono" }}
                tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v)}
              />
              <Tooltip
                cursor={{ fill: "#F1F5F9" }}
                contentStyle={{ borderRadius: 0, border: "1px solid #E2E8F0", fontFamily: "IBM Plex Mono", fontSize: 12 }}
                formatter={(v, _n, entry) => [formatMoney(v, currency), `${entry.payload.share.toFixed(1)}%`]}
                labelFormatter={(l) => l}
              />
              <Bar dataKey="total" radius={[0, 0, 0, 0]}>
                {data.map((d) => (
                  <Cell key={d.category} fill={d.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="lg:col-span-2 p-4">
          <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-2">Ranking</div>
          <div className="space-y-2" data-testid="cost-drivers-list">
            {data.map((d) => (
              <div key={d.category} className="flex items-center gap-2" data-testid={`driver-${d.category}`}>
                <div className="h-3 w-3 flex-shrink-0" style={{ background: d.color }} />
                <div className="text-xs text-slate-700 flex-1 truncate">{d.label}</div>
                <div className="font-mono-num text-xs text-slate-900">{formatMoney(d.total, currency)}</div>
                <div className="font-mono-num text-xs text-slate-500 w-12 text-right">{d.share.toFixed(1)}%</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
