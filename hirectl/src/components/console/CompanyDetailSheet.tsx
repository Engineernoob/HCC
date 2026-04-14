"use client";

import { CompanyDetail, ExecutionStatus } from "@/types";

interface CompanyDetailSheetProps {
  detail: CompanyDetail | null;
  open: boolean;
  watchlisted: boolean;
  onToggleWatchlist?: () => void;
  onUpdateExecution?: (status: ExecutionStatus) => void;
  executionSaving?: boolean;
  onClose: () => void;
}

const TONE_CLASS = {
  green: "text-console-green",
  yellow: "text-console-gold",
  blue: "text-console-blue",
  red: "text-console-red",
  neutral: "text-console-primary",
} as const;

export default function CompanyDetailSheet({
  detail,
  open,
  watchlisted,
  onToggleWatchlist,
  onUpdateExecution,
  executionSaving = false,
  onClose,
}: CompanyDetailSheetProps) {
  return (
    <div className={`fixed inset-0 z-50 transition ${open ? "pointer-events-auto" : "pointer-events-none"}`}>
      <div
        onClick={onClose}
        className={`absolute inset-0 bg-black/55 transition ${open ? "opacity-100" : "opacity-0"}`}
      />
      <aside
        className={`sheet-scroll absolute right-0 top-0 h-full w-[560px] overflow-y-auto border-l border-console-rule2 bg-ink-0 transition-transform duration-300 ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {detail ? (
          <>
            <div className="sticky top-0 z-10 border-b border-console-rule2 bg-ink-0 px-5 py-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">
                    Company detail
                  </div>
                  <div className="mt-1 font-serif text-[30px] italic leading-none text-console-bright">
                    {detail.companyName}
                  </div>
                  <div className="mt-2 font-mono text-[11px] uppercase tracking-[0.12em] text-console-secondary">
                    {detail.companyTagline}
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <span className="border border-console-gold px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-console-gold">
                      Stage · {detail.stageLabel}
                    </span>
                    {watchlisted ? (
                      <span className="border border-console-blue px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-console-blue">
                        Watchlist active
                      </span>
                    ) : null}
                  </div>
                </div>
                <div className="flex flex-wrap justify-end gap-2">
                  {onToggleWatchlist ? (
                    <button
                      type="button"
                      onClick={onToggleWatchlist}
                      className={`border px-3 py-2 font-mono text-[10px] uppercase tracking-[0.14em] ${
                        watchlisted
                          ? "border-console-blue text-console-blue"
                          : "border-console-gold text-console-gold"
                      }`}
                    >
                      {watchlisted ? "Remove watchlist" : "Add to watchlist"}
                    </button>
                  ) : null}
                  {onUpdateExecution ? (
                    <button
                      type="button"
                      disabled={executionSaving}
                      onClick={() => onUpdateExecution(detail.execution?.status === "applied" ? "follow_up" : "applied")}
                      className={`border px-3 py-2 font-mono text-[10px] uppercase tracking-[0.14em] ${
                        executionSaving
                          ? "border-console-rule3 text-console-dim"
                          : "border-console-green text-console-green"
                      }`}
                    >
                      {detail.execution?.status === "applied" ? "Mark follow-up" : "Mark applied"}
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={onClose}
                    className="border border-console-rule3 px-3 py-2 font-mono text-[10px] uppercase tracking-[0.14em] text-console-primary"
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>

            <div className="space-y-6 px-5 py-5">
              <section className="grid grid-cols-4 border border-console-rule2">
                <div className="border-r border-console-rule2 px-3 py-3">
                  <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-console-dim">Score</div>
                  <div className="mt-2 font-mono text-[30px] text-console-bright">{detail.score}</div>
                </div>
                <div className="border-r border-console-rule2 px-3 py-3">
                  <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-console-dim">Stage</div>
                  <div className="mt-2 font-mono text-[12px] uppercase tracking-[0.12em] text-console-primary">{detail.stageLabel}</div>
                </div>
                <div className="border-r border-console-rule2 px-3 py-3">
                  <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-console-dim">HQ</div>
                  <div className="mt-2 font-mono text-[12px] uppercase tracking-[0.12em] text-console-primary">{detail.headquarters}</div>
                </div>
                <div className="px-3 py-3">
                  <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-console-dim">Remote</div>
                  <div className="mt-2 font-mono text-[12px] uppercase tracking-[0.12em] text-console-primary">{detail.remoteLabel}</div>
                </div>
              </section>

              <section>
                <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">Score breakdown</div>
                <div className="mt-3 space-y-2">
                  {detail.scoreBreakdown.map((item) => (
                    <div key={item.label} className="grid grid-cols-[140px_56px_minmax(0,1fr)] items-start gap-3 border border-console-rule2 px-3 py-3">
                      <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-console-secondary">{item.label}</div>
                      <div className={`font-mono text-[18px] ${TONE_CLASS[item.tone]}`}>{item.value}</div>
                      <div className="font-mono text-[11px] leading-5 text-console-primary">{item.note}</div>
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">Why this scored high</div>
                <div className="mt-2 font-mono text-[11px] uppercase tracking-[0.12em] text-console-secondary">
                  Opportunity score: {detail.score}
                </div>
                <div className="mt-3 space-y-2">
                  {detail.scoreEvidence.map((item) => (
                    <div key={item.id} className="border border-console-rule2 px-3 py-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className={`font-mono text-[16px] ${item.contribution >= 0 ? "text-console-green" : "text-console-red"}`}>
                          {item.contribution >= 0 ? "+" : ""}
                          {item.contribution}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-console-dim">
                            {item.sourceType} · {item.timestamp}
                          </div>
                          <div className="mt-1 font-mono text-[12px] uppercase tracking-[0.08em] text-console-bright">
                            {item.label}
                          </div>
                          <div className="mt-2 font-mono text-[11px] leading-5 text-console-primary">
                            {item.note}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">Execution ledger</div>
                <div className="mt-3 space-y-2">
                  <div className="grid grid-cols-[120px_minmax(0,1fr)] gap-3 border border-console-rule2 px-3 py-3">
                    <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-console-dim">Current state</div>
                    <div className="font-mono text-[11px] leading-6 text-console-primary">
                      {detail.execution ? (
                        <>
                          <span className="uppercase tracking-[0.12em] text-console-bright">{detail.execution.statusLabel}</span>
                          <span className="mx-2 text-console-dim">/</span>
                          <span>{detail.execution.targetRoleTitle || "no target role stored"}</span>
                        </>
                      ) : (
                        "No execution record yet."
                      )}
                    </div>
                  </div>
                  {detail.execution?.events.map((event) => (
                    <div key={event.id} className="grid grid-cols-[92px_minmax(0,1fr)] gap-3 border border-console-rule2 px-3 py-3">
                      <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-console-dim">
                        {new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(new Date(event.occurredAt))}
                      </div>
                      <div>
                        <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-console-bright">
                          {event.statusLabel}
                        </div>
                        <div className="mt-1 font-mono text-[11px] leading-5 text-console-primary">
                          {event.label}
                        </div>
                        {event.notes ? (
                          <div className="mt-1 font-mono text-[11px] leading-5 text-console-secondary">
                            {event.notes}
                          </div>
                        ) : null}
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">Open roles</div>
                <div className="mt-3 space-y-2">
                  {detail.openRoles.map((role) => (
                    <div key={role.id} className="border border-console-rule2 px-3 py-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="font-serif text-[20px] italic text-console-bright">{role.title}</div>
                          <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.12em] text-console-secondary">
                            {role.team} · {role.location}
                          </div>
                        </div>
                        <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-console-dim">{role.postedAge}</div>
                      </div>
                      <div className="mt-2 font-mono text-[11px] leading-5 text-console-primary">{role.matchNote}</div>
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">Signal history</div>
                <div className="mt-3 space-y-2">
                  {detail.signalHistory.map((event) => (
                    <div key={event.id} className="grid grid-cols-[76px_74px_minmax(0,1fr)] gap-3 border border-console-rule2 px-3 py-3">
                      <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-console-dim">{event.timestamp}</div>
                      <div className={`font-mono text-[10px] uppercase tracking-[0.14em] ${TONE_CLASS[event.tone]}`}>{event.label}</div>
                      <div className="font-mono text-[11px] leading-5 text-console-primary">{event.detail}</div>
                    </div>
                  ))}
                </div>
              </section>

              <section className="grid gap-4 md:grid-cols-2">
                <div className="border border-console-rule2 px-3 py-3">
                  <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">Tech stack clues</div>
                  <div className="mt-3 space-y-2">
                    {detail.techStackClues.map((clue) => (
                      <div key={clue} className="font-mono text-[11px] leading-5 text-console-primary">
                        {clue}
                      </div>
                    ))}
                  </div>
                </div>
                <div className="border border-console-rule2 px-3 py-3">
                  <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">Outreach recommendation</div>
                  <div className="mt-3 font-mono text-[11px] leading-6 text-console-primary">
                    {detail.outreachRecommendation}
                  </div>
                </div>
              </section>

              <section className="border border-console-rule2 px-3 py-3">
                <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">AI summary</div>
                <div className="mt-3 font-mono text-[11px] leading-6 text-console-primary">
                  {detail.aiSummary}
                </div>
              </section>
            </div>
          </>
        ) : null}
      </aside>
    </div>
  );
}
