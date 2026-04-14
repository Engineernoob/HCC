"use client";

import { CompanyDetail, Opportunity } from "@/types";

interface CompanyIntelPanelProps {
  opportunity: Opportunity;
  detail: CompanyDetail;
  watchlisted: boolean;
  onOpenDetail: () => void;
  onToggleWatchlist: () => void;
}

export default function CompanyIntelPanel({
  opportunity,
  detail,
  watchlisted,
  onOpenDetail,
  onToggleWatchlist,
}: CompanyIntelPanelProps) {
  return (
    <section className="border border-console-rule2 bg-ink-1">
      <div className="border-b border-console-rule2 px-4 py-3">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">
          Company intelligence
        </div>
        <div className="mt-1 flex items-start justify-between gap-4">
          <div>
            <div className="font-serif text-[24px] italic text-console-bright">{opportunity.companyName}</div>
            <div className="mt-2 flex flex-wrap gap-2">
              <span className="border border-console-gold px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-console-gold">
                Stage · {opportunity.stageLabel}
              </span>
              <span className="border border-console-rule3 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-console-primary">
                Confidence · {opportunity.confidence}
              </span>
              {detail.execution ? (
                <span className="border border-console-green px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-console-green">
                  Execution · {detail.execution.statusLabel}
                </span>
              ) : null}
              {watchlisted ? (
                <span className="border border-console-blue px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-console-blue">
                  On watchlist
                </span>
              ) : null}
            </div>
          </div>
          <button
            type="button"
            onClick={onToggleWatchlist}
            className={`border px-3 py-2 font-mono text-[10px] uppercase tracking-[0.16em] transition ${
              watchlisted
                ? "border-console-blue text-console-blue hover:bg-[rgba(80,112,176,0.08)]"
                : "border-console-gold text-console-gold hover:bg-[rgba(200,169,110,0.08)]"
            }`}
          >
            {watchlisted ? "Remove watchlist" : "Add to watchlist"}
          </button>
        </div>
      </div>

      <div className="space-y-4 px-4 py-4">
        <p className="font-mono text-[11px] leading-6 text-console-primary">
          {detail.aiSummary}
        </p>

        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">
            Tech stack clues
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {detail.techStackClues.map((clue) => (
              <span
                key={clue}
                className="border border-console-rule3 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.1em] text-console-primary"
              >
                {clue}
              </span>
            ))}
          </div>
        </div>

        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">
            Outreach recommendation
          </div>
          <p className="mt-2 font-mono text-[11px] leading-6 text-console-secondary">
            {detail.outreachRecommendation}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onOpenDetail}
            className="border border-console-gold px-3 py-2 font-mono text-[10px] uppercase tracking-[0.16em] text-console-bright transition hover:bg-[rgba(200,169,110,0.08)]"
          >
            Open detail sheet
          </button>
          <button
            type="button"
            onClick={onToggleWatchlist}
            className={`border px-3 py-2 font-mono text-[10px] uppercase tracking-[0.16em] transition ${
              watchlisted
                ? "border-console-blue text-console-blue hover:bg-[rgba(80,112,176,0.08)]"
                : "border-console-rule3 text-console-primary hover:bg-ink-2"
            }`}
          >
            {watchlisted ? "Watchlist active" : "Mark watchlist"}
          </button>
        </div>
      </div>
    </section>
  );
}
