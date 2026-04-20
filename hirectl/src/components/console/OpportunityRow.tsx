"use client";

import { Opportunity, OpportunityActionState } from "@/types";

interface OpportunityRowProps {
  opportunity: Opportunity;
  active: boolean;
  onSelect: (opportunity: Opportunity) => void;
}

const ACTION_LABELS: Record<OpportunityActionState, string> = {
  apply_now: "APPLY NOW",
  reach_out: "REACH OUT",
  high_leverage: "HIGH LEVERAGE",
  early_signal: "EARLY SIGNAL",
};

const ACTION_CLASS: Record<OpportunityActionState, string> = {
  apply_now: "border-console-green text-console-green hover:bg-[rgba(74,138,90,0.08)]",
  reach_out: "border-console-gold text-console-gold hover:bg-[rgba(200,169,110,0.08)]",
  high_leverage: "border-console-blue text-console-blue hover:bg-[rgba(80,112,176,0.08)]",
  early_signal: "border-console-red text-console-red hover:bg-[rgba(184,64,64,0.08)]",
};

const URGENCY_CLASS: Record<Opportunity["urgency"], string> = {
  critical: "text-console-red",
  high: "text-console-gold",
  medium: "text-console-blue",
  low: "text-console-secondary",
};

const CONFIDENCE_CLASS: Record<Opportunity["confidence"], string> = {
  high: "border-console-green text-console-green",
  medium: "border-console-blue text-console-blue",
  low: "border-console-red text-console-red",
};

const EXECUTION_LABELS: Record<NonNullable<Opportunity["executionStatus"]>, string> = {
  tracking: "TRACKING",
  reached_out: "REACHED OUT",
  applied: "APPLIED",
  follow_up: "FOLLOW-UP",
  interview: "INTERVIEW",
  offer: "OFFER",
  closed: "CLOSED",
};

function scoreBarTone(score: number): string {
  if (score >= 75) return "bg-console-green";
  if (score >= 60) return "bg-console-gold";
  if (score >= 45) return "bg-console-blue";
  return "bg-console-red";
}

export default function OpportunityRow({
  opportunity,
  active,
  onSelect,
}: OpportunityRowProps) {
  const elevated = opportunity.rank <= 3;
  const scoreWidth = `${Math.max(8, Math.min(100, opportunity.score))}%`;

  return (
    <article
      className={`group grid grid-cols-[minmax(0,1fr)_220px] border-b border-console-rule2 transition ${
        active ? "bg-ink-2" : "bg-ink-1 hover:bg-ink-2"
      } ${elevated ? "border-l-2 border-l-console-gold" : "border-l-2 border-l-transparent"}`}
    >
      <button
        type="button"
        onClick={() => onSelect(opportunity)}
        className="grid min-w-0 grid-cols-[120px_minmax(0,1fr)] text-left outline-none focus-visible:ring-1 focus-visible:ring-console-gold"
        aria-label={`Open ${opportunity.companyName} opportunity dossier`}
      >
        <span
          className={`flex flex-col justify-center border-r border-console-rule2 px-4 py-5 ${
            elevated ? "bg-[rgba(200,169,110,0.06)]" : ""
          }`}
        >
          <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-console-dim">
            Score
          </span>

          <span className="mt-2 font-mono text-[44px] leading-none text-console-bright">
            {opportunity.score}
          </span>

          <span className="mt-3 h-[3px] w-full bg-ink-5">
            <span className={`block h-full ${scoreBarTone(opportunity.score)}`} style={{ width: scoreWidth }} />
          </span>

          <span
            className={`mt-3 font-mono text-[10px] uppercase tracking-[0.14em] ${URGENCY_CLASS[opportunity.urgency]}`}
          >
            {opportunity.urgency}
          </span>

          <span
            className={`mt-2 inline-flex w-fit border px-2 py-1 font-mono text-[9px] uppercase tracking-[0.14em] ${CONFIDENCE_CLASS[opportunity.confidence]}`}
          >
            {opportunity.confidence} confidence
          </span>

          <span className="mt-1 font-mono text-[10px] text-console-secondary">
            {opportunity.scoreDelta}
          </span>
        </span>

        <span className="min-w-0 px-5 py-5">
          <span className="flex items-start justify-between gap-3">
            <span className="min-w-0">
              <span className="block font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">
                #{opportunity.rank} {opportunity.companyName}
              </span>

              <span
                className={`mt-1 block font-serif italic leading-[1.05] text-console-bright ${
                  elevated ? "text-[30px]" : "text-[24px]"
                }`}
              >
                {opportunity.primaryRoleTitle}
              </span>
            </span>

            <span className="shrink-0 font-mono text-[10px] uppercase tracking-[0.12em] text-console-dim">
              {opportunity.postedAge}
            </span>
          </span>

          <span className="mt-3 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] uppercase tracking-[0.12em] text-console-secondary">
            <span>{opportunity.location}</span>
            <span>{opportunity.remoteLabel}</span>
            <span className="border border-console-rule3 px-2 py-1 text-console-gold">
              {opportunity.stageLabel}
            </span>
            <span>{opportunity.openRoles} roles</span>
            <span>{opportunity.signalCount} signals</span>
            {opportunity.watchlisted ? <span className="text-console-blue">Watchlist</span> : null}
          </span>

          <span className="mt-3 flex flex-wrap gap-2">
            {opportunity.stackTags.map((tag) => (
              <span
                key={tag}
                className="border border-console-rule3 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.1em] text-console-primary"
              >
                {tag}
              </span>
            ))}
          </span>

          <span className="mt-3 block max-w-[72ch] font-mono text-[11px] leading-5 text-console-primary">
            {opportunity.summary}
          </span>

          <span className="mt-3 grid gap-1">
            {opportunity.scoreReasons.slice(0, 3).map((reason) => (
              <span
                key={reason}
                className="font-mono text-[10px] uppercase tracking-[0.08em] text-console-secondary"
              >
                + {reason}
              </span>
            ))}
          </span>
        </span>
      </button>

      <div className="flex flex-col justify-between border-l border-console-rule2 px-4 py-5">
        <div className="space-y-2">
          {opportunity.primaryRoleUrl ? (
            <a
              href={opportunity.primaryRoleUrl}
              target="_blank"
              rel="noreferrer"
              className={`inline-flex w-full justify-center border px-3 py-2 font-mono text-[10px] uppercase tracking-[0.18em] transition ${ACTION_CLASS[opportunity.actionState]}`}
            >
              {ACTION_LABELS[opportunity.actionState]} →
            </a>
          ) : (
            <button
              type="button"
              onClick={() => onSelect(opportunity)}
              className={`inline-flex w-full justify-center border px-3 py-2 font-mono text-[10px] uppercase tracking-[0.18em] transition ${ACTION_CLASS[opportunity.actionState]}`}
            >
              {ACTION_LABELS[opportunity.actionState]} →
            </button>
          )}

          <button
            type="button"
            onClick={() => onSelect(opportunity)}
            className="inline-flex w-full justify-center border border-console-rule3 px-3 py-2 font-mono text-[10px] uppercase tracking-[0.16em] text-console-primary transition hover:border-console-gold hover:text-console-bright"
          >
            Open dossier
          </button>

          {opportunity.executionStatus ? (
            <span className="inline-flex w-full justify-center border border-console-rule3 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-console-primary">
              {EXECUTION_LABELS[opportunity.executionStatus]}
            </span>
          ) : null}
        </div>

        <div className="mt-4">
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-console-dim">
            Latest signal
          </div>

          <div className="mt-2 font-mono text-[11px] leading-5 text-console-primary">
            {opportunity.latestSignal}
          </div>

          <div className="mt-2 font-mono text-[10px] uppercase tracking-[0.12em] text-console-secondary">
            {opportunity.latestSignalAge || "Recent"}
          </div>
        </div>
      </div>
    </article>
  );
}
