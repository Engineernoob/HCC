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
  apply_now: "border-console-green text-console-green",
  reach_out: "border-console-gold text-console-gold",
  high_leverage: "border-console-blue text-console-blue",
  early_signal: "border-console-red text-console-red",
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

export default function OpportunityRow({
  opportunity,
  active,
  onSelect,
}: OpportunityRowProps) {
  const elevated = opportunity.rank <= 3;

  return (
    <button
      type="button"
      onClick={() => onSelect(opportunity)}
      className={`group grid w-full grid-cols-[120px_minmax(0,1fr)_220px] border-b border-console-rule2 text-left transition ${
        active ? "bg-ink-2" : "bg-ink-1 hover:bg-ink-2"
      }`}
    >
      {/* ── SCORE BLOCK ── */}
      <div
        className={`border-r border-console-rule2 px-4 py-5 flex flex-col justify-center ${
          elevated ? "bg-[rgba(200,169,110,0.06)]" : ""
        }`}
      >
        <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-console-dim">
          SCORE
        </div>

        <div className="mt-2 font-mono text-[44px] leading-none text-console-bright">
          {opportunity.score}
        </div>

        <div
          className={`mt-2 font-mono text-[10px] uppercase tracking-[0.14em] ${URGENCY_CLASS[opportunity.urgency]}`}
        >
          {opportunity.urgency}
        </div>

        <div
          className={`mt-2 inline-flex w-fit border px-2 py-1 font-mono text-[9px] uppercase tracking-[0.14em] ${CONFIDENCE_CLASS[opportunity.confidence]}`}
        >
          {opportunity.confidence} confidence
        </div>

        <div className="mt-1 font-mono text-[10px] text-console-secondary">
          {opportunity.scoreDelta}
        </div>

        <div className="mt-3 space-y-1">
          {opportunity.scoreReasons.slice(0, 3).map((reason) => (
            <div
              key={reason}
              className="font-mono text-[10px] uppercase tracking-[0.08em] text-console-secondary"
            >
              + {reason}
            </div>
          ))}
        </div>
      </div>

      {/* ── MAIN INFO ── */}
      <div className="px-5 py-5">
        {/* Header */}
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">
              #{opportunity.rank} {opportunity.companyName}
            </div>

            <div
              className={`mt-1 font-serif italic leading-[1.05] text-console-bright ${
                elevated ? "text-[30px]" : "text-[24px]"
              }`}
            >
              {opportunity.primaryRoleTitle}
            </div>
          </div>

          <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-console-dim">
            {opportunity.postedAge}
          </div>
        </div>

        {/* Metadata */}
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] uppercase tracking-[0.12em] text-console-secondary">
          <span>{opportunity.location}</span>
          <span>{opportunity.remoteLabel}</span>
          <span className="border border-console-rule3 px-2 py-1 text-console-gold">
            {opportunity.stageLabel}
          </span>
          <span>{opportunity.openRoles} roles</span>
          <span>{opportunity.signalCount} signals</span>
        </div>

        {/* Stack */}
        <div className="mt-3 flex flex-wrap gap-2">
          {opportunity.stackTags.map((tag) => (
            <span
              key={tag}
              className="border border-console-rule3 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.1em] text-console-primary"
            >
              {tag}
            </span>
          ))}
        </div>

        {/* Summary (tightened) */}
        <p className="mt-3 max-w-[65ch] font-mono text-[11px] leading-5 text-console-primary">
          {opportunity.summary}
        </p>
      </div>

      {/* ── ACTION PANEL ── */}
      <div className="border-l border-console-rule2 px-4 py-5 flex flex-col justify-between">
        {/* Action */}
        <div
          className={`inline-flex w-fit border px-3 py-2 font-mono text-[10px] uppercase tracking-[0.18em] ${ACTION_CLASS[opportunity.actionState]}`}
        >
          {ACTION_LABELS[opportunity.actionState]} →
        </div>

        {opportunity.executionStatus ? (
          <div className="mt-3 inline-flex w-fit border border-console-rule3 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-console-primary">
            {EXECUTION_LABELS[opportunity.executionStatus]}
          </div>
        ) : null}

        {/* Signal */}
        <div className="mt-4">
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-console-dim">
            SIGNAL
          </div>

          <div className="mt-2 font-mono text-[11px] leading-5 text-console-primary">
            {opportunity.latestSignal}
          </div>

          <div className="mt-2 font-mono text-[10px] uppercase tracking-[0.12em] text-console-secondary">
            {opportunity.latestSignalAge || "RECENT"}
          </div>
        </div>
      </div>
    </button>
  );
}
