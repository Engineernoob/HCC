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

export default function SidebarNav({ active, watchlistCount, onChange }: SidebarNavProps) {
  return (
    <aside className="border-r border-console-rule2 bg-ink-1">
      <div className="border-b border-console-rule2 px-4 py-4">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">
          Operator Nav
        </div>
        <div className="mt-2 font-mono text-[11px] uppercase tracking-[0.14em] text-console-secondary">
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
              className={`mb-1 flex w-full items-center justify-between border px-3 py-3 text-left transition ${
                activeItem
                  ? "border-console-gold bg-[rgba(200,169,110,0.08)] text-console-bright"
                  : "border-transparent text-console-dim hover:border-console-rule3 hover:bg-ink-0 hover:text-console-primary"
              }`}
            >
              <span className="font-mono text-[11px] uppercase tracking-[0.16em]">
                {item.label}
              </span>
              {item.key === "watchlist" ? (
                <span className="font-mono text-[10px] text-console-secondary">{watchlistCount}</span>
              ) : (
                <span className="font-mono text-[10px] text-console-faint">::</span>
              )}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
