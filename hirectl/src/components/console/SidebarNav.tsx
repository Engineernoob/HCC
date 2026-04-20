"use client";

import { SidebarSection } from "@/types";

interface SidebarNavProps {
  active: SidebarSection;
  watchlistCount: number;
  onChange: (section: SidebarSection) => void;
}

const ITEMS: Array<{ key: SidebarSection; label: string }> = [
  { key: "dashboard", label: "Dashboard" },
  { key: "signals", label: "Signals" },
  { key: "companies", label: "Companies" },
  { key: "watchlist", label: "Watchlist" },
  { key: "alerts", label: "Alerts" },
  { key: "outreach", label: "Outreach" },
];

const INDEX_LABELS: Record<SidebarSection, string> = {
  dashboard: "01",
  signals: "02",
  companies: "03",
  watchlist: "04",
  alerts: "05",
  outreach: "06",
};

export default function SidebarNav({ active, watchlistCount, onChange }: SidebarNavProps) {
  return (
    <aside className="border-r border-console-rule2 bg-ink-1">
      <div className="border-b border-console-rule2 px-4 py-4">
        <div className="console-label">
          Operator Nav
        </div>
        <div className="console-subtle mt-2">
          focus now, not later
        </div>
      </div>

      <nav className="p-2">
        {ITEMS.map((item) => {
          const activeItem = item.key === active;
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => onChange(item.key)}
              className={`console-focus mb-1 grid w-full grid-cols-[32px_minmax(0,1fr)_34px] items-center border px-3 py-3 text-left transition ${
                activeItem
                  ? "border-console-gold bg-[rgba(200,169,110,0.08)] text-console-bright"
                  : "border-transparent text-console-dim hover:border-console-rule3 hover:bg-ink-0 hover:text-console-primary"
              }`}
            >
              <span className="font-mono text-[10px] text-console-faint">
                {INDEX_LABELS[item.key]}
              </span>
              <span className="font-mono text-[11px] uppercase tracking-[0.16em]">
                {item.label}
              </span>
              {item.key === "watchlist" ? (
                <span className="text-right font-mono text-[10px] text-console-secondary">{watchlistCount}</span>
              ) : (
                <span className="text-right font-mono text-[10px] text-console-faint">::</span>
              )}
            </button>
          );
        })}
      </nav>

      <div className="mx-2 mt-3 border border-console-rule2 px-3 py-3">
        <div className="console-label text-[9px]">Mode</div>
        <div className="mt-2 font-mono text-[11px] uppercase tracking-[0.14em] text-console-green">
          Live operator
        </div>
        <div className="mt-2 console-body text-console-secondary">
          Use the queue as a triage surface. Open dossiers only when the action state is clear.
        </div>
      </div>
    </aside>
  );
}
