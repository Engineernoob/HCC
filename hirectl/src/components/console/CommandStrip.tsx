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
    <section className="grid grid-cols-2 border-b border-console-rule2 bg-ink-1 md:grid-cols-5">
      {metrics.map((metric) => (
        <div
          key={metric.id}
          className="relative border-r border-t border-console-rule2 px-4 py-3 first:border-t-0 md:border-t-0 md:last:border-r-0"
        >
          <div className="console-label text-[9px]">
            {metric.label}
          </div>
          <div className={`mt-2 font-mono text-[28px] leading-none ${TONE_CLASS[metric.tone]}`}>
            {metric.value}
          </div>
          <div className="console-subtle mt-1">
            {metric.delta}
          </div>
          <div className={`absolute bottom-0 left-0 h-[2px] w-1/2 ${
            metric.tone === "green"
              ? "bg-console-green"
              : metric.tone === "yellow"
                ? "bg-console-gold"
                : metric.tone === "red"
                  ? "bg-console-red"
                  : "bg-console-blue"
          }`} />
        </div>
      ))}
    </section>
  );
}
