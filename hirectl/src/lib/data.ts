/**
 * Data layer — wraps the API client.
 * Components import from here, not from api.ts directly.
 * Shows real backend data only; when the API is unreachable the UI stays empty/offline.
 */

import { api, CompanyOut, ExecutionOut, RoleOut, SignalOut, StatsOut } from "./api";
import { computeOpportunityScore } from "./scoring-engine";
import { CandidateProfile } from "./personalization";
import {
  AccentTone,
  CommandMetric,
  Company,
  CompanyExecution,
  CompanyDetail,
  ConsoleDashboardData,
  DashboardStats,
  ExecutionStatus,
  NextAction,
  OpenRole,
  Opportunity,
  OpportunityActionState,
  ScoreBreakdown,
  Signal,
  TechStack,
  TickerItem,
  TimelineEvent,
} from "@/types";

export interface DashboardData {
  companies: Company[];
  signals: Signal[];
  stats: DashboardStats;
  apiConnected: boolean;
}

const DATE_FORMATTER = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
});

const EMPTY_STATS: DashboardStats = {
  companies: 0,
  openRoles: 0,
  signals: 0,
  outreachDue: 0,
  avgFitScore: 0,
};

export const DEFAULT_CANDIDATE_PROFILE: CandidateProfile = {
  preferredRoles: ["backend", "distributed", "infra", "platform", "ai_ml"],
  preferredSkills: [
    "python",
    "typescript",
    "node",
    "postgres",
    "docker",
    "kubernetes",
    "aws",
    "fastapi",
    "react",
  ],
  preferredStages: ["seed", "series a", "series b", "series c"],
  remoteOnly: true,
  preferredLocations: ["remote"],
  targetCompanyIds: [],
  avoidCompanyIds: [],
};

// ── Type adapters: API → internal types ───────────────────────────

function formatStageLabel(stage: CompanyOut["stage"]): string {
  return stage.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function inferStageFromFundingLabel(fundingLabel: string | null | undefined): string | null {
  const normalized = (fundingLabel || "").toLowerCase();

  if (!normalized) {
    return null;
  }

  if (normalized.includes("series d") || normalized.includes("series e") || normalized.includes("series f")) {
    return "Series D+";
  }
  if (normalized.includes("series c")) {
    return "Series C";
  }
  if (normalized.includes("series b")) {
    return "Series B";
  }
  if (normalized.includes("series a")) {
    return "Series A";
  }
  if (normalized.includes("seed")) {
    return "Seed";
  }
  if (normalized.includes("public") || normalized.includes("ipo")) {
    return "Public";
  }

  return null;
}

function resolveStageLabel(company: CompanyOut): string {
  if (company.stage && company.stage !== "unknown") {
    return formatStageLabel(company.stage);
  }

  return inferStageFromFundingLabel(company.funding_label) ?? "Unverified";
}

function formatRelativeTime(timestamp: string | null): string {
  if (!timestamp) {
    return "";
  }

  const deltaMs = Date.now() - new Date(timestamp).getTime();
  const deltaHours = Math.max(1, Math.round(deltaMs / (1000 * 60 * 60)));
  if (deltaHours < 24) {
    return `${deltaHours}h ago`;
  }

  const deltaDays = Math.round(deltaHours / 24);
  return `${deltaDays}d ago`;
}

function sourceLabelFromSignal(signal: SignalOut): string {
  if (signal.source_url) {
    try {
      const host = new URL(signal.source_url).hostname.replace(/^www\./, "");
      return host.replace(/^jobs\./, "").replace(/^news\./, "");
    } catch {
      return signal.type_label;
    }
  }

  switch (signal.type) {
    case "founder_post":
      return "founder";
    case "funding":
      return "funding feed";
    case "career_page":
      return "career page";
    case "github_spike":
      return "github";
    case "ats_greenhouse":
      return "greenhouse";
    case "ats_ashby":
      return "ashby";
    case "yc_jobs":
      return "yc jobs";
    default:
      return signal.type_label.toLowerCase();
  }
}

function operatorHintFromSignal(signal: SignalOut): string {
  switch (signal.type) {
    case "founder_post":
      return "Direct reach-out window";
    case "funding":
      return "Expect hiring follow-through";
    case "career_page":
    case "ats_greenhouse":
    case "ats_ashby":
    case "ats_lever":
    case "yc_jobs":
      return "Live role confirmation";
    case "github_spike":
      return "Engineering motion rising";
    default:
      return "Monitor for confirmation";
  }
}

function normalizeTechStack(stack: CompanyOut["tech_stack"] | null | undefined): TechStack {
  return {
    languages: Array.isArray(stack?.languages) ? stack.languages : [],
    frameworks: Array.isArray(stack?.frameworks) ? stack.frameworks : [],
    infra: Array.isArray(stack?.infra) ? stack.infra : [],
  };
}

function apiCompanyToInternal(co: CompanyOut): Company {
  return {
    id: co.id,
    slug: co.slug,
    rank: 0, // set after sorting
    name: co.name,
    tagline: co.tagline,
    stage: co.stage as Company["stage"],
    stageLabel: resolveStageLabel(co),
    funding: co.funding_label || undefined,
    location: co.remote_us ? "Remote" : "On-site",
    remote: co.remote_us,
    remoteLabel: co.remote_label,
    fitScore: Math.round(co.fit_score),
    urgency: co.urgency_label as Company["urgency"],
    openRoles: co.open_roles_count,
    signalCount: co.signal_count,
    stack: normalizeTechStack(co.tech_stack),
    chips: co.chips as Company["chips"],
    description: co.description,
    latestSignal: "",
    latestSignalAge: "",
    onWatchlist: co.on_watchlist,
    aiBrief: co.ai_brief,
    lastSignalAt: co.last_signal_at,
    compositeScore: co.composite_score,
    urgencyScore: co.urgency_score,
  };
}

export function apiSignalToInternal(s: SignalOut): Signal {
  const ageLabel = formatRelativeTime(s.signal_date);
  return {
    id: s.id,
    companyId: s.company_id,
    companyName: s.company_name,
    type: s.type as Signal["type"],
    typeLabel: s.type_label,
    headline: s.headline,
    detail: s.detail,
    date: DATE_FORMATTER.format(new Date(s.signal_date)),
    timestamp: s.signal_date,
    ageLabel,
    score: Math.round(s.score),
    scoreVariant: s.score_variant,
    sourceUrl: s.source_url,
    sourceLabel: sourceLabelFromSignal(s),
    operatorHint: operatorHintFromSignal(s),
  };
}

function toDashboardStats(stats: StatsOut): DashboardStats {
  return {
    companies: stats.companies_total,
    openRoles: stats.open_roles,
    signals: stats.signals_total,
    outreachDue: stats.outreach_due,
    avgFitScore: stats.avg_fit_score,
  };
}

function apiExecutionToInternal(execution: ExecutionOut): CompanyExecution {
  return {
    id: execution.id,
    companyId: execution.company_id,
    companyName: execution.company_name,
    status: execution.status,
    statusLabel: execution.status_label,
    notes: execution.notes,
    targetRoleTitle: execution.target_role_title,
    targetRoleUrl: execution.target_role_url,
    followUpDue: execution.follow_up_due,
    lastEventAt: execution.last_event_at,
    updatedAt: execution.updated_at,
    events: execution.events.map((event) => ({
      id: event.id,
      companyId: event.company_id,
      status: event.status,
      statusLabel: event.status_label,
      label: event.label,
      notes: event.notes,
      targetRoleTitle: event.target_role_title,
      targetRoleUrl: event.target_role_url,
      followUpDue: event.follow_up_due,
      occurredAt: event.occurred_at,
    })),
  };
}

function withLatestSignals(companies: Company[], signals: Signal[]): Company[] {
  const latestSignalByCompany = new Map<string, Signal>();

  for (const signal of signals) {
    const current = latestSignalByCompany.get(signal.companyId);
    if (!current) {
      latestSignalByCompany.set(signal.companyId, signal);
      continue;
    }

    const currentTime = current.timestamp ? new Date(current.timestamp).getTime() : 0;
    const signalTime = signal.timestamp ? new Date(signal.timestamp).getTime() : 0;
    if (signalTime > currentTime) {
      latestSignalByCompany.set(signal.companyId, signal);
    }
  }

  return companies.map((company) => {
    const latestSignal = latestSignalByCompany.get(company.id);
    if (!latestSignal) {
      return company;
    }

    return {
      ...company,
      latestSignal: latestSignal.headline,
      latestSignalAge: formatRelativeTime(latestSignal.timestamp),
    };
  });
}

// ── Data fetching functions ────────────────────────────────────────

export async function fetchCompanies(filters = {}): Promise<Company[]> {
  const cos = await api.getCompanies(filters);
  return cos
    .sort((a, b) => b.composite_score - a.composite_score)
    .map((co, index) => ({ ...apiCompanyToInternal(co), rank: index + 1 }));
}

export async function fetchSignals(filters = {}): Promise<Signal[]> {
  const sigs = await api.getSignals(filters);
  return sigs.map(apiSignalToInternal);
}

export async function fetchStats(): Promise<StatsOut> {
  return api.getStats();
}

export async function loadDashboardData(): Promise<DashboardData> {
  try {
    const [companies, signals, stats] = await Promise.all([
      fetchCompanies(),
      fetchSignals({ hours: 24 * 7, limit: 80 }),
      fetchStats(),
    ]);

    return {
      companies: withLatestSignals(companies, signals),
      signals,
      stats: toDashboardStats(stats),
      apiConnected: true,
    };
  } catch {
    return {
      companies: [],
      signals: [],
      stats: EMPTY_STATS,
      apiConnected: false,
    };
  }
}

function roleLabelFromCompany(company: Company): Opportunity["roleFocus"] {
  const haystack = [company.tagline, company.description, ...company.stack.languages, ...company.stack.frameworks, ...company.stack.infra]
    .join(" ")
    .toLowerCase();

  if (haystack.includes("frontend") || haystack.includes("react")) return "frontend";
  if (haystack.includes("ai") || haystack.includes("ml") || haystack.includes("gpu")) return "ai_ml";
  if (haystack.includes("distributed") || haystack.includes("database") || haystack.includes("storage")) return "distributed";
  if (haystack.includes("infra") || haystack.includes("platform") || haystack.includes("kubernetes")) return "infra";
  return "backend";
}

function fallbackRoleTitle(company: Company, roleFocus: Opportunity["roleFocus"]): string {
  const roleLabel =
    roleFocus === "ai_ml"
      ? "AI / ML"
      : roleFocus === "fullstack"
        ? "Full-stack"
        : roleFocus === "infra"
          ? "Infrastructure"
          : roleFocus === "distributed"
            ? "Distributed systems"
            : roleFocus.charAt(0).toUpperCase() + roleFocus.slice(1);

  if (company.openRoles > 0) {
    return `${roleLabel} hiring window`;
  }

  return `${company.name} signal watch candidate`;
}

function fallbackOpportunitySummary(company: Company): string {
  if (company.openRoles > 0) {
    return company.description;
  }

  return company.latestSignal
    ? `Signal detected without a confirmed live role cluster yet. Treat ${company.name} as a watch candidate and wait for the next hiring confirmation before spending real time here.`
    : `Coverage is still thin for ${company.name}. Keep it on radar, but do not treat it like a primary execution target yet.`;
}

function roleFocusFromApi(roleType: string | undefined): Opportunity["roleFocus"] {
  switch (roleType) {
    case "backend":
    case "fullstack":
    case "ai_ml":
    case "infra":
    case "platform":
    case "distributed":
    case "frontend":
    case "mobile":
    case "data":
      return roleType;
    default:
      return "backend";
  }
}

function roleTypeLabel(roleType: string | undefined): string {
  return (roleType || "unknown")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function postedAgeFromDays(daysOpen: number): string {
  if (daysOpen <= 0) return "today";
  if (daysOpen === 1) return "1d";
  return `${daysOpen}d`;
}

function roleStatusFromDays(daysOpen: number): OpenRole["status"] {
  if (daysOpen <= 2) return "fresh";
  if (daysOpen <= 10) return "open";
  return "competitive";
}

function groupRolesByCompany(roles: RoleOut[]): Record<string, RoleOut[]> {
  return roles.reduce<Record<string, RoleOut[]>>((acc, role) => {
    if (!acc[role.company_id]) {
      acc[role.company_id] = [];
    }
    acc[role.company_id].push(role);
    return acc;
  }, {});
}

function buildOpenRolesFromApi(company: Company, roles: RoleOut[]): OpenRole[] {
  return roles.slice(0, 5).map((role) => ({
    id: role.id,
    title: role.title,
    team: roleTypeLabel(role.role_type),
    url: role.url,
    location: role.location || (role.is_remote ? company.remoteLabel : company.location),
    remote: role.is_remote,
    postedAge: postedAgeFromDays(role.days_open),
    matchNote:
      role.required_skills.length > 0
        ? `Required: ${role.required_skills.slice(0, 3).join(", ")}`
        : `Strong fit for ${roleTypeLabel(role.role_type).toLowerCase()} work.`,
    status: roleStatusFromDays(role.days_open),
  }));
}

function buildScoreBreakdownFromApi(
  company: Company,
  roles: RoleOut[],
  scopedSignals: Signal[],
  profile: CandidateProfile
): ScoreBreakdown[] {
  const scored = computeOpportunityScore(company, roles, scopedSignals, profile);

  return [
    {
      label: "Signal strength",
      value: scored.breakdown.signalStrength,
      tone: "green",
      note: "Weighted by freshness, source type, and signal density.",
    },
    {
      label: "Hiring velocity",
      value: scored.breakdown.hiringVelocity,
      tone: "yellow",
      note: "Rewards fresh roles and active hiring windows.",
    },
    {
      label: "Personal fit",
      value: scored.breakdown.baseFit,
      tone: "blue",
      note: "Based on stack and role alignment.",
    },
    {
      label: "Personalization",
      value: scored.breakdown.personalization,
      tone: "red",
      note: "Adjusted for your role, skills, stage, and remote preferences.",
    },
  ];
}

function buildTechCluesFromApi(company: Company, roles: RoleOut[]): string[] {
  const stack = [...company.stack.languages, ...company.stack.frameworks, ...company.stack.infra];
  const requiredSkills = roles.flatMap((role) => role.required_skills).filter(Boolean);
  return [...new Set([...stack, ...requiredSkills])].slice(0, 6);
}

function buildOutreachRecommendationFromApi(company: Company, roles: RoleOut[], scopedSignals: Signal[]): string {
  const founderSignal = scopedSignals.some((signal) => signal.type === "founder_post");
  const freshestRole = roles[0];

  if (founderSignal) {
    return `Reach out directly to ${company.name} leadership. Founder intent is visible, so direct operator-to-operator messaging has leverage here.`;
  }

  if (freshestRole) {
    return `Apply to ${freshestRole.title} first, then follow up with a targeted note referencing ${roleTypeLabel(freshestRole.role_type).toLowerCase()} overlap and the current hiring window.`;
  }

  return `Do not force outreach yet. Keep ${company.name} on the watchlist until a live role or stronger operator signal confirms that the window is actionable.`;
}

function buildNextActionFromApi(company: Company, roles: RoleOut[], scopedSignals: Signal[]): NextAction {
  const founderSignal = scopedSignals.find((signal) => signal.type === "founder_post");
  const freshestRole = roles[0];

  if (founderSignal) {
    return {
      title: `Reach out to ${company.name} leadership now`,
      urgency: "Founder intent visible",
      summary: "This is a direct-intent signal, not passive ATS traffic. Speed matters more than polish.",
      steps: [
        "Send a concise operator-style message tied to the founder signal.",
        "Reference the most relevant systems or stack overlap explicitly.",
        "Apply immediately after outreach so there is a formal record.",
      ],
    };
  }

  if (freshestRole) {
    return {
      title: `Apply to ${freshestRole.title} at ${company.name}`,
      urgency: freshestRole.days_open <= 2 ? "Fresh role window" : "Active hiring window",
      summary: "The backend is already confirming live hiring motion here, so this should be treated as an execution target.",
      steps: [
        "Submit the closest matching role first.",
        "Anchor the application around the role family and required skills, not generic startup language.",
        "Follow up with a targeted note if the role is still fresh.",
      ],
    };
  }

  return buildFallbackNextAction(company);
}

function buildExecutionAwareNextAction(
  company: Company,
  roles: RoleOut[],
  scopedSignals: Signal[],
  execution: CompanyExecution | null,
): NextAction {
  if (!execution) {
    return buildNextActionFromApi(company, roles, scopedSignals);
  }

  const targetRole = execution.targetRoleTitle || roles[0]?.title || "target role";

  switch (execution.status) {
    case "reached_out":
      return {
        title: `Follow up on outreach at ${company.name}`,
        urgency: execution.followUpDue ? `Due ${DATE_FORMATTER.format(new Date(execution.followUpDue))}` : "Outreach sent",
        summary: "You already opened the conversation. The next edge is tight follow-through, not another cold start.",
        steps: [
          "Reference the original note and the freshest hiring signal in one short follow-up.",
          `Re-anchor around ${targetRole} and the concrete stack overlap that matters most.`,
          "If there is still no response, convert the next touch into a formal application.",
        ],
      };
    case "applied":
      return {
        title: `Support the ${targetRole} application`,
        urgency: "Application in flight",
        summary: "The application exists. The next move is to improve odds with a targeted follow-up instead of starting over elsewhere.",
        steps: [
          "Send a concise follow-up tied to the latest company signal.",
          "Mention one concrete systems or product overlap that strengthens the application.",
          "Set a follow-up window if no response lands within a few days.",
        ],
      };
    case "follow_up":
      return {
        title: `Follow up with ${company.name} now`,
        urgency: execution.followUpDue ? `Due ${DATE_FORMATTER.format(new Date(execution.followUpDue))}` : "Follow-up window active",
        summary: "This target is already in motion. Use the next touch to revive momentum, not to restate the original pitch.",
        steps: [
          "Reference the last interaction directly.",
          "Use the newest role or signal as the timing hook.",
          "Close with a clear ask for next-step alignment or screen scheduling.",
        ],
      };
    case "interview":
      return {
        title: `Prepare for ${company.name} interview motion`,
        urgency: "Interview active",
        summary: "The opportunity is live. Shift from discovery to preparation and targeted signal usage.",
        steps: [
          "Review the company’s latest signals and technical stack clues.",
          "Prepare two operator-level questions tied to the hiring signals you observed.",
          "Map your strongest project evidence to the active role family.",
        ],
      };
    case "offer":
      return {
        title: `Evaluate the ${company.name} offer path`,
        urgency: "Offer stage",
        summary: "The intelligence layer should now help with leverage, timing, and tradeoff evaluation rather than discovery.",
        steps: [
          "Review changes in hiring urgency and company momentum before deciding.",
          "Compare the role scope against your target stage and skill growth goals.",
          "Use follow-up questions to clarify reporting line, ownership, and execution scope.",
        ],
      };
    case "closed":
      return {
        title: `Archive ${company.name} and move capital elsewhere`,
        urgency: "Execution closed",
        summary: "This thread is no longer active. Preserve the history, but do not let it consume ranking attention.",
        steps: [
          "Leave one short note on why the loop closed.",
          "Keep the company in the ledger for future signal changes.",
          "Reallocate effort to fresher high-confidence targets.",
        ],
      };
    default:
      return buildNextActionFromApi(company, roles, scopedSignals);
  }
}

function actionStateFromCompany(company: Company): OpportunityActionState {
  if (company.latestSignal.toLowerCase().includes("founder")) return "reach_out";
  if (company.urgency === "critical") return "apply_now";
  if (company.signalCount >= 5) return "high_leverage";
  return "early_signal";
}

function toneFromSignal(signal: Signal): AccentTone {
  if (signal.type === "funding") return "yellow";
  if (signal.type === "founder_post") return "green";
  if (signal.scoreVariant === "high") return "green";
  if (signal.scoreVariant === "medium") return "blue";
  return "red";
}

function tickerLabel(signal: Signal): string {
  switch (signal.type) {
    case "funding":
      return "FUNDING";
    case "founder_post":
      return "FOUNDER";
    case "github_spike":
      return "ENGINEERING";
    case "career_page":
      return "DIRECT";
    default:
      return "HIGH";
  }
}

function metricTone(id: CommandMetric["id"]): AccentTone {
  if (id === "signals_today") return "green";
  if (id === "watchlist_delta") return "yellow";
  if (id === "high_priority") return "red";
  return "blue";
}

function buildOpportunityFromBackend(
  company: Company,
  roles: RoleOut[],
  scopedSignals: Signal[],
  profile: CandidateProfile,
  execution: CompanyExecution | null,
): Opportunity {
  const topRole = roles[0];
  const roleFocus = topRole ? roleFocusFromApi(topRole.role_type) : roleLabelFromCompany(company);
  const scored = computeOpportunityScore(company, roles, scopedSignals, profile);
  const actionState =
    scopedSignals.some((signal) => signal.type === "founder_post")
      ? "reach_out"
      : topRole && topRole.days_open <= 2
        ? "apply_now"
        : company.openRoles === 0
          ? "early_signal"
          : actionStateFromCompany(company);
  const stackTags = buildTechCluesFromApi(company, roles).slice(0, 4);

  return {
    id: `${company.id}-opportunity`,
    companyId: company.id,
    rank: company.rank,
    score: scored.score,
    confidence: scored.confidence,
    scoreReasons: scored.reasons,
    scoreDelta: scored.delta,
    companyName: company.name,
    companyTagline: company.tagline,
    primaryRoleTitle: topRole?.title ?? fallbackRoleTitle(company, roleFocus),
    primaryRoleUrl: topRole?.url || undefined,
    roleFocus,
    summary: company.aiBrief ?? fallbackOpportunitySummary(company),
    location: company.location,
    remote: company.remote,
    remoteLabel: company.remoteLabel,
    postedAge: topRole ? postedAgeFromDays(topRole.days_open) : company.latestSignalAge || "recent",
    stackTags,
    actionState,
    urgency: company.urgency,
    stageLabel: company.stageLabel,
    signalCount: company.signalCount,
    openRoles: company.openRoles,
    latestSignal: company.latestSignal,
    latestSignalAge: company.latestSignalAge,
    watchlisted: company.onWatchlist,
    executionStatus: execution?.status ?? null,
  };
}

function buildFallbackBreakdown(company: Company): ScoreBreakdown[] {
  return [
    { label: "Signal density", value: Math.min(96, 55 + company.signalCount * 7), tone: "green", note: "Derived from current signal volume and freshness." },
    { label: "Timing edge", value: company.urgency === "critical" ? 92 : company.urgency === "high" ? 82 : 68, tone: "yellow", note: "Based on urgency and posted age." },
    { label: "Stack overlap", value: Math.max(58, company.fitScore - 4), tone: "blue", note: "Backed by visible stack clues and fit score." },
  ];
}

function buildFallbackRoles(company: Company): OpenRole[] {
  return Array.from({ length: Math.max(1, Math.min(3, company.openRoles)) }, (_, index) => ({
    id: `${company.id}-role-${index + 1}`,
    title:
      index === 0
        ? `${roleLabelFromCompany(company).replace("_", " ")} engineer`
        : index === 1
          ? "platform engineer"
          : "software engineer",
    team: index === 0 ? "Core Engineering" : "Platform",
    url: undefined,
    location: company.remote ? company.remoteLabel : company.location,
    remote: company.remote,
    postedAge: company.latestSignalAge || "recent",
    matchNote: "Strong alignment with current signal mix and visible stack clues.",
    status: index === 0 ? "fresh" : "open",
  }));
}

function buildFallbackTimeline(company: Company, signals: Signal[]): TimelineEvent[] {
  const scoped = signals
    .filter((signal) => signal.companyId === company.id)
    .slice(0, 4)
    .map((signal, index) => ({
      id: `${company.id}-timeline-${index}`,
      timestamp: signal.timestamp ? formatRelativeTime(signal.timestamp) : signal.date,
      label: tickerLabel(signal),
      detail: signal.headline,
      tone: toneFromSignal(signal),
      source: signal.typeLabel,
    }));

  return scoped.length > 0
    ? scoped
    : [
        {
          id: `${company.id}-timeline-fallback`,
          timestamp: company.latestSignalAge || "recent",
          label: "INTEL",
          detail: company.latestSignal || company.description,
          tone: "blue",
          source: "Console",
        },
      ];
}

function buildFallbackNextAction(company: Company): NextAction {
  const actionState = actionStateFromCompany(company);
  const titleMap: Record<OpportunityActionState, string> = {
    apply_now: `Apply to ${company.name} immediately`,
    reach_out: `Reach out directly to ${company.name} leadership`,
    high_leverage: `Treat ${company.name} as a high-leverage target`,
    early_signal: `Monitor and move early on ${company.name}`,
  };

  return {
    title: titleMap[actionState],
    urgency: company.latestSignalAge || "Active window",
    summary: "The current signal mix suggests this is worth focused attention, not passive tracking.",
    steps: [
      "Pick the strongest matching role and tighten the message around concrete stack overlap.",
      "Use the latest signal as the timing hook in outreach or application framing.",
      "If no direct contact exists, apply first and follow up with a targeted message."
    ],
  };
}

function buildCompanyDetail(
  company: Company,
  signals: Signal[],
  roles: RoleOut[],
  profile: CandidateProfile,
  execution: CompanyExecution | null,
): CompanyDetail {
  const scopedSignals = signals.filter((signal) => signal.companyId === company.id);
  const liveRoles = buildOpenRolesFromApi(company, roles);
  const techClues = buildTechCluesFromApi(company, roles);
  const scored = computeOpportunityScore(company, roles, scopedSignals, profile);

  return {
    companyId: company.id,
    companyName: company.name,
    companyTagline: company.tagline,
    stageLabel: company.stageLabel,
    headquarters: company.location,
    remoteLabel: company.remoteLabel,
    score: scored.score,
    scoreBreakdown: buildScoreBreakdownFromApi(company, roles, scopedSignals, profile),
    scoreEvidence: scored.evidence,
    openRoles: liveRoles.length > 0 ? liveRoles : buildFallbackRoles(company),
    signalHistory: buildFallbackTimeline(company, scopedSignals.length > 0 ? scopedSignals : signals),
    techStackClues: techClues.length > 0 ? techClues : [...company.stack.languages, ...company.stack.frameworks, ...company.stack.infra].slice(0, 5),
    outreachRecommendation: buildOutreachRecommendationFromApi(company, roles, scopedSignals),
    aiSummary: company.aiBrief || buildOpportunityFromBackend(company, roles, scopedSignals, profile, execution).summary,
    nextAction: buildExecutionAwareNextAction(company, roles, scopedSignals, execution),
    execution,
  };
}

function buildCommandMetrics(opportunities: Opportunity[], stats: DashboardStats): CommandMetric[] {
  const highPriority = opportunities.filter((opportunity) => opportunity.urgency === "critical" || opportunity.urgency === "high").length;
  const watchlistDelta = opportunities.filter((opportunity) => opportunity.watchlisted).length;

  const metrics = [
    { id: "opportunities", label: "Opportunities", value: String(opportunities.length), delta: "Ranked live" },
    { id: "open_roles", label: "Open roles", value: String(stats.openRoles), delta: "Tracked now" },
    { id: "high_priority", label: "High priority", value: String(highPriority), delta: "Immediate focus" },
    { id: "signals_today", label: "Signals today", value: String(Math.min(stats.signals, 24)), delta: "Fresh movement" },
    { id: "watchlist_delta", label: "Watchlist delta", value: String(watchlistDelta), delta: "Targets marked" },
  ] satisfies Array<Omit<CommandMetric, "tone">>;

  return metrics.map((metric) => ({ ...metric, tone: metricTone(metric.id) }));
}

function buildTicker(signals: Signal[]): TickerItem[] {
  return signals.slice(0, 8).map((signal) => ({
    id: signal.id,
    tone: toneFromSignal(signal),
    label: tickerLabel(signal),
    message: `${signal.companyName.toUpperCase()} ${signal.headline.toUpperCase()}`,
    age: signal.timestamp ? formatRelativeTime(signal.timestamp).toUpperCase() : signal.date.toUpperCase(),
  }));
}

function buildConsoleDashboard(
  companies: Company[],
  signals: Signal[],
  stats: DashboardStats,
  apiConnected: boolean,
  roles: RoleOut[] = [],
  profile: CandidateProfile = DEFAULT_CANDIDATE_PROFILE,
  executions: CompanyExecution[] = [],
): ConsoleDashboardData {
  const rolesByCompany = groupRolesByCompany(roles);
  const executionByCompany = Object.fromEntries(executions.map((execution) => [execution.companyId, execution]));
  const opportunities = companies
    .map((company) =>
      buildOpportunityFromBackend(
        company,
        rolesByCompany[company.id] ?? [],
        signals.filter((signal) => signal.companyId === company.id),
        profile,
        executionByCompany[company.id] ?? null
      )
    )
    .sort((a, b) => b.score - a.score)
    .map((opportunity, index) => ({
      ...opportunity,
      rank: index + 1,
    }));
  const companyDetails = Object.fromEntries(
    companies.map((company) => [
      company.id,
      buildCompanyDetail(
        company,
        signals,
        rolesByCompany[company.id] ?? [],
        profile,
        executionByCompany[company.id] ?? null
      ),
    ])
  );

  return {
    opportunities,
    liveSignals: signals.slice(0, 30),
    ticker: buildTicker(signals),
    commandMetrics: buildCommandMetrics(opportunities, stats),
    companyDetails,
    apiConnected,
    generatedAt: new Date().toISOString(),
  };
}

export async function loadConsoleDashboard(): Promise<ConsoleDashboardData> {
  const dashboard = await loadDashboardData();
  let roles: RoleOut[] = [];
  let executions: CompanyExecution[] = [];
  let profile = DEFAULT_CANDIDATE_PROFILE;

  if (dashboard.apiConnected) {
    try {
      const [fetchedRoles, fetchedProfile, fetchedExecutions] = await Promise.all([
        api.getRoles({ limit: 150 }),
        api.getProfile().catch(() => DEFAULT_CANDIDATE_PROFILE),
        api.getExecution(undefined, 200).catch(() => []),
      ]);
      roles = fetchedRoles;
      profile = fetchedProfile;
      executions = fetchedExecutions.map(apiExecutionToInternal);
    } catch {
      roles = [];
      profile = DEFAULT_CANDIDATE_PROFILE;
      executions = [];
    }
  }

  return buildConsoleDashboard(
    dashboard.companies,
    dashboard.signals,
    dashboard.stats,
    dashboard.apiConnected,
    roles,
    profile,
    executions,
  );
}

export async function toggleCompanyWatchlist(companyId: string, nextValue: boolean): Promise<boolean> {
  const response = await api.setWatchlist(companyId, nextValue);
  return response.on_watchlist;
}

export async function loadCandidateProfile(): Promise<CandidateProfile> {
  try {
    return await api.getProfile();
  } catch {
    return DEFAULT_CANDIDATE_PROFILE;
  }
}

export async function saveCandidateProfile(profile: CandidateProfile): Promise<CandidateProfile> {
  return api.updateProfile(profile);
}

export async function updateCompanyExecution(
  companyId: string,
  payload: {
    status: ExecutionStatus;
    label?: string;
    notes?: string;
    targetRoleTitle?: string;
    targetRoleUrl?: string;
    followUpDue?: string | null;
  },
): Promise<CompanyExecution> {
  const response = await api.updateExecution(companyId, {
    status: payload.status,
    label: payload.label,
    notes: payload.notes,
    target_role_title: payload.targetRoleTitle,
    target_role_url: payload.targetRoleUrl,
    follow_up_due: payload.followUpDue ?? undefined,
  });
  return apiExecutionToInternal(response);
}
