import { Company, Signal } from "@/types";
import { RoleOut } from "./api";

export type CandidateRoleFocus =
  | "backend"
  | "fullstack"
  | "ai_ml"
  | "infra"
  | "platform"
  | "distributed"
  | "frontend"
  | "mobile"
  | "data";

export interface CandidateProfile {
  preferredRoles: CandidateRoleFocus[];
  preferredSkills: string[];
  preferredStages: string[];
  remoteOnly: boolean;
  preferredLocations: string[];
  targetCompanyIds?: string[];
  avoidCompanyIds?: string[];
}

export interface PersonalizationResult {
  fitBoost: number;
  stageBoost: number;
  remoteBoost: number;
  skillBoost: number;
  targetBoost: number;
  penalty: number;
  reasons: string[];
}

function normalize(value: string): string {
  return value.trim().toLowerCase();
}

function uniqueNormalized(values: string[]): string[] {
  return [...new Set(values.map(normalize).filter(Boolean))];
}

function inferRoleFamily(company: Company, roles: RoleOut[]): CandidateRoleFocus[] {
  const roleTypes = roles
    .map((r) => r.role_type)
    .filter(Boolean) as CandidateRoleFocus[];

  if (roleTypes.length > 0) {
    return [...new Set(roleTypes)];
  }

  const haystack = [
    company.tagline,
    company.description,
    ...company.stack.languages,
    ...company.stack.frameworks,
    ...company.stack.infra,
  ]
    .join(" ")
    .toLowerCase();

  const families: CandidateRoleFocus[] = [];
  if (haystack.includes("frontend") || haystack.includes("react")) families.push("frontend");
  if (haystack.includes("ai") || haystack.includes("ml") || haystack.includes("gpu")) families.push("ai_ml");
  if (haystack.includes("distributed") || haystack.includes("database") || haystack.includes("storage")) {
    families.push("distributed");
  }
  if (haystack.includes("infra") || haystack.includes("platform") || haystack.includes("kubernetes")) {
    families.push("infra");
  }
  if (families.length === 0) {
    families.push("backend");
  }

  return families;
}

function getSkillUniverse(company: Company, roles: RoleOut[]): string[] {
  const roleSkills = roles.flatMap((r) => r.required_skills ?? []);
  return uniqueNormalized([
    ...company.stack.languages,
    ...company.stack.frameworks,
    ...company.stack.infra,
    ...roleSkills,
  ]);
}

export function computePersonalization(
  company: Company,
  roles: RoleOut[],
  signals: Signal[],
  profile: CandidateProfile
): PersonalizationResult {
  const reasons: string[] = [];
  let fitBoost = 0;
  let stageBoost = 0;
  let remoteBoost = 0;
  let skillBoost = 0;
  let targetBoost = 0;
  let penalty = 0;

  const preferredRoles = profile.preferredRoles ?? [];
  const inferredFamilies = inferRoleFamily(company, roles);

  const roleMatches = inferredFamilies.filter((family) => preferredRoles.includes(family)).length;
  if (roleMatches > 0) {
    fitBoost += Math.min(18, roleMatches * 8);
    reasons.push(`Role alignment: ${inferredFamilies.join(", ")}`);
  }

  const preferredSkills = uniqueNormalized(profile.preferredSkills ?? []);
  const skillUniverse = getSkillUniverse(company, roles);
  const matchedSkills = preferredSkills.filter((skill) => skillUniverse.includes(skill));
  if (matchedSkills.length > 0) {
    skillBoost += Math.min(20, matchedSkills.length * 5);
    reasons.push(`Skill overlap: ${matchedSkills.slice(0, 4).join(", ")}`);
  }

  const preferredStages = uniqueNormalized(profile.preferredStages ?? []);
  if (preferredStages.includes(normalize(company.stageLabel))) {
    stageBoost += 10;
    reasons.push(`Preferred stage: ${company.stageLabel}`);
  }

  if (profile.remoteOnly) {
    if (company.remote) {
      remoteBoost += 12;
      reasons.push("Remote-compatible");
    } else {
      penalty += 20;
      reasons.push("Penalized: not remote");
    }
  } else if (
    profile.preferredLocations?.length &&
    profile.preferredLocations.map(normalize).includes(normalize(company.location))
  ) {
    remoteBoost += 6;
    reasons.push(`Location match: ${company.location}`);
  }

  if (profile.targetCompanyIds?.includes(company.id)) {
    targetBoost += 15;
    reasons.push("User target company");
  }

  if (profile.avoidCompanyIds?.includes(company.id)) {
    penalty += 30;
    reasons.push("Avoid list");
  }

  const founderSignal = signals.some((signal) => signal.type === "founder_post");
  if (founderSignal && preferredRoles.includes("backend")) {
    fitBoost += 4;
    reasons.push("Founder intent + backend bias");
  }

  return {
    fitBoost,
    stageBoost,
    remoteBoost,
    skillBoost,
    targetBoost,
    penalty,
    reasons,
  };
}
