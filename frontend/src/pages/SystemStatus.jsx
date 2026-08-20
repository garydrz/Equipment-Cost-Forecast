import { useEffect, useRef, useState } from "react";
import { api, API } from "@/lib/api";
import { toast } from "sonner";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Database, HardDrives, Globe, WifiSlash, ShieldCheck, Archive, CloudArrowUp, DownloadSimple, ArrowClockwise } from "@phosphor-icons/react";

function humanBytes(n) {
  if (!n) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v >= 100 ? 0 : 1)} ${units[i]}`;
}

function Card({ title, icon: Icon, children }) {
  return (
    <section className="border border-border bg-white">
      <header className="px-5 py-3 border-b border-border flex items-center gap-2">
        {Icon ? <Icon size={16} weight="regular" className="text-slate-600" /> : null}
        <h2 className="text-sm font-heading font-semibold text-slate-900">{title}</h2>
      </header>
      <div className="p-5">{children}</div>
    </section>
  );
}

function KV({ k, v, mono = true }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5 text-sm border-b border-slate-100 last:border-0">
      <span className="text-slate-500">{k}</span>
      <span className={`text-slate-900 text-right break-all ${mono ? "font-mono-num" : ""}`}>{v}</span>
    </div>
  );
}

export default function SystemStatus() {
  const [status, setStatus] = useState(null);
  const [backups, setBackups] = useState([]);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);

  const reload = async () => {
    try {
      const [{ data: s }, { data: b }] = await Promise.all([
        api.get("/system/status"),
        api.get("/system/backups"),
      ]);
      setStatus(s);
      setBackups(b.backups || []);
    } catch (e) {
      toast.error("Failed to load system status");
    }
  };

  useEffect(() => { reload(); }, []);

  const toggleOffline = async (next) => {
    setBusy(true);
    try {
      await api.put("/system/offline-mode", { offline_mode: next });
      toast.success(next ? "Offline mode enabled" : "Offline mode disabled");
      await reload();
    } catch (e) {
      toast.error("Failed to change offline mode");
    } finally { setBusy(false); }
  };

  const createBackup = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/system/backups");
      toast.success(`Backup created: ${data.filename}`);
      await reload();
    } catch (e) { toast.error("Backup failed"); }
    finally { setBusy(false); }
  };

  const restoreBackup = async (name) => {
    if (!window.confirm(`Restore ${name}? Current DB will be backed up first.`)) return;
    setBusy(true);
    try {
      await api.post(`/system/backups/${encodeURIComponent(name)}/restore`);
      toast.success("Restore complete. Reloading data…");
      setTimeout(() => window.location.reload(), 900);
    } catch (e) { toast.error("Restore failed"); }
    finally { setBusy(false); }
  };

  const deleteBackup = async (name) => {
    if (!window.confirm(`Delete backup ${name}?`)) return;
    setBusy(true);
    try {
      await api.delete(`/system/backups/${encodeURIComponent(name)}`);
      await reload();
    } catch (e) { toast.error("Delete failed"); }
    finally { setBusy(false); }
  };

  const importEquipment = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post("/equipment/import.csv", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(`Imported ${data.inserted}/${data.total_rows} rows (${data.errors?.length || 0} errors)`);
      if (data.errors?.length) console.warn("Import errors", data.errors);
    } catch (err) { toast.error("Import failed"); }
    finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  if (!status) return <div className="p-8 text-slate-500 text-sm">Loading system status…</div>;

  const offline = !!status.offline_mode;
  const dbExists = status.database?.exists;

  return (
    <div className="p-8 max-w-6xl">
      <div className="mb-6 flex items-start justify-between">
        <div>
          <div className="text-xs uppercase tracking-[0.2em] text-slate-500 mb-2">Local Runtime</div>
          <h1 className="font-heading text-3xl font-semibold tracking-tight text-slate-900 klein-underline">System Status</h1>
          <p className="text-sm text-slate-600 mt-3">
            Everything runs on this machine. SQLite storage, local cache, and a strict egress whitelist keep project data private.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={reload} data-testid="btn-refresh-status">
          <ArrowClockwise size={14} className="mr-1.5" /> Refresh
        </Button>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <Card title="Database" icon={Database}>
          <KV k="File" v={status.database.path} />
          <KV k="Size" v={humanBytes(status.database.size_bytes)} />
          <KV k="Available" v={dbExists ? "yes" : "no"} />
          <KV k="Model version" v={status.model_version} />
          <KV k="Config file" v={status.config_file} />
        </Card>

        <Card title="Network Policy" icon={offline ? WifiSlash : Globe}>
          <div className="flex items-center justify-between py-1.5" data-testid="offline-toggle-row">
            <div>
              <div className="text-sm text-slate-900 font-medium">Offline mode</div>
              <div className="text-xs text-slate-500">Block every outbound request, use only local caches.</div>
            </div>
            <Switch checked={offline} disabled={busy} onCheckedChange={toggleOffline} data-testid="switch-offline" />
          </div>
          <div className="mt-3 pt-3 border-t border-slate-100">
            <div className="flex items-center gap-1.5 text-xs uppercase tracking-widest text-slate-500 mb-2">
              <ShieldCheck size={12} /> Egress whitelist
            </div>
            <ul className="text-sm font-mono-num text-slate-800 space-y-1">
              {status.network_allowed_hosts.map((h) => <li key={h}>· {h}</li>)}
            </ul>
          </div>
        </Card>

        <Card title="FRED Indices" icon={HardDrives}>
          <KV k="API key configured" v={status.fred_status.api_key_present ? "yes" : "no (add to config/app_config.json → fred.api_key)"} mono={false} />
          <KV k="Last source" v={status.fred_status.last_source} />
          <KV k="Steel years cached" v={status.fred_status.steel_series_years} />
          <KV k="Oil years cached" v={status.fred_status.oil_series_years} />
          <KV k="Cache file" v={status.cache.fred_cache_file} />
        </Card>

        <Card title="FX Cache" icon={HardDrives}>
          <KV k="Currency pairs cached" v={status.fx_status.pairs_cached} />
          <KV k="Cache file" v={status.cache.fx_cache_file} />
          <p className="text-xs text-slate-500 mt-3">
            All Frankfurter responses are persisted locally so historical conversions keep working offline.
          </p>
        </Card>

        <Card title="Backups" icon={Archive}>
          <div className="flex justify-between items-center mb-3">
            <div className="text-sm text-slate-600">Directory: <span className="font-mono-num text-slate-800">{status.backup.dir}</span></div>
            <Button size="sm" onClick={createBackup} disabled={busy} data-testid="btn-create-backup">
              <CloudArrowUp size={14} className="mr-1.5" /> Create backup
            </Button>
          </div>
          {backups.length === 0 ? (
            <div className="text-sm text-slate-500 py-3">No backups yet.</div>
          ) : (
            <ul className="text-sm divide-y divide-slate-100">
              {backups.map((b) => (
                <li key={b.filename} className="py-2 flex items-center justify-between gap-3" data-testid={`backup-row-${b.filename}`}>
                  <div className="min-w-0">
                    <div className="font-mono-num text-slate-900 truncate">{b.filename}</div>
                    <div className="text-xs text-slate-500">{b.created_at} · {humanBytes(b.size_bytes)}</div>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <Button size="sm" variant="outline" disabled={busy} onClick={() => restoreBackup(b.filename)} data-testid={`btn-restore-${b.filename}`}>Restore</Button>
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => deleteBackup(b.filename)}>Delete</Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Import / Export" icon={DownloadSimple}>
          <div className="text-sm text-slate-700 mb-3">Historical repository — bulk file operations.</div>
          <div className="flex flex-wrap gap-2 mb-4">
            <Button size="sm" variant="outline" asChild data-testid="btn-export-eq-csv">
              <a href={`${API}/equipment/export.csv`}>Export CSV</a>
            </Button>
            <Button size="sm" variant="outline" asChild data-testid="btn-export-eq-xlsx">
              <a href={`${API}/equipment/export.xlsx`}>Export Excel</a>
            </Button>
            <label className="inline-flex items-center px-3 py-1.5 text-sm border border-border cursor-pointer hover:bg-slate-50">
              <input ref={fileRef} type="file" accept=".csv" onChange={importEquipment} className="hidden" data-testid="input-import-csv" />
              Import CSV…
            </label>
          </div>
          <div className="text-xs text-slate-500">
            CSV headers accepted: <span className="font-mono-num">category, subtype, size, size_unit, material, year, cost_original, currency, ...</span>
          </div>
        </Card>
      </div>
    </div>
  );
}
