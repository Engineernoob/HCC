/**
 * HIRE INTEL API client
 * Connects the Next.js frontend to the FastAPI backend.
 * When the API is unreachable, the UI shows an explicit offline state.
 */

import type { CandidateProfile } from "./personalization";
import type { ExecutionStatus } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "https://hirectl-backend.onrender.com";

function isNgrokUrl(url: string): boolean {
  try {
    const host = new URL(url).hostname;
    return host.endsWith(".ngrok-free.dev") || host.endsWith(".ngrok-free.app");
  } catch {
    return false;
  }
}

function buildApiHeaders(extra?: HeadersInit): Headers {
  const headers = new Headers(extra);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  // Free ngrok serves a browser warning page unless this header is present.
  if (isNgrokUrl(API_BASE)) {
    headers.set("ngrok-skip-browser-warning", "true");
  }
  return headers;
}

// ── Types matching the FastAPI response models ─────────────────────

export interface CompanyOut {
  id: string;
  name: string;
  slug: string;
  tagline: string;
  stage: string;
  funding_amount: number | null;
  funding_label: string;
  remote_us: boolean;
  remote_label: string;
  fit_score: number;
  urgency_score: number;
  composite_score: number;
  urgency_label: "critical" | "high" | "medium" | "low";
  open_roles_count: number;
  signal_count: number;
  tech_stack: { languages?: string[]; frameworks?: string[]; infra?: string[] };
  chips: { label: string; variant: "gold" | "green" | "blue" | "default" }[];
  description: string;
  ai_brief: string | null;
  on_watchlist: boolean;
  last_signal_at: string | null;
}

export interface SignalOut {
  id: string;
  company_id: string;
  company_name: string;
  type: string;
  type_label: string;
  headline: string;
  detail: string;
  score: number;
  score_variant: "high" | "medium" | "low";
  signal_date: string;
  source_url: string;
}

export interface SignalStreamHandlers {
  onSignal: (signal: SignalOut) => void;
  onOpen?: () => void;
  onError?: () => void;
}

export interface RoleOut {
  id: string;
  company_id: string;
  company_name: string;
  title: string;
  url: string;
  role_type: string;
  seniority: string;
  is_remote: boolean;
  is_remote_us: boolean;
  location: string;
  fit_score: number;
  days_open: number;
  required_skills: string[];
}

export interface StatsOut {
  companies_total: number;
  companies_watchlist: number;
  open_roles: number;
  signals_total: number;
  signals_last_24h: number;
  outreach_due: number;
  avg_fit_score: number;
  last_ingest: string | null;
}

export interface ExecutionEventOut {
  id: string;
  company_id: string;
  status: ExecutionStatus;
  status_label: string;
  label: string;
  notes: string;
  target_role_title: string;
  target_role_url: string;
  follow_up_due: string | null;
  occurred_at: string;
}

export interface ExecutionOut {
  id: string;
  company_id: string;
  company_name: string;
  status: ExecutionStatus;
  status_label: string;
  notes: string;
  target_role_title: string;
  target_role_url: string;
  follow_up_due: string | null;
  last_event_at: string | null;
  updated_at: string | null;
  events: ExecutionEventOut[];
}

export interface CompanyFilters {
  stage?: string;
  remote_us?: boolean;
  min_score?: number;
  role_type?: string;
  watchlist_only?: boolean;
  search?: string;
  limit?: number;
  offset?: number;
}

export interface SignalFilters {
  company_id?: string;
  signal_type?: string;
  min_score?: number;
  hours?: number;
  limit?: number;
}

export interface ExecutionUpdate {
  status: ExecutionStatus;
  label?: string;
  notes?: string;
  target_role_title?: string;
  target_role_url?: string;
  follow_up_due?: string | null;
}

// ── HTTP helpers ───────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: buildApiHeaders(options?.headers),
    ...options,
  });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${res.statusText} — ${url}`);
  }
  return res.json();
}

function buildQuery(params: Record<string, unknown>): string {
  const qs = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join("&");
  return qs ? `?${qs}` : "";
}

// ── API methods ────────────────────────────────────────────────────

export const api = {
  // Health
  async health() {
    return apiFetch<{ status: string; db: string }>("/healthz");
  },

  // Stats
  async getStats(): Promise<StatsOut> {
    return apiFetch<StatsOut>("/api/stats");
  },

  // Companies
  async getCompanies(filters: CompanyFilters = {}): Promise<CompanyOut[]> {
    const q = buildQuery(filters as Record<string, unknown>);
    return apiFetch<CompanyOut[]>(`/api/companies${q}`);
  },

  async getCompany(id: string): Promise<CompanyOut> {
    return apiFetch<CompanyOut>(`/api/companies/${id}`);
  },

  async generateBrief(id: string, regenerate = false): Promise<{ brief: string; cached: boolean }> {
    return apiFetch<{ brief: string; cached: boolean }>(
      `/api/companies/${id}/brief`,
      {
        method: "POST",
        body: JSON.stringify({ regenerate }),
      }
    );
  },

  async generateOutreach(
    id: string,
    contact_role = "engineering lead",
    specific_angle = ""
  ): Promise<{ draft: string }> {
    return apiFetch<{ draft: string }>(`/api/companies/${id}/outreach`, {
      method: "POST",
      body: JSON.stringify({ contact_role, specific_angle }),
    });
  },

  async setWatchlist(id: string, on_watchlist: boolean) {
    return apiFetch<{ on_watchlist: boolean }>(
      `/api/companies/${id}/watchlist`,
      {
        method: "PUT",
        body: JSON.stringify({ on_watchlist }),
      }
    );
  },

  async getProfile(): Promise<CandidateProfile> {
    return apiFetch<CandidateProfile>("/api/profile");
  },

  async updateProfile(profile: CandidateProfile): Promise<CandidateProfile> {
    return apiFetch<CandidateProfile>("/api/profile", {
      method: "PUT",
      body: JSON.stringify(profile),
    });
  },

  async getExecution(company_id?: string, limit = 100): Promise<ExecutionOut[]> {
    const q = buildQuery({ company_id, limit });
    return apiFetch<ExecutionOut[]>(`/api/execution${q}`);
  },

  async updateExecution(id: string, payload: ExecutionUpdate): Promise<ExecutionOut> {
    return apiFetch<ExecutionOut>(`/api/execution/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },

  // Signals
  async getSignals(filters: SignalFilters = {}): Promise<SignalOut[]> {
    const q = buildQuery(filters as Record<string, unknown>);
    return apiFetch<SignalOut[]>(`/api/signals${q}`);
  },

  // Roles
  async getRoles(params: {
    company_id?: string;
    role_type?: string;
    remote_us?: boolean;
    min_fit?: number;
    limit?: number;
  } = {}): Promise<RoleOut[]> {
    const q = buildQuery(params as Record<string, unknown>);
    return apiFetch<RoleOut[]>(`/api/roles${q}`);
  },

  // Ingest trigger (dev/admin use)
  async triggerIngest(source?: string) {
    const q = source ? `?source=${source}` : "";
    return apiFetch<{ triggered_at: string; results: Record<string, unknown> }>(
      `/api/ingest/run${q}`,
      { method: "POST" }
    );
  },
};

export function subscribeToSignalStream({
  onSignal,
  onOpen,
  onError,
}: SignalStreamHandlers): () => void {
  const controller = new AbortController();
  let cancelled = false;

  void (async () => {
    try {
      const response = await fetch(`${API_BASE}/api/signals/stream`, {
        method: "GET",
        headers: buildApiHeaders({ Accept: "text/event-stream" }),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error(`SSE ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let currentEvent = "";
      let currentData: string[] = [];

      while (!cancelled) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n");
        buffer = parts.pop() ?? "";

        for (const rawLine of parts) {
          const line = rawLine.replace(/\r$/, "");

          if (line.startsWith("event:")) {
            currentEvent = line.slice(6).trim();
            continue;
          }

          if (line.startsWith("data:")) {
            currentData.push(line.slice(5).trim());
            continue;
          }

          if (line === "") {
            const data = currentData.join("\n");
            if (currentEvent === "ready") {
              onOpen?.();
            } else if (currentEvent === "signal" && data) {
              onSignal(JSON.parse(data) as SignalOut);
            }
            currentEvent = "";
            currentData = [];
          }
        }
      }
    } catch {
      if (!cancelled) {
        onError?.();
      }
    }
  })();

  return () => {
    cancelled = true;
    controller.abort();
  };
}

// ── Connectivity check ─────────────────────────────────────────────

export async function isApiReachable(): Promise<boolean> {
  try {
    await api.health();
    return true;
  } catch {
    return false;
  }
}
