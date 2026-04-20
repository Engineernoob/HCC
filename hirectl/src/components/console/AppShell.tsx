"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  AccentTone,
  ConsoleDashboardData,
  ExecutionStatus,
  Opportunity,
  QuickFilterKey,
  SidebarSection,
} from "@/types";
import { apiSignalToInternal, loadCandidateProfile, loadConsoleDashboard, saveCandidateProfile, toggleCompanyWatchlist, updateCompanyExecution } from "@/lib/data";
import { subscribeToSignalStream } from "@/lib/api";
import { CandidateProfile } from "@/lib/personalization";
import TopBar from "./TopBar";
import HiringTicker from "./HiringTicker";
import SidebarNav from "./SidebarNav";
import CommandStrip from "./CommandStrip";
import RankedOpportunities from "./RankedOpportunities";
import DecisionBriefingBar from "./DecisionBriefingBar";
import LiveSignalsFeed from "./LiveSignalsFeed";
import CompanyIntelPanel from "./CompanyIntelPanel";
import TimelinePanel from "./TimelinePanel";
import NextActionPanel from "./NextActionPanel";
import ExecutionPanel from "./ExecutionPanel";
import CompanyDetailSheet from "./CompanyDetailSheet";
import ProfileSettingsSheet from "./ProfileSettingsSheet";

function matchesQuickFilter(opportunity: Opportunity, filter: QuickFilterKey): boolean {
  switch (filter) {
    case "remote_us":
      return opportunity.remote;
    case "backend":
      return opportunity.roleFocus === "backend" || opportunity.roleFocus === "fullstack" || opportunity.stackTags.some((tag) => ["go", "python", "api"].includes(tag.toLowerCase()));
    case "ai_ml":
      return opportunity.roleFocus === "ai_ml" || opportunity.stackTags.some((tag) => ["gpu", "cuda", "llm", "pytorch"].includes(tag.toLowerCase()));
    case "infrastructure":
      return opportunity.roleFocus === "infra" || opportunity.roleFocus === "distributed" || opportunity.stackTags.some((tag) => ["k8s", "grpc", "docker"].includes(tag.toLowerCase()));
    case "frontend":
      return opportunity.roleFocus === "frontend";
    default:
      return true;
  }
}

function actionHeadline(section: SidebarSection): { title: string; subtitle: string } {
  switch (section) {
    case "watchlist":
      return { title: "Watchlist focus", subtitle: "Operator-marked targets only" };
    case "alerts":
      return { title: "High urgency windows", subtitle: "Critical and high priority only" };
    case "outreach":
      return { title: "Actionable outreach targets", subtitle: "Companies where direct action matters now" };
    case "signals":
      return { title: "Signal-weighted opportunities", subtitle: "Prioritized against latest market movement" };
    case "companies":
      return { title: "Tracked companies", subtitle: "Full company universe ranked by score" };
    default:
      return { title: "Priority queue", subtitle: "Ranked by timing, fit, and signal density" };
  }
}

export default function AppShell() {
  const [dashboard, setDashboard] = useState<ConsoleDashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [section, setSection] = useState<SidebarSection>("dashboard");
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<QuickFilterKey[]>([]);
  const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [profileSaving, setProfileSaving] = useState(false);
  const [executionSavingCompanyId, setExecutionSavingCompanyId] = useState<string | null>(null);
  const [profile, setProfile] = useState<CandidateProfile | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  function applyWatchlistState(current: ConsoleDashboardData, companyId: string, watchlisted: boolean): ConsoleDashboardData {
    const opportunities = current.opportunities.map((opportunity) =>
      opportunity.companyId === companyId ? { ...opportunity, watchlisted } : opportunity
    );

    return {
      ...current,
      opportunities,
      commandMetrics: current.commandMetrics.map((metric) =>
        metric.id === "watchlist_delta"
          ? {
              ...metric,
              value: String(opportunities.filter((opportunity) => opportunity.watchlisted).length),
            }
          : metric
      ),
    };
  }

  async function handleToggleWatchlist(companyId: string, nextValue: boolean) {
    setDashboard((current) => (current ? applyWatchlistState(current, companyId, nextValue) : current));

    try {
      const confirmed = await toggleCompanyWatchlist(companyId, nextValue);
      setDashboard((current) => (current ? applyWatchlistState(current, companyId, confirmed) : current));
    } catch {
      setDashboard((current) => (current ? applyWatchlistState(current, companyId, !nextValue) : current));
    }
  }

  async function reloadDashboard() {
    setLoading(true);
    const [data, loadedProfile] = await Promise.all([
      loadConsoleDashboard(),
      loadCandidateProfile(),
    ]);
    setDashboard(data);
    setProfile(loadedProfile);
    setLoading(false);
  }

  async function handleUpdateExecution(companyId: string, status: ExecutionStatus) {
    const selectedRole = dashboard?.companyDetails[companyId]?.openRoles[0];
    const targetRoleTitle = selectedRole?.title ?? dashboard?.opportunities.find((opportunity) => opportunity.companyId === companyId)?.primaryRoleTitle ?? "";
    const targetRoleUrl = selectedRole?.url ?? "";
    const followUpDue =
      status === "follow_up"
        ? new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString()
        : null;

    setExecutionSavingCompanyId(companyId);
    try {
      await updateCompanyExecution(companyId, {
        status,
        label: `Operator marked ${status.replace(/_/g, " ")}`,
        notes: `Execution state updated to ${status.replace(/_/g, " ")} from the console.`,
        targetRoleTitle,
        targetRoleUrl,
        followUpDue,
      });
      await reloadDashboard();
    } finally {
      setExecutionSavingCompanyId(null);
    }
  }

  useEffect(() => {
    void reloadDashboard();
  }, []);

  useEffect(() => {
    const unsubscribe = subscribeToSignalStream({
      onSignal: (payload) => {
        const signal = apiSignalToInternal(payload);
        setDashboard((current) => {
          if (!current) {
            return current;
          }
          if (current.liveSignals.some((item) => item.id === signal.id)) {
            return current;
          }

          const tone: AccentTone =
            signal.scoreVariant === "high"
              ? "green"
              : signal.scoreVariant === "medium"
                ? "blue"
                : "red";

          const liveSignals = [signal, ...current.liveSignals].slice(0, 30);
          const ticker = [
            {
              id: signal.id,
              tone,
              label: signal.typeLabel.toUpperCase(),
              message: `${signal.companyName.toUpperCase()} ${signal.headline.toUpperCase()}`,
              age: signal.timestamp ? `${Math.max(1, Math.round((Date.now() - new Date(signal.timestamp).getTime()) / 3600000))}H AGO` : signal.date.toUpperCase(),
            },
            ...current.ticker,
          ].slice(0, 10);

          const opportunities = current.opportunities.map((opportunity) =>
            opportunity.companyId === signal.companyId
              ? {
                  ...opportunity,
                  signalCount: opportunity.signalCount + 1,
                  latestSignal: signal.headline,
                  latestSignalAge: signal.timestamp ? "now" : signal.date,
                }
              : opportunity
          );

          const detail = current.companyDetails[signal.companyId];
          const companyDetails = detail
            ? {
                ...current.companyDetails,
                [signal.companyId]: {
                  ...detail,
                  signalHistory: [
                    {
                      id: `live-${signal.id}`,
                      timestamp: "now",
                      label: signal.typeLabel.toUpperCase(),
                      detail: signal.headline,
                      tone,
                      source: signal.typeLabel,
                    },
                    ...detail.signalHistory,
                  ].slice(0, 8),
                },
              }
            : current.companyDetails;

          return {
            ...current,
            liveSignals,
            ticker,
            opportunities,
            companyDetails,
            generatedAt: new Date().toISOString(),
          };
        });
      },
    });

    return unsubscribe;
  }, []);

  const filteredOpportunities = useMemo(() => {
    if (!dashboard) {
      return [];
    }

    const lowered = search.trim().toLowerCase();
    return dashboard.opportunities.filter((opportunity) => {
      if (section === "watchlist" && !opportunity.watchlisted) return false;
      if (section === "alerts" && !["critical", "high"].includes(opportunity.urgency)) return false;
      if (
        section === "outreach" &&
        !(
          ["reach_out", "apply_now"].includes(opportunity.actionState) ||
          ["reached_out", "applied", "follow_up", "interview"].includes(opportunity.executionStatus ?? "")
        )
      ) {
        return false;
      }

      if (lowered) {
        const haystack = [
          opportunity.companyName,
          opportunity.companyTagline,
          opportunity.primaryRoleTitle,
          opportunity.summary,
          ...opportunity.stackTags,
        ]
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(lowered)) return false;
      }

      return filters.every((filter) => matchesQuickFilter(opportunity, filter));
    });
  }, [dashboard, filters, search, section]);

  const prioritizedOpportunities = useMemo(() => {
    const actionable = filteredOpportunities.filter(
      (opportunity) => opportunity.openRoles > 0 || opportunity.signalCount > 1 || opportunity.score >= 50
    );

    const base = actionable.length > 0 ? actionable : filteredOpportunities;
    return [...base].sort((a, b) => {
      if (b.openRoles !== a.openRoles) return b.openRoles - a.openRoles;
      if (b.score !== a.score) return b.score - a.score;
      return b.signalCount - a.signalCount;
    });
  }, [filteredOpportunities]);

  useEffect(() => {
    if (prioritizedOpportunities.length === 0) {
      setSelectedCompanyId(null);
      setSheetOpen(false);
      return;
    }

    if (!selectedCompanyId || !prioritizedOpportunities.some((opportunity) => opportunity.companyId === selectedCompanyId)) {
      setSelectedCompanyId(prioritizedOpportunities[0].companyId);
    }
  }, [prioritizedOpportunities, selectedCompanyId]);

  const selectedOpportunity = prioritizedOpportunities.find((opportunity) => opportunity.companyId === selectedCompanyId) ?? prioritizedOpportunities[0] ?? null;
  const selectedDetail = selectedOpportunity && dashboard ? dashboard.companyDetails[selectedOpportunity.companyId] : null;

  useEffect(() => {
    function shouldIgnoreKeyboardEvent(event: KeyboardEvent): boolean {
      const target = event.target as HTMLElement | null;
      if (event.metaKey || event.ctrlKey || event.altKey) return true;
      if (!target) return false;
      return ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable;
    }

    function moveSelection(direction: 1 | -1) {
      if (prioritizedOpportunities.length === 0) return;
      const currentIndex = Math.max(
        0,
        prioritizedOpportunities.findIndex((opportunity) => opportunity.companyId === selectedCompanyId)
      );
      const nextIndex = Math.min(
        prioritizedOpportunities.length - 1,
        Math.max(0, currentIndex + direction)
      );
      setSelectedCompanyId(prioritizedOpportunities[nextIndex].companyId);
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setSheetOpen(false);
        setProfileOpen(false);
        return;
      }

      if (shouldIgnoreKeyboardEvent(event)) {
        return;
      }

      if (event.key === "/") {
        event.preventDefault();
        searchInputRef.current?.focus();
        return;
      }

      if (event.key.toLowerCase() === "j") {
        event.preventDefault();
        moveSelection(1);
        return;
      }

      if (event.key.toLowerCase() === "k") {
        event.preventDefault();
        moveSelection(-1);
        return;
      }

      if (event.key === "Enter" && selectedOpportunity) {
        event.preventDefault();
        setSheetOpen(true);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [prioritizedOpportunities, selectedCompanyId, selectedOpportunity]);

  const visibleSignals = useMemo(() => {
    if (!dashboard) {
      return [];
    }

    if (section === "signals" || !selectedOpportunity) {
      return dashboard.liveSignals;
    }

    const scoped = dashboard.liveSignals.filter((signal) => signal.companyId === selectedOpportunity.companyId);
    return scoped.length > 0 ? scoped : dashboard.liveSignals;
  }, [dashboard, section, selectedOpportunity]);

  const watchlistCount = dashboard?.opportunities.filter((opportunity) => opportunity.watchlisted).length ?? 0;
  const header = actionHeadline(section);
  const profileSummary = profile
    ? profile.preferredRoles.slice(0, 2).map((role) => role.replace("_", " ")).join(" / ") || "profile loaded"
    : "loading profile";

  async function handleSaveProfile(nextProfile: CandidateProfile) {
    setProfileSaving(true);
    try {
      const saved = await saveCandidateProfile(nextProfile);
      setProfile(saved);
      await reloadDashboard();
      setProfileOpen(false);
    } finally {
      setProfileSaving(false);
    }
  }

  if (!dashboard) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-ink-0 font-mono text-[11px] uppercase tracking-[0.18em] text-console-dim">
        {loading ? "Loading console" : "Unable to load console"}
      </div>
    );
  }

  return (
    <div className="console-grid-bg min-h-screen bg-ink-0 text-console-primary">
      <TopBar
        searchInputRef={searchInputRef}
        search={search}
        notifications={Math.min(9, dashboard.liveSignals.filter((signal) => signal.scoreVariant === "high").length)}
        activeFilters={filters}
        apiConnected={dashboard.apiConnected}
        trackedCount={dashboard.opportunities.length}
        profileSummary={profileSummary}
        onSearchChange={setSearch}
        onToggleFilter={(filter) =>
          setFilters((current) =>
            current.includes(filter)
              ? current.filter((item) => item !== filter)
              : [...current, filter]
          )
        }
        onOpenSettings={() => setProfileOpen(true)}
      />
      <HiringTicker items={dashboard.ticker} />

      <div className="grid min-h-[calc(100vh-126px)] grid-cols-[220px_minmax(0,1fr)]">
        <SidebarNav active={section} watchlistCount={watchlistCount} onChange={setSection} />

        <div className="min-w-0">
          <CommandStrip metrics={dashboard.commandMetrics} />

          {!dashboard.apiConnected || prioritizedOpportunities.every((opportunity) => opportunity.openRoles === 0) ? (
            <div className="border-b border-console-rule2 bg-ink-1 px-4 py-3">
              <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-console-gold">
                {dashboard.apiConnected ? "Intel density is thin" : "Fallback mode active"}
              </div>
              <div className="mt-1 max-w-[90ch] font-mono text-[11px] leading-6 text-console-secondary">
                {dashboard.apiConnected
                  ? "The backend is connected, but the current queue does not have enough confirmed live roles to support aggressive action. Treat this screen as signal radar until stronger hiring confirmation lands."
                  : "The frontend is running, but the backend feed is unavailable from this session. Bring the API up to restore live companies, roles, and signals."}
              </div>
            </div>
          ) : null}

          <DecisionBriefingBar
            opportunity={selectedOpportunity}
            detail={selectedDetail}
            resultCount={prioritizedOpportunities.length}
            activeFilterCount={filters.length}
            apiConnected={dashboard.apiConnected}
            onOpenDetail={() => setSheetOpen(true)}
          />

          <div className="grid grid-cols-1 gap-4 p-4 xl:grid-cols-[minmax(0,1.3fr)_380px] 2xl:grid-cols-[minmax(0,1.45fr)_minmax(380px,0.9fr)]">
            <RankedOpportunities
              opportunities={prioritizedOpportunities}
              selectedCompanyId={selectedCompanyId}
              title={header.title}
              subtitle={header.subtitle}
              apiConnected={dashboard.apiConnected}
              onSelect={(opportunity) => {
                setSelectedCompanyId(opportunity.companyId);
                setSheetOpen(true);
              }}
            />

            <div className="space-y-4 xl:sticky xl:top-4 xl:self-start">
              {selectedDetail ? <NextActionPanel action={selectedDetail.nextAction} /> : null}
              {selectedDetail && selectedOpportunity ? (
                <ExecutionPanel
                  companyName={selectedOpportunity.companyName}
                  targetRoleTitle={selectedOpportunity.primaryRoleTitle}
                  execution={selectedDetail.execution}
                  saving={executionSavingCompanyId === selectedOpportunity.companyId}
                  onUpdateExecution={(status) => void handleUpdateExecution(selectedOpportunity.companyId, status)}
                />
              ) : null}
              <LiveSignalsFeed
                signals={visibleSignals}
                title={selectedOpportunity ? `${selectedOpportunity.companyName} context` : "global feed"}
              />
              {selectedOpportunity && selectedDetail ? (
                <CompanyIntelPanel
                  opportunity={selectedOpportunity}
                  detail={selectedDetail}
                  watchlisted={selectedOpportunity.watchlisted}
                  onOpenDetail={() => setSheetOpen(true)}
                  onToggleWatchlist={() =>
                    void handleToggleWatchlist(selectedOpportunity.companyId, !selectedOpportunity.watchlisted)
                  }
                />
              ) : null}
              {selectedDetail ? <TimelinePanel events={selectedDetail.signalHistory} /> : null}
            </div>
          </div>
        </div>
      </div>

      <CompanyDetailSheet
        detail={selectedDetail}
        open={sheetOpen && Boolean(selectedDetail)}
        watchlisted={selectedOpportunity?.watchlisted ?? false}
        onToggleWatchlist={
          selectedOpportunity
            ? () => void handleToggleWatchlist(selectedOpportunity.companyId, !selectedOpportunity.watchlisted)
            : undefined
        }
        onUpdateExecution={
          selectedOpportunity
            ? (status) => void handleUpdateExecution(selectedOpportunity.companyId, status)
            : undefined
        }
        executionSaving={selectedOpportunity ? executionSavingCompanyId === selectedOpportunity.companyId : false}
        onClose={() => setSheetOpen(false)}
      />
      {profile ? (
        <ProfileSettingsSheet
          open={profileOpen}
          profile={profile}
          saving={profileSaving}
          onClose={() => setProfileOpen(false)}
          onSave={(nextProfile) => void handleSaveProfile(nextProfile)}
        />
      ) : null}
    </div>
  );
}
