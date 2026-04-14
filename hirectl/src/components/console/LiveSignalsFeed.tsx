"use client";

import { Signal } from "@/types";
import SignalFeedItem from "./SignalFeedItem";

interface LiveSignalsFeedProps {
  signals: Signal[];
  title: string;
}

export default function LiveSignalsFeed({ signals, title }: LiveSignalsFeedProps) {
  const highPriority = signals.filter((signal) => signal.scoreVariant === "high").length;

  return (
    <section className="border border-console-rule2 bg-ink-1">
      <div className="flex items-center justify-between border-b border-console-rule2 px-4 py-3">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">
            Live signals feed
          </div>
          <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.12em] text-console-secondary">
            {signals.length} events loaded · {highPriority} high-priority
          </div>
        </div>
        <div className="text-right font-mono text-[10px] uppercase tracking-[0.12em] text-console-secondary">
          {title}
        </div>
      </div>
      <div className="border-b border-console-rule2 bg-ink-0/70 px-4 py-2 font-mono text-[10px] uppercase tracking-[0.12em] text-console-dim">
        Time · type · company · source · impact
      </div>
      <div className="max-h-[420px] overflow-y-auto">
        {signals.length > 0 ? (
          signals.map((signal) => <SignalFeedItem key={signal.id} signal={signal} />)
        ) : (
          <div className="px-4 py-6">
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-gold">
              No live signals
            </div>
            <div className="mt-2 max-w-[70ch] font-mono text-[11px] leading-6 text-console-secondary">
              The feed is connected, but nothing fresh is currently breaking through the scoring threshold. Keep the queue open and wait for new hiring or funding motion.
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
