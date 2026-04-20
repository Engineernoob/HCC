"use client";

import { CompanyExecution, ExecutionStatus } from "@/types";

interface ExecutionPanelProps {
  companyName: string;
  targetRoleTitle: string;
  execution: CompanyExecution | null;
  saving: boolean;
  onUpdateExecution: (status: ExecutionStatus) => void;
}

const STATUS_CLASS: Record<ExecutionStatus, string> = {
  tracking: "border-console-rule3 text-console-primary",
  reached_out: "border-console-gold text-console-gold",
  applied: "border-console-green text-console-green",
  follow_up: "border-console-red text-console-red",
  interview: "border-console-blue text-console-blue",
  offer: "border-console-green text-console-green",
  closed: "border-console-rule3 text-console-dim",
};

const ACTIONS: Array<{ status: ExecutionStatus; label: string }> = [
  { status: "reached_out", label: "Reached out" },
  { status: "applied", label: "Applied" },
  { status: "follow_up", label: "Follow-up due" },
  { status: "interview", label: "Interview" },
];

function formatDate(value: string | null): string {
  if (!value) return "not set";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export default function ExecutionPanel({
  companyName,
  targetRoleTitle,
  execution,
  saving,
  onUpdateExecution,
}: ExecutionPanelProps) {
  return (
    <section className="console-panel">
      <div className="console-panel-header">
        <div className="console-label">
          Execution
        </div>
        <div className="mt-1 font-serif text-[22px] italic text-console-bright">
          {execution ? execution.statusLabel : `No execution history for ${companyName}`}
        </div>
        <div className="console-subtle mt-2">
          {execution?.targetRoleTitle || targetRoleTitle}
        </div>
      </div>

      <div className="space-y-4 px-4 py-4">
        <div className="flex flex-wrap gap-2">
          {(execution ? [execution.status] : (["tracking"] as ExecutionStatus[])).map((status) => (
            <span
              key={status}
              className={`console-tag ${STATUS_CLASS[status]}`}
            >
              {execution?.statusLabel || "Tracking"}
            </span>
          ))}
          {execution?.followUpDue ? (
            <span className="console-tag border-console-red text-console-red">
              Due {formatDate(execution.followUpDue)}
            </span>
          ) : null}
        </div>

        <div className="grid grid-cols-2 gap-2">
          {ACTIONS.map((action) => (
            <button
              key={action.status}
              type="button"
              disabled={saving}
              onClick={() => onUpdateExecution(action.status)}
              className={`console-action justify-start text-left ${
                saving
                  ? "cursor-wait border-console-rule3 text-console-dim"
                  : STATUS_CLASS[action.status]
              }`}
            >
              {action.label}
            </button>
          ))}
        </div>

        <div className="border border-console-rule2 px-3 py-3">
          <div className="console-label">
            Current note
          </div>
          <div className="console-body mt-2">
            {execution?.notes ||
              "No operator note yet. Use the status controls to start building decision history for this company."}
          </div>
        </div>

        <div>
          <div className="console-label">
            Recent activity
          </div>
          <div className="mt-3 space-y-2">
            {(execution?.events ?? []).slice(0, 4).map((event) => (
              <div key={event.id} className="border border-console-rule2 px-3 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-console-dim">
                      {event.statusLabel}
                    </div>
                    <div className="mt-1 font-mono text-[11px] uppercase tracking-[0.08em] text-console-bright">
                      {event.label}
                    </div>
                  </div>
                  <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-console-secondary">
                    {formatDate(event.occurredAt)}
                  </div>
                </div>
                {event.notes ? (
                  <div className="mt-2 font-mono text-[11px] leading-5 text-console-primary">
                    {event.notes}
                  </div>
                ) : null}
              </div>
            ))}
            {execution?.events?.length ? null : (
              <div className="border border-console-rule2 px-3 py-3 font-mono text-[11px] leading-6 text-console-secondary">
                No execution events recorded yet. The first action you log here becomes the start of the company-specific operating history.
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
