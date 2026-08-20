import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Plus, ArrowRight, Trash } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function ProjectsList() {
  const [projects, setProjects] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", output_currency: "EUR", target_year: new Date().getFullYear() });

  const load = async () => {
    try {
      const { data } = await api.get("/projects");
      setProjects(data);
    } catch (e) {
      toast.error("Failed to load projects");
    }
  };

  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!form.name.trim()) { toast.error("Project name required"); return; }
    try {
      await api.post("/projects", form);
      toast.success("Project created");
      setOpen(false);
      setForm({ name: "", description: "", output_currency: "EUR", target_year: new Date().getFullYear() });
      load();
    } catch (e) {
      toast.error("Failed to create project");
    }
  };

  const remove = async (id) => {
    if (!window.confirm("Delete this project and all its equipment?")) return;
    try {
      await api.delete(`/projects/${id}`);
      toast.success("Project deleted");
      load();
    } catch (e) {
      toast.error("Failed to delete");
    }
  };

  return (
    <div className="p-8 max-w-7xl">
      <div className="flex items-end justify-between mb-8">
        <div>
          <div className="text-xs uppercase tracking-[0.2em] text-slate-500 mb-2">Overview</div>
          <h1 className="font-heading text-4xl font-semibold tracking-tight text-slate-900 klein-underline">Projects</h1>
          <p className="text-sm text-slate-600 mt-3 max-w-2xl">
            Manage EPC project cost estimates. Each project aggregates equipment cost estimates with statistical confidence intervals per AACE Class 3-5.
          </p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button data-testid="add-project-btn" className="rounded-none bg-[#002FA7] hover:bg-[#002480] text-white h-10 px-5">
              <Plus size={16} className="mr-2" /> New Project
            </Button>
          </DialogTrigger>
          <DialogContent className="rounded-none max-w-lg">
            <DialogHeader>
              <DialogTitle className="font-heading">Create New Project</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div>
                <Label className="text-xs uppercase tracking-wider">Project name</Label>
                <Input data-testid="new-project-name-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-none mt-1" />
              </div>
              <div>
                <Label className="text-xs uppercase tracking-wider">Description</Label>
                <Textarea data-testid="new-project-desc-input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="rounded-none mt-1" rows={2} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs uppercase tracking-wider">Output currency</Label>
                  <Select value={form.output_currency} onValueChange={(v) => setForm({ ...form, output_currency: v })}>
                    <SelectTrigger data-testid="new-project-currency-select" className="rounded-none mt-1"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="EUR">EUR</SelectItem>
                      <SelectItem value="USD">USD</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs uppercase tracking-wider">Target year</Label>
                  <Input data-testid="new-project-year-input" type="number" value={form.target_year} onChange={(e) => setForm({ ...form, target_year: Number(e.target.value) })} className="rounded-none mt-1" />
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" className="rounded-none" onClick={() => setOpen(false)}>Cancel</Button>
              <Button data-testid="create-project-submit-btn" className="rounded-none bg-[#002FA7] hover:bg-[#002480]" onClick={create}>Create</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="projects-grid">
        {projects.length === 0 && (
          <div className="col-span-3 card-tech p-10 text-center text-slate-500 text-sm">No projects yet. Create one to start.</div>
        )}
        {projects.map((p) => (
          <div key={p.id} data-testid={`project-card-${p.id}`} className="card-tech p-5 flex flex-col hover:border-slate-400 transition-colors duration-150">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">Project</div>
                <div className="font-heading font-semibold text-lg text-slate-900">{p.name}</div>
              </div>
              <button data-testid={`delete-project-${p.id}`} onClick={() => remove(p.id)} className="text-slate-400 hover:text-red-600 transition-colors" title="Delete">
                <Trash size={16} />
              </button>
            </div>
            {p.description && <p className="text-xs text-slate-600 mt-2 line-clamp-2">{p.description}</p>}
            <div className="flex items-center gap-4 mt-4 text-xs">
              <div>
                <div className="text-[10px] uppercase tracking-widest text-slate-500">Currency</div>
                <div className="font-mono-num text-slate-900">{p.output_currency}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-widest text-slate-500">Target Yr</div>
                <div className="font-mono-num text-slate-900">{p.target_year}</div>
              </div>
            </div>
            <Link
              to={`/projects/${p.id}`}
              data-testid={`open-project-${p.id}`}
              className="mt-5 inline-flex items-center justify-center gap-2 border border-[#002FA7] text-[#002FA7] hover:bg-[#002FA7] hover:text-white transition-colors duration-150 py-2 text-sm font-medium"
            >
              Open Dashboard <ArrowRight size={14} />
            </Link>
          </div>
        ))}
      </div>
    </div>
  );
}
