"use client";

import { QuickFilterKey } from "@/types";

interface TopBarProps {
  search: string;
  notifications: number;
  activeFilters: QuickFilterKey[];
  apiConnected: boolean;
  trackedCount: number;
  profileSummary: string;
  onSearchChange: (value: string) => void;
  onToggleFilter: (filter: QuickFilterKey) => void;
  onOpenSettings: () => void;
}

const FILTERS: Array<{ key: QuickFilterKey; label: string }> = [
  { key: "remote_us", label: "Remote US" },
  { key: "backend", label: "Backend" },
  { key: "ai_ml", label: "AI/ML" },
  { key: "infrastructure", label: "Infrastructure" },
  { key: "frontend", label: "Frontend" },
];

export default function TopBar({
  search,
  notifications,
  activeFilters,
  apiConnected,
  trackedCount,
  profileSummary,
  onSearchChange,
  onToggleFilter,
  onOpenSettings,
}: TopBarProps) {
  return (
    <header className="border-b border-console-rule2 bg-ink-1">
      <div className="grid grid-cols-[240px_minmax(0,1fr)_280px] items-stretch">
        <div className="border-r border-console-rule2 px-4 py-3">
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-console-dim">
            Hiring Intelligence Console
          </div>
          <div className="mt-2 font-serif text-[21px] italic leading-[1.08] text-console-bright">
            A real-time hiring intelligence system that identifies high-signal opportunities and tells you exactly how to act before they get saturated.
          </div>
          <div className="mt-3 flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.16em]">
            <span className={apiConnected ? "text-console-green" : "text-console-red"}>
              {apiConnected ? "Backend online" : "Backend offline"}
            </span>
            <span className="text-console-dim">/</span>
            <span className="text-console-secondary">{trackedCount} tracked</span>
          </div>
        </div>

        <div className="border-r border-console-rule2 px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="flex min-w-0 flex-1 items-center border border-console-rule3 bg-ink-0 px-3 py-2">
              <span className="mr-3 font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">
                Search
              </span>
              <input
                value={search}
                onChange={(event) => onSearchChange(event.target.value)}
                placeholder="company, role, stack, signal"
                className="w-full bg-transparent font-mono text-[12px] text-console-bright outline-none placeholder:text-console-dim"
              />
            </div>
            <div className="hidden items-center gap-2 lg:flex">
              <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">
                Filters
              </span>
            </div>
          </div>

          <div className="mt-2 flex flex-wrap gap-2">
            {FILTERS.map((filter) => {
              const active = activeFilters.includes(filter.key);
              return (
                <button
                  key={filter.key}
                  type="button"
                  onClick={() => onToggleFilter(filter.key)}
                  className={`border px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] transition ${
                    active
                      ? "border-console-gold bg-[rgba(200,169,110,0.08)] text-console-bright"
                      : "border-console-rule3 bg-transparent text-console-dim hover:border-console-dim hover:text-console-primary"
                  }`}
                >
                  {filter.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="grid grid-cols-3 divide-x divide-console-rule2">
          <div className="px-4 py-3">
            <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-console-dim">
              Notifications
            </div>
            <div className="mt-1 font-mono text-[22px] text-console-bright">
              {notifications}
            </div>
            <div className="mt-1 font-mono text-[10px] text-console-secondary">
              fresh signals
            </div>
          </div>
          <button
            type="button"
            onClick={onOpenSettings}
            className="px-4 py-3 text-left transition hover:bg-ink-2"
          >
            <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-console-dim">
              Settings
            </div>
            <div className="mt-1 font-mono text-[13px] uppercase tracking-[0.16em] text-console-primary">
              Profile
            </div>
            <div className="mt-1 font-mono text-[10px] text-console-secondary">
              edit ranking
            </div>
          </button>
          <div className="px-4 py-3">
            <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-console-dim">
              Operator
            </div>
            <div className="mt-1 font-mono text-[13px] uppercase tracking-[0.16em] text-console-bright">
              TD / ACTIVE
            </div>
            <div className="mt-1 font-mono text-[10px] text-console-secondary">
              {profileSummary}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
