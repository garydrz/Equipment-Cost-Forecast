import { NavLink } from "react-router-dom";
import { GridFour, Database, Sliders, TrendUp, Gauge } from "@phosphor-icons/react";

const items = [
  { to: "/", label: "Projects", icon: GridFour, id: "nav-projects" },
  { to: "/repository", label: "Historical Repository", icon: Database, id: "nav-repository" },
  { to: "/admin", label: "Admin Parameters", icon: Sliders, id: "nav-admin" },
  { to: "/indices", label: "Indices", icon: TrendUp, id: "nav-indices" },
  { to: "/system", label: "System Status", icon: Gauge, id: "nav-system" },
];

export default function Sidebar() {
  return (
    <aside className="w-60 border-r border-border bg-white h-screen sticky top-0 flex flex-col" data-testid="app-sidebar">
      <div className="px-5 py-6 border-b border-border">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 flex items-center justify-center" style={{ background: "#002FA7" }}>
            <span className="text-white font-heading font-bold text-sm">EP</span>
          </div>
          <div>
            <div className="font-heading font-semibold text-sm text-slate-900 leading-tight">EPC Estimator</div>
            <div className="text-[10px] uppercase tracking-widest text-slate-500">Parametric Costs</div>
          </div>
        </div>
      </div>
      <nav className="flex-1 py-4">
        {items.map(({ to, label, icon: Icon, id }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            data-testid={id}
            className={({ isActive }) =>
              `flex items-center gap-3 px-5 py-2.5 text-sm border-l-2 transition-colors duration-150 ${
                isActive
                  ? "border-l-[#002FA7] bg-slate-50 text-slate-900 font-medium"
                  : "border-l-transparent text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              }`
            }
          >
            <Icon size={18} weight="regular" />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="px-5 py-4 border-t border-border text-[10px] uppercase tracking-widest text-slate-400">
        AACE 18R-97 Methodology
      </div>
    </aside>
  );
}
