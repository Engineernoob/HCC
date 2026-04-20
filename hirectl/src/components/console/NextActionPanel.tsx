"use client";

import { NextAction } from "@/types";

interface NextActionPanelProps {
  action: NextAction;
}

export default function NextActionPanel({ action }: NextActionPanelProps) {
  return (
    <section className="console-panel">
      <div className="console-panel-header">
        <div className="console-label">
          Next action
        </div>
        <div className="mt-1 font-serif text-[22px] italic text-console-bright">
          {action.title}
        </div>
      </div>

      <div className="px-4 py-4">
        <div className="console-tag border-console-gold text-console-gold">
          {action.urgency}
        </div>
        <p className="console-body mt-3">
          {action.summary}
        </p>
        <div className="mt-4 space-y-2">
          {action.steps.map((step, index) => (
            <div key={step} className="grid grid-cols-[28px_minmax(0,1fr)] gap-3 border-t border-console-rule2 pt-3 first:border-t-0 first:pt-0">
              <span className="flex h-5 w-5 items-center justify-center border border-console-rule3 font-mono text-[10px] text-console-dim">
                {index + 1}
              </span>
              <span className="console-body">{step}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
