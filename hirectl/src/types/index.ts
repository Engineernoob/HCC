export type UrgencyLevel = "critical" | "high" | "medium" | "low";
export type SignalType =
  | "funding"
  | "founder_post"
  | "ats_greenhouse"
  | "ats_ashby"
  | "ats_lever"
  | "github_spike"
  | "career_page"
  | "blog_post"
  | "news"
  | "yc_jobs"
  | "wellfound";
export type RoleType =
  | "backend"
  | "fullstack"
  | "ai_ml"
  | "infra"
  | "platform"
  | "distributed"
  | "frontend"
  | "mobile"
  | "data"
  | "unknown";
export type FundingStage =
  | "seed"
  | "series_a"
  | "series_b"
  | "series_c"
  | "series_d_plus"
  | "unknown"
  | "public";
export interface TechStack {
  languages: string[];
  frameworks: string[];
  infra: string[];
}

export interface Company {
  id: string;
  slug?: string;
  rank: number;
  name: string;
  tagline: string;
  stage: FundingStage;
  stageLabel: string;
  funding?: string;
  location: string;
  remote: boolean;
  remoteLabel: string;
  fitScore: number;
  urgency: UrgencyLevel;
  openRoles: number;
  signalCount: number;
  stack: TechStack;
  chips: { label: string; variant: "gold" | "green" | "blue" | "default" }[];
  description: string;
  latestSignal: string;
  latestSignalAge: string;
  onWatchlist: boolean;
  aiBrief: string | null;
  lastSignalAt: string | null;
  compositeScore?: number;
  urgencyScore?: number;
}

export interface Signal {
  id: string;
  companyId: string;
  companyName: string;
  type: SignalType;
  typeLabel: string;
  headline: string;
  detail: string;
  date: string;
  timestamp: string | null;
  ageLabel: string;
  score: number;
  scoreVariant: "high" | "medium" | "low";
  sourceUrl: string;
  sourceLabel: string;
  operatorHint: string;
}

export interface DashboardStats {
  companies: number;
  openRoles: number;
  signals: number;
  outreachDue: number;
  avgFitScore: number;
}

export type SidebarSection =
  | "dashboard"
  | "signals"
  | "companies"
  | "watchlist"
  | "alerts"
  | "outreach";

export type QuickFilterKey =
  | "remote_us"
  | "backend"
  | "ai_ml"
  | "infrastructure"
  | "frontend";

export type OpportunityActionState =
  | "apply_now"
  | "reach_out"
  | "high_leverage"
  | "early_signal";

export type OpportunityConfidence = "high" | "medium" | "low";
export type ExecutionStatus =
  | "tracking"
  | "reached_out"
  | "applied"
  | "follow_up"
  | "interview"
  | "offer"
  | "closed";

export type AccentTone = "green" | "yellow" | "blue" | "red" | "neutral";

export interface TickerItem {
  id: string;
  tone: AccentTone;
  label: string;
  message: string;
  age: string;
}

export interface CommandMetric {
  id: string;
  label: string;
  value: string;
  delta?: string;
  tone: AccentTone;
}

export interface Opportunity {
  id: string;
  companyId: string;
  rank: number;
  score: number;
  confidence: OpportunityConfidence;
  scoreReasons: string[];
  scoreDelta: string;
  companyName: string;
  companyTagline: string;
  primaryRoleTitle: string;
  primaryRoleUrl?: string;
  roleFocus: RoleType;
  summary: string;
  location: string;
  remote: boolean;
  remoteLabel: string;
  postedAge: string;
  stackTags: string[];
  actionState: OpportunityActionState;
  urgency: UrgencyLevel;
  stageLabel: string;
  signalCount: number;
  openRoles: number;
  latestSignal: string;
  latestSignalAge: string;
  watchlisted: boolean;
  executionStatus: ExecutionStatus | null;
}

export interface ScoreBreakdown {
  label: string;
  value: number;
  tone: AccentTone;
  note: string;
}

export interface ScoreEvidence {
  id: string;
  label: string;
  sourceType: string;
  timestamp: string;
  contribution: number;
  tone: AccentTone;
  note: string;
}

export interface OpenRole {
  id: string;
  title: string;
  team: string;
  url?: string;
  location: string;
  remote: boolean;
  postedAge: string;
  matchNote: string;
  status: "open" | "fresh" | "competitive";
}

export interface TimelineEvent {
  id: string;
  timestamp: string;
  label: string;
  detail: string;
  tone: AccentTone;
  source: string;
}

export interface NextAction {
  title: string;
  urgency: string;
  summary: string;
  steps: string[];
}

export interface ExecutionEvent {
  id: string;
  companyId: string;
  status: ExecutionStatus;
  statusLabel: string;
  label: string;
  notes: string;
  targetRoleTitle: string;
  targetRoleUrl: string;
  followUpDue: string | null;
  occurredAt: string;
}

export interface CompanyExecution {
  id: string;
  companyId: string;
  companyName: string;
  status: ExecutionStatus;
  statusLabel: string;
  notes: string;
  targetRoleTitle: string;
  targetRoleUrl: string;
  followUpDue: string | null;
  lastEventAt: string | null;
  updatedAt: string | null;
  events: ExecutionEvent[];
}

export interface CompanyDetail {
  companyId: string;
  companyName: string;
  companyTagline: string;
  stageLabel: string;
  headquarters: string;
  remoteLabel: string;
  score: number;
  scoreBreakdown: ScoreBreakdown[];
  scoreEvidence: ScoreEvidence[];
  openRoles: OpenRole[];
  signalHistory: TimelineEvent[];
  techStackClues: string[];
  outreachRecommendation: string;
  aiSummary: string;
  nextAction: NextAction;
  execution: CompanyExecution | null;
}

export interface ConsoleDashboardData {
  opportunities: Opportunity[];
  liveSignals: Signal[];
  ticker: TickerItem[];
  commandMetrics: CommandMetric[];
  companyDetails: Record<string, CompanyDetail>;
  apiConnected: boolean;
  generatedAt: string;
}
