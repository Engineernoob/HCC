import { Company, ScoreEvidence, Signal } from "@/types";
import { RoleOut } from "./api";
import { CandidateProfile, computePersonalization } from "./personalization";

export interface OpportunityScoreResult {
  score: number;
  confidence: "low" | "medium" | "high";
  delta: string;
  reasons: string[];
  evidence: ScoreEvidence[];
  breakdown: {
    signalStrength: number;
    hiringVelocity: number;
    baseFit: number;
    urgency: number;
    accessibility: number;
    personalization: number;
  };
}

function ageLabelFromTimestamp(timestamp: string | null): string {
  if (!timestamp) {
    return "current";
  }
  const hours = Math.max(0, (Date.now() - new Date(timestamp).getTime()) / 3_600_000);
  if (hours < 1) {
    return "now";
  }
  if (hours < 24) {
    return `${Math.round(hours)}h ago`;
  }
  return `${Math.round(hours / 24)}d ago`;
}

function roleAgeLabel(daysOpen: number): string {
  if (daysOpen <= 0) return "today";
  if (daysOpen === 1) return "1d ago";
  return `${daysOpen}d ago`;
}

function signalTypeWeight(signal: Signal, ageHours: number): number {
  const recencyMultiplier =
    ageHours < 6 ? 1.45 :
    ageHours < 24 ? 1.2 :
    ageHours < 72 ? 1.0 :
    0.65;

  const typeWeight =
    signal.type === "founder_post" ? 30 :
    signal.type === "career_page" ? 24 :
    signal.type === "funding" ? 18 :
    signal.type === "github_spike" ? 10 :
    6;

  return typeWeight * recencyMultiplier;
}

function signalEvidenceLabel(company: Company, signal: Signal): string {
  switch (signal.type) {
    case "founder_post":
      return "Founder hiring signal";
    case "funding":
      return company.stageLabel !== "Unverified"
        ? `${company.stageLabel} funding announcement`
        : "Funding momentum";
    case "github_spike":
      return "GitHub activity spike";
    case "career_page":
      return "Fresh hiring signal";
    default:
      return signal.typeLabel;
  }
}

export function computeOpportunityScore(
  company: Company,
  roles: RoleOut[],
  signals: Signal[],
  profile?: CandidateProfile
): OpportunityScoreResult {
  const now = Date.now();
  const evidence: ScoreEvidence[] = [];

  for (const signal of signals) {
    const ageHours = signal.timestamp
      ? (now - new Date(signal.timestamp).getTime()) / (1000 * 60 * 60)
      : 72;
    const rawContribution = signalTypeWeight(signal, ageHours);
    const weightedContribution = Math.max(1, Math.round(rawContribution * 0.28));
    evidence.push({
      id: `signal-${signal.id}`,
      label: signalEvidenceLabel(company, signal),
      sourceType: signal.typeLabel,
      timestamp: ageLabelFromTimestamp(signal.timestamp),
      contribution: weightedContribution,
      tone:
        signal.type === "founder_post" ? "green" :
        signal.type === "funding" ? "yellow" :
        signal.type === "github_spike" ? "blue" :
        "green",
      note: signal.headline,
    });
  }

  const signalStrength = Math.min(
    100,
    signals.reduce((acc, signal) => {
      const ageHours = signal.timestamp
        ? (now - new Date(signal.timestamp).getTime()) / (1000 * 60 * 60)
        : 72;
      return acc + signalTypeWeight(signal, ageHours);
    }, 0)
  );

  const freshRoles = roles.filter((role) => role.days_open <= 2);
  const hiringVelocity = Math.min(
    100,
    roles.reduce((acc, role) => {
      if (role.days_open <= 2) return acc + 22;
      if (role.days_open <= 7) return acc + 14;
      if (role.days_open <= 14) return acc + 7;
      return acc + 3;
    }, company.openRoles * 4)
  );

  if (freshRoles.length > 0) {
    evidence.push({
      id: `roles-fresh-${company.id}`,
      label:
        freshRoles.length === 1
          ? `Fresh ${freshRoles[0].role_type.replace("_", " ")} role`
          : `${freshRoles.length} roles opened in 48 hours`,
      sourceType: "Role openings",
      timestamp: roleAgeLabel(Math.min(...freshRoles.map((role) => role.days_open))),
      contribution: Math.min(
        24,
        Math.round(
          freshRoles.reduce((acc, role) => acc + (role.days_open <= 2 ? 22 : 0), 0) * 0.24
        )
      ),
      tone: "yellow",
      note: freshRoles
        .slice(0, 2)
        .map((role) => role.title)
        .join(" • "),
    });
  } else if (roles.length > 0) {
    evidence.push({
      id: `roles-active-${company.id}`,
      label: `${roles.length} active hiring roles`,
      sourceType: "Role openings",
      timestamp: roleAgeLabel(Math.min(...roles.map((role) => role.days_open))),
      contribution: Math.max(4, Math.round(hiringVelocity * 0.18)),
      tone: "yellow",
      note: roles
        .slice(0, 2)
        .map((role) => role.title)
        .join(" • "),
    });
  }

  const baseFit = Math.min(100, Math.max(0, Math.round(company.fitScore)));

  const urgency =
    company.urgency === "critical" ? 100 :
    company.urgency === "high" ? 82 :
    company.urgency === "medium" ? 64 :
    42;

  const accessibility =
    signals.some((signal) => signal.type === "founder_post") ? 92 :
    roles.length > 0 ? 72 :
    38;

  const personalization = profile
    ? computePersonalization(company, roles, signals, profile)
    : {
        fitBoost: 0,
        stageBoost: 0,
        remoteBoost: 0,
        skillBoost: 0,
        targetBoost: 0,
        penalty: 0,
        reasons: [],
      };

  const personalizationTotal =
    personalization.fitBoost +
    personalization.stageBoost +
    personalization.remoteBoost +
    personalization.skillBoost +
    personalization.targetBoost -
    personalization.penalty;

  if (company.remote && profile?.remoteOnly) {
    evidence.push({
      id: `remote-${company.id}`,
      label: "Remote U.S. fit confirmed",
      sourceType: "Profile preference",
      timestamp: "current",
      contribution: personalization.remoteBoost || 12,
      tone: "blue",
      note: company.remoteLabel,
    });
  } else if (profile?.remoteOnly && !company.remote) {
    evidence.push({
      id: `remote-penalty-${company.id}`,
      label: "Remote mismatch penalty",
      sourceType: "Profile preference",
      timestamp: "current",
      contribution: -(personalization.penalty || 12),
      tone: "red",
      note: `${company.name} is not confirmed remote-compatible.`,
    });
  }

  const skillOverlapReason = personalization.reasons.find((reason) => reason.startsWith("Skill overlap:"));
  if (skillOverlapReason) {
    evidence.push({
      id: `skills-${company.id}`,
      label: "Strong stack overlap",
      sourceType: "Fit model",
      timestamp: "current",
      contribution: Math.max(6, personalization.skillBoost || Math.round(baseFit * 0.1)),
      tone: "blue",
      note: skillOverlapReason.replace("Skill overlap:", "").trim(),
    });
  } else if (baseFit >= 75) {
    evidence.push({
      id: `fit-${company.id}`,
      label: "Strong stack fit",
      sourceType: "Fit model",
      timestamp: "current",
      contribution: Math.max(6, Math.round(baseFit * 0.1)),
      tone: "blue",
      note: "Visible stack and role-family overlap support strong fit.",
    });
  }

  const preferredStageReason = personalization.reasons.find((reason) => reason.startsWith("Preferred stage:"));
  if (preferredStageReason) {
    evidence.push({
      id: `stage-${company.id}`,
      label: `Preferred ${company.stageLabel} stage`,
      sourceType: "Profile preference",
      timestamp: "current",
      contribution: personalization.stageBoost || 10,
      tone: "yellow",
      note: preferredStageReason,
    });
  }

  const weighted =
    signalStrength * 0.28 +
    hiringVelocity * 0.24 +
    baseFit * 0.18 +
    urgency * 0.15 +
    accessibility * 0.10 +
    Math.max(-25, Math.min(25, personalizationTotal)) * 1.0;

  const score = Math.max(1, Math.min(99, Math.round(weighted)));

  const confidence: "low" | "medium" | "high" =
    signals.length >= 4 && roles.length >= 2
      ? "high"
      : signals.length >= 2 || roles.length >= 1
        ? "medium"
        : "low";

  const delta =
    score >= 85 ? "+14" :
    score >= 75 ? "+9" :
    score >= 65 ? "+5" :
    "+2";

  const reasons = [
    ...evidence
      .filter((item) => item.contribution > 0)
      .sort((a, b) => b.contribution - a.contribution)
      .slice(0, 4)
      .map((item) => item.label),
  ];

  return {
    score,
    confidence,
    delta,
    reasons,
    evidence: evidence
      .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
      .slice(0, 6),
    breakdown: {
      signalStrength,
      hiringVelocity,
      baseFit,
      urgency,
      accessibility,
      personalization: Math.max(0, Math.min(100, 50 + personalizationTotal)),
    },
  };
}
