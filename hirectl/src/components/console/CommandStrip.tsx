"use client";

import { CommandMetric } from "@/types";

interface CommandStripProps {
  metrics: CommandMetric[];
}

const TONE_CLASS: Record<CommandMetric["tone"], string> = {
  green: "text-console-green",
  yellow: "text-console-gold",
  blue: "text-console-blue",
  red: "text-console-red",
  neutral: "text-console-primary",
};

export default function CommandStrip({ metrics }: CommandStripProps) {
  return (
    <section className="grid grid-cols-5 border-b border-console-rule2 bg-ink-1">
      {metrics.map((metric) => (
        <div key={metric.id} className="border-r border-console-rule2 px-4 py-3 last:border-r-0">
          <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-console-dim">
            {metric.label}
          </div>
          <div className={`mt-2 font-mono text-[26px] leading-none ${TONE_CLASS[metric.tone]}`}>
            {metric.value}
          </div>
          <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.12em] text-console-secondary">
            {metric.delta}
          </div>
        </div>
      ))}
    </section>
  );
}
