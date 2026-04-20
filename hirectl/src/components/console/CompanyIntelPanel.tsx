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
    <section className="console-panel">
      <div className="console-panel-header">
        <div className="console-label">
          Company intelligence
        </div>
        <div className="mt-1 flex items-start justify-between gap-4">
          <div>
            <div className="font-serif text-[24px] italic text-console-bright">{opportunity.companyName}</div>
            <div className="mt-2 flex flex-wrap gap-2">
              <span className="console-tag border-console-gold text-console-gold">
                Stage · {opportunity.stageLabel}
              </span>
              <span className="console-tag">
                Confidence · {opportunity.confidence}
              </span>
              {detail.execution ? (
                <span className="console-tag border-console-green text-console-green">
                  Execution · {detail.execution.statusLabel}
                </span>
              ) : null}
              {watchlisted ? (
                <span className="console-tag border-console-blue text-console-blue">
                  On watchlist
                </span>
              ) : null}
            </div>
          </div>
          <button
            type="button"
            onClick={onToggleWatchlist}
            className={`console-action ${
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
        <p className="console-body">
          {detail.aiSummary}
        </p>

        <div>
          <div className="console-label">
            Tech stack clues
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {detail.techStackClues.map((clue) => (
              <span
                key={clue}
                className="console-tag"
              >
                {clue}
              </span>
            ))}
          </div>
        </div>

        <div>
          <div className="console-label">
            Outreach recommendation
          </div>
          <p className="console-body mt-2 text-console-secondary">
            {detail.outreachRecommendation}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onOpenDetail}
            className="console-action border-console-gold text-console-bright"
          >
            Open detail sheet
          </button>
          <button
            type="button"
            onClick={onToggleWatchlist}
            className={`console-action ${
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
