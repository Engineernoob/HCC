"use client";

import { Opportunity } from "@/types";
import OpportunityRow from "./OpportunityRow";

interface RankedOpportunitiesProps {
  opportunities: Opportunity[];
  selectedCompanyId: string | null;
  title: string;
  subtitle: string;
  apiConnected: boolean;
  onSelect: (opportunity: Opportunity) => void;
}

export default function RankedOpportunities({
  opportunities,
  selectedCompanyId,
  title,
  subtitle,
  apiConnected,
  onSelect,
}: RankedOpportunitiesProps) {
  return (
    <section className="border border-console-rule2 bg-ink-1">
      <div className="flex items-end justify-between border-b border-console-rule2 px-5 py-4">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">
            Ranked opportunities
          </div>
          <h2 className="mt-1 font-serif text-[28px] italic text-console-bright">{title}</h2>
        </div>
        <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-console-secondary">
          {subtitle}
        </div>
      </div>

      <div>
        {opportunities.length > 0 ? (
          opportunities.map((opportunity) => (
            <OpportunityRow
              key={opportunity.id}
              opportunity={opportunity}
              active={selectedCompanyId === opportunity.companyId}
              onSelect={onSelect}
            />
          ))
        ) : (
          <div className="px-5 py-8">
            <div className="font-serif text-[28px] italic text-console-bright">
              {apiConnected ? "No matching opportunities in the current filter window." : "Backend offline. Running on fallback intelligence only."}
            </div>
            <p className="mt-3 max-w-[70ch] font-mono text-[11px] leading-6 text-console-secondary">
              {apiConnected
                ? "Broaden the quick filters or switch sections. The console is avoiding fake precision when the current queue does not support a real action recommendation."
                : "The dashboard is showing static fallback data because the API is unavailable. Bring the backend up to restore live roles, signals, and company detail."}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
