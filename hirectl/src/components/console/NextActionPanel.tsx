"use client";

import { NextAction } from "@/types";

interface NextActionPanelProps {
  action: NextAction;
}

export default function NextActionPanel({ action }: NextActionPanelProps) {
  return (
    <section className="border border-console-rule2 bg-ink-1">
      <div className="border-b border-console-rule2 px-4 py-3">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">
          Next action
        </div>
        <div className="mt-1 font-serif text-[22px] italic text-console-bright">
          {action.title}
        </div>
      </div>

      <div className="px-4 py-4">
        <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-console-gold">
          {action.urgency}
        </div>
        <p className="mt-3 font-mono text-[11px] leading-6 text-console-primary">
          {action.summary}
        </p>
        <div className="mt-4 space-y-2">
          {action.steps.map((step, index) => (
            <div key={step} className="grid grid-cols-[24px_minmax(0,1fr)] gap-3 border-t border-console-rule2 pt-2 first:border-t-0 first:pt-0">
              <span className="font-mono text-[11px] text-console-dim">{index + 1}.</span>
              <span className="font-mono text-[11px] leading-6 text-console-primary">{step}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
