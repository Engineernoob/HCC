"use client";

import { TimelineEvent } from "@/types";

interface TimelinePanelProps {
  events: TimelineEvent[];
}

const TONE_CLASS: Record<TimelineEvent["tone"], string> = {
  green: "text-console-green",
  yellow: "text-console-gold",
  blue: "text-console-blue",
  red: "text-console-red",
  neutral: "text-console-primary",
};

export default function TimelinePanel({ events }: TimelinePanelProps) {
  return (
    <section className="border border-console-rule2 bg-ink-1">
      <div className="border-b border-console-rule2 px-4 py-3">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">
          Activity timeline
        </div>
      </div>
      <div className="space-y-0">
        {events.map((event) => (
          <div key={event.id} className="grid grid-cols-[86px_68px_minmax(0,1fr)] gap-3 border-b border-console-rule2 px-4 py-3 last:border-b-0">
            <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-console-dim">
              {event.timestamp}
            </div>
            <div className={`font-mono text-[10px] uppercase tracking-[0.14em] ${TONE_CLASS[event.tone]}`}>
              {event.label}
            </div>
            <div>
              <div className="font-mono text-[11px] leading-5 text-console-primary">
                {event.detail}
              </div>
              <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.12em] text-console-secondary">
                {event.source}
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
