"use client";

import { TickerItem } from "@/types";

interface HiringTickerProps {
  items: TickerItem[];
}

const TONE_CLASS: Record<TickerItem["tone"], string> = {
  green: "text-console-green",
  yellow: "text-console-gold",
  blue: "text-console-blue",
  red: "text-console-red",
  neutral: "text-console-primary",
};

export default function HiringTicker({ items }: HiringTickerProps) {
  const loop = [...items, ...items];

  return (
    <div className="overflow-hidden border-b border-console-rule2 bg-ink-0">
      <div className="ticker-track flex items-center gap-6 px-4 py-2">
        {loop.map((item, index) => (
          <div
            key={`${item.id}-${index}`}
            className="flex items-center gap-3 whitespace-nowrap border-r border-console-rule2 pr-6 last:border-r-0"
          >
            <span className={`font-mono text-[10px] uppercase tracking-[0.18em] ${TONE_CLASS[item.tone]}`}>
              [{item.label}]
            </span>
            <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-console-primary">
              {item.message}
            </span>
            <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-console-dim">
              {item.age}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
