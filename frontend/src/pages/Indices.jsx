import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";

export default function Indices() {
  const [data, setData] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/indices");
        setData(data);
      } catch (e) { toast.error("Failed to load indices"); }
    })();
  }, []);

  if (!data) return <div className="p-8 text-slate-500 text-sm">Loading indices…</div>;

  const years = Array.from(new Set([
    ...Object.keys(data.steel_by_year), ...Object.keys(data.oil_by_year)
  ].map(Number))).sort();

  return (
    <div className="p-8 max-w-4xl">
      <div className="mb-6">
        <div className="text-xs uppercase tracking-[0.2em] text-slate-500 mb-2">Reference Data</div>
        <h1 className="font-heading text-3xl font-semibold tracking-tight text-slate-900 klein-underline">Escalation Indices</h1>
        <p className="text-sm text-slate-600 mt-3">Source: <span className="font-mono-num font-medium text-slate-900">{data.source}</span></p>
      </div>

      <div className="border border-border bg-white">
        <table className="w-full data-table">
          <thead>
            <tr>
              <th className="text-left px-3 py-2.5">Year</th>
              <th className="text-right px-3 py-2.5">Steel Index (WPU101706)</th>
              <th className="text-right px-3 py-2.5">Brent Oil (USD/bbl)</th>
            </tr>
          </thead>
          <tbody>
            {years.map((y) => (
              <tr key={y}>
                <td className="px-3 py-2 font-mono-num text-slate-900">{y}</td>
                <td className="px-3 py-2 text-right font-mono-num">{data.steel_by_year[y] ? Number(data.steel_by_year[y]).toFixed(2) : "—"}</td>
                <td className="px-3 py-2 text-right font-mono-num">{data.oil_by_year[y] ? Number(data.oil_by_year[y]).toFixed(2) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
