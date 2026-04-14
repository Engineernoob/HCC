"use client";

import { Signal } from "@/types";

interface SignalFeedItemProps {
  signal: Signal;
}

const TONE_CLASS: Record<Signal["scoreVariant"], string> = {
  high: "text-console-green",
  medium: "text-console-blue",
  low: "text-console-red",
};

const SURFACE_CLASS: Record<Signal["scoreVariant"], string> = {
  high: "bg-console-green/5",
  medium: "bg-console-blue/5",
  low: "bg-console-red/5",
};

function scoreLabel(signal: Signal) {
  if (signal.score >= 85) return "critical";
  if (signal.score >= 70) return "high";
  if (signal.score >= 55) return "active";
  return "watch";
}

export default function SignalFeedItem({ signal }: SignalFeedItemProps) {
  return (
    <div className={`border-b border-console-rule2 px-4 py-3 last:border-b-0 ${SURFACE_CLASS[signal.scoreVariant]}`}>
      <div className="grid grid-cols-[68px_minmax(0,1fr)] gap-4">
        <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-console-dim">
          <div>{signal.ageLabel || signal.date}</div>
          <div className="mt-2 text-console-secondary">{signal.timestamp ? new Date(signal.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "--:--"}</div>
        </div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`font-mono text-[10px] uppercase tracking-[0.16em] ${TONE_CLASS[signal.scoreVariant]}`}>
              {signal.typeLabel}
            </span>
            <span className="border border-console-rule2 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-console-secondary">
              {signal.sourceLabel}
            </span>
            <span className="border border-console-rule2 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-console-dim">
              {scoreLabel(signal)} · {signal.score}
            </span>
            <div className="truncate font-mono text-[10px] uppercase tracking-[0.14em] text-console-primary">
              {signal.companyName}
            </div>
          </div>
          <div className="mt-2 font-mono text-[11px] uppercase tracking-[0.08em] text-console-bright">
            {signal.headline}
          </div>
          <div className="mt-2 grid gap-2 md:grid-cols-[minmax(0,1fr)_220px]">
            <div className="font-mono text-[10px] leading-5 text-console-secondary">
              {signal.detail}
            </div>
            <div className="border-l border-console-rule2 pl-3 font-mono text-[10px] uppercase tracking-[0.12em] text-console-dim">
              <div className="text-console-gold">Operator note</div>
              <div className="mt-2 leading-5 text-console-secondary">{signal.operatorHint}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
