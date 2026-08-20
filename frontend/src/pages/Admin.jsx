import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";

export default function Admin() {
  const [exponents, setExponents] = useState([]);
  const [weights, setWeights] = useState([]);

  const load = async () => {
    try {
      const [e, w] = await Promise.all([
        api.get("/admin/scale-exponents"),
        api.get("/admin/escalation-weights"),
      ]);
      setExponents(e.data);
      setWeights(w.data);
    } catch (err) {
      toast.error("Failed to load admin params");
    }
  };

  useEffect(() => { load(); }, []);

  const saveExponents = async () => {
    try {
      await api.put("/admin/scale-exponents", exponents.map((r) => ({ category: r.category, n: Number(r.n) })));
      toast.success("Scale exponents saved");
    } catch (e) { toast.error("Failed"); }
  };

  const saveWeights = async () => {
    for (const r of weights) {
      if (Math.abs(Number(r.steel_weight) + Number(r.oil_weight) - 1) > 0.01) {
        toast.error(`Weights for ${r.label} must sum to 1.0`);
        return;
      }
    }
    try {
      await api.put("/admin/escalation-weights", weights.map((r) => ({
        category: r.category,
        steel_weight: Number(r.steel_weight),
        oil_weight: Number(r.oil_weight),
      })));
      toast.success("Escalation weights saved");
    } catch (e) { toast.error("Failed"); }
  };

  return (
    <div className="p-8 max-w-6xl">
      <div className="mb-8">
        <div className="text-xs uppercase tracking-[0.2em] text-slate-500 mb-2">Configuration</div>
        <h1 className="font-heading text-3xl font-semibold tracking-tight text-slate-900 klein-underline">Admin Parameters</h1>
        <p className="text-sm text-slate-600 mt-3 max-w-2xl">
          Calibrate scaling exponents (capacity factor method) and steel/oil escalation weights per equipment category.
        </p>
      </div>

      <section className="mb-10">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-heading text-lg font-medium text-slate-900">Scale Exponents (n)</h2>
          <Button onClick={saveExponents} className="rounded-none bg-[#002FA7] hover:bg-[#002480]" data-testid="save-exponents-btn">Save Exponents</Button>
        </div>
        <div className="border border-border bg-white">
          <table className="w-full data-table">
            <thead>
              <tr>
                <th className="text-left px-3 py-2.5">Category</th>
                <th className="text-right px-3 py-2.5">Default n</th>
                <th className="text-right px-3 py-2.5 w-40">Current n</th>
              </tr>
            </thead>
            <tbody>
              {exponents.map((row, idx) => (
                <tr key={row.category} data-testid={`exp-row-${row.category}`}>
                  <td className="px-3 py-2 text-slate-800">{row.label}</td>
                  <td className="px-3 py-2 text-right font-mono-num text-slate-500">{row.default_n}</td>
                  <td className="px-3 py-2 text-right">
                    <Input type="number" step="0.01" value={row.n} onChange={(e) => {
                      const v = [...exponents]; v[idx] = { ...row, n: e.target.value }; setExponents(v);
                    }} className="rounded-none font-mono-num text-right h-8" data-testid={`exp-input-${row.category}`} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="text-xs text-slate-500 mt-2">Formula: Cost_new = Cost_hist × (Size_new / Size_hist)^n</div>
      </section>

      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-heading text-lg font-medium text-slate-900">Escalation Weights (Steel / Oil)</h2>
          <Button onClick={saveWeights} className="rounded-none bg-[#002FA7] hover:bg-[#002480]" data-testid="save-weights-btn">Save Weights</Button>
        </div>
        <div className="border border-border bg-white">
          <table className="w-full data-table">
            <thead>
              <tr>
                <th className="text-left px-3 py-2.5">Category</th>
                <th className="text-right px-3 py-2.5">Default Steel / Oil</th>
                <th className="text-right px-3 py-2.5 w-32">Steel</th>
                <th className="text-right px-3 py-2.5 w-32">Oil</th>
              </tr>
            </thead>
            <tbody>
              {weights.map((row, idx) => (
                <tr key={row.category} data-testid={`weight-row-${row.category}`}>
                  <td className="px-3 py-2 text-slate-800">{row.label}</td>
                  <td className="px-3 py-2 text-right font-mono-num text-slate-500 text-xs">{row.default_steel} / {row.default_oil}</td>
                  <td className="px-3 py-2 text-right">
                    <Input type="number" step="0.05" min={0} max={1} value={row.steel_weight} onChange={(e) => {
                      const v = [...weights]; v[idx] = { ...row, steel_weight: e.target.value }; setWeights(v);
                    }} className="rounded-none font-mono-num text-right h-8" data-testid={`steel-input-${row.category}`} />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Input type="number" step="0.05" min={0} max={1} value={row.oil_weight} onChange={(e) => {
                      const v = [...weights]; v[idx] = { ...row, oil_weight: e.target.value }; setWeights(v);
                    }} className="rounded-none font-mono-num text-right h-8" data-testid={`oil-input-${row.category}`} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="text-xs text-slate-500 mt-2">Formula: Esc = 1 + steel_w × Δ%_steel + oil_w × Δ%_oil · Weights per category must sum to 1.0.</div>
      </section>
    </div>
  );
}
