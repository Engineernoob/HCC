"use client";

import { CompanyDetail, Opportunity } from "@/types";

interface DecisionBriefingBarProps {
  opportunity: Opportunity | null;
  detail: CompanyDetail | null;
  resultCount: number;
  activeFilterCount: number;
  apiConnected: boolean;
  onOpenDetail: () => void;
}

const ACTION_COPY: Record<Opportunity["actionState"], string> = {
  apply_now: "Open role",
  reach_out: "Prep outreach",
  high_leverage: "Inspect leverage",
  early_signal: "Monitor window",
};

const CONFIDENCE_TONE: Record<Opportunity["confidence"], string> = {
  high: "text-console-green",
  medium: "text-console-blue",
  low: "text-console-red",
};

export default function DecisionBriefingBar({
  opportunity,
  detail,
  resultCount,
  activeFilterCount,
  apiConnected,
  onOpenDetail,
}: DecisionBriefingBarProps) {
  if (!opportunity) {
    return (
      <section className="border-b border-console-rule2 bg-ink-1 px-4 py-3">
        <div className="console-label text-console-gold">
          No target selected
        </div>
        <div className="console-body mt-1 text-console-secondary">
          Relax the current filters or wait for the next ingest cycle. The console is withholding action when the evidence is too thin.
        </div>
      </section>
    );
  }

  const topEvidence = detail?.scoreEvidence?.[0];
  const roleUrl = opportunity.primaryRoleUrl || detail?.openRoles.find((role) => role.url)?.url;

  return (
    <section className="border-b border-console-rule2 bg-ink-1">
      <div className="grid grid-cols-[minmax(0,1fr)_220px_220px] divide-x divide-console-rule2">
        <div className="px-4 py-3">
          <div className="flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-console-dim">
            <span>Selected target</span>
            <span className={apiConnected ? "text-console-green" : "text-console-red"}>
              {apiConnected ? "live backend" : "offline"}
            </span>
            <span>{resultCount} in queue</span>
            {activeFilterCount > 0 ? <span>{activeFilterCount} filters active</span> : null}
          </div>

          <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="font-serif text-[25px] italic leading-none text-console-bright">
              {opportunity.companyName}
            </span>
            <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-console-primary">
              {opportunity.primaryRoleTitle}
            </span>
          </div>

          <div className="mt-2 max-w-[105ch] font-mono text-[11px] leading-5 text-console-secondary">
            {topEvidence
              ? `${topEvidence.contribution >= 0 ? "+" : ""}${topEvidence.contribution} ${topEvidence.label}: ${topEvidence.note}`
              : opportunity.latestSignal}
          </div>
        </div>

        <div className="grid grid-cols-2 divide-x divide-console-rule2">
          <div className="px-4 py-3">
            <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-console-dim">Score</div>
            <div className="mt-1 font-mono text-[30px] leading-none text-console-bright">{opportunity.score}</div>
            <div className={`mt-1 font-mono text-[10px] uppercase tracking-[0.12em] ${CONFIDENCE_TONE[opportunity.confidence]}`}>
              {opportunity.confidence} confidence
            </div>
          </div>
          <div className="px-4 py-3">
            <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-console-dim">Window</div>
            <div className="mt-2 font-mono text-[12px] uppercase tracking-[0.12em] text-console-primary">
              {opportunity.postedAge}
            </div>
            <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.12em] text-console-secondary">
              {opportunity.openRoles} roles / {opportunity.signalCount} signals
            </div>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 px-4 py-3">
          {roleUrl ? (
            <a
              href={roleUrl}
              target="_blank"
              rel="noreferrer"
              className="console-action border-console-green text-console-green hover:bg-[rgba(74,138,90,0.08)]"
            >
              {ACTION_COPY[opportunity.actionState]}
            </a>
          ) : (
            <button
              type="button"
              disabled
              className="console-action cursor-not-allowed text-console-dim hover:border-console-rule3 hover:bg-transparent hover:text-console-dim"
            >
              No role URL
            </button>
          )}
          <button
            type="button"
            onClick={onOpenDetail}
            className="console-action border-console-gold text-console-bright"
          >
            Dossier
          </button>
        </div>
      </div>

      <div className="border-t border-console-rule2 px-4 py-2 font-mono text-[10px] uppercase tracking-[0.14em] text-console-dim">
        Shortcuts: / search · J/K move queue · Enter open dossier · Esc close
      </div>
    </section>
  );
}
