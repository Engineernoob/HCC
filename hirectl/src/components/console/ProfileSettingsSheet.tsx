"use client";

import { useEffect, useState } from "react";
import { CandidateProfile, CandidateRoleFocus } from "@/lib/personalization";

interface ProfileSettingsSheetProps {
  open: boolean;
  profile: CandidateProfile;
  saving: boolean;
  onClose: () => void;
  onSave: (profile: CandidateProfile) => void;
}

const ROLE_OPTIONS: CandidateRoleFocus[] = [
  "backend",
  "distributed",
  "infra",
  "platform",
  "ai_ml",
  "fullstack",
  "frontend",
  "data",
  "mobile",
];

const STAGE_OPTIONS = ["seed", "series a", "series b", "series c", "series d+", "public"];

function parseCsv(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export default function ProfileSettingsSheet({
  open,
  profile,
  saving,
  onClose,
  onSave,
}: ProfileSettingsSheetProps) {
  const [draft, setDraft] = useState<CandidateProfile>(profile);
  const [skillsInput, setSkillsInput] = useState(profile.preferredSkills.join(", "));
  const [locationsInput, setLocationsInput] = useState(profile.preferredLocations.join(", "));

  useEffect(() => {
    setDraft(profile);
    setSkillsInput(profile.preferredSkills.join(", "));
    setLocationsInput(profile.preferredLocations.join(", "));
  }, [profile]);

  function toggleRole(role: CandidateRoleFocus) {
    setDraft((current) => ({
      ...current,
      preferredRoles: current.preferredRoles.includes(role)
        ? current.preferredRoles.filter((item) => item !== role)
        : [...current.preferredRoles, role],
    }));
  }

  function toggleStage(stage: string) {
    setDraft((current) => ({
      ...current,
      preferredStages: current.preferredStages.includes(stage)
        ? current.preferredStages.filter((item) => item !== stage)
        : [...current.preferredStages, stage],
    }));
  }

  function submit() {
    onSave({
      ...draft,
      preferredSkills: parseCsv(skillsInput),
      preferredLocations: parseCsv(locationsInput),
    });
  }

  return (
    <div className={`fixed inset-0 z-50 transition ${open ? "pointer-events-auto" : "pointer-events-none"}`}>
      <div
        onClick={onClose}
        className={`absolute inset-0 bg-black/55 transition ${open ? "opacity-100" : "opacity-0"}`}
      />
      <aside
        className={`sheet-scroll absolute right-0 top-0 h-full w-[520px] overflow-y-auto border-l border-console-rule2 bg-ink-0 transition-transform duration-300 ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="sticky top-0 z-10 border-b border-console-rule2 bg-ink-0 px-5 py-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">
                Operator profile
              </div>
              <div className="mt-1 font-serif text-[30px] italic leading-none text-console-bright">
                Personalization settings
              </div>
              <div className="mt-2 font-mono text-[11px] uppercase tracking-[0.12em] text-console-secondary">
                Save preferences and rerank the queue.
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="border border-console-rule3 px-3 py-2 font-mono text-[10px] uppercase tracking-[0.14em] text-console-primary"
            >
              Close
            </button>
          </div>
        </div>

        <div className="space-y-6 px-5 py-5">
          <section className="border border-console-rule2 px-4 py-4">
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">
              Preferred role families
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {ROLE_OPTIONS.map((role) => {
                const active = draft.preferredRoles.includes(role);
                return (
                  <button
                    key={role}
                    type="button"
                    onClick={() => toggleRole(role)}
                    className={`border px-3 py-2 font-mono text-[10px] uppercase tracking-[0.14em] ${
                      active
                        ? "border-console-gold bg-[rgba(200,169,110,0.08)] text-console-bright"
                        : "border-console-rule3 text-console-dim"
                    }`}
                  >
                    {role.replace("_", " ")}
                  </button>
                );
              })}
            </div>
          </section>

          <section className="border border-console-rule2 px-4 py-4">
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">
              Preferred skills
            </div>
            <textarea
              value={skillsInput}
              onChange={(event) => setSkillsInput(event.target.value)}
              rows={4}
              className="mt-3 w-full border border-console-rule3 bg-ink-1 px-3 py-3 font-mono text-[11px] leading-6 text-console-primary outline-none"
              placeholder="python, postgres, docker, kubernetes"
            />
          </section>

          <section className="border border-console-rule2 px-4 py-4">
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">
              Preferred stages
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {STAGE_OPTIONS.map((stage) => {
                const active = draft.preferredStages.includes(stage);
                return (
                  <button
                    key={stage}
                    type="button"
                    onClick={() => toggleStage(stage)}
                    className={`border px-3 py-2 font-mono text-[10px] uppercase tracking-[0.14em] ${
                      active
                        ? "border-console-green bg-[rgba(102,208,135,0.08)] text-console-green"
                        : "border-console-rule3 text-console-dim"
                    }`}
                  >
                    {stage}
                  </button>
                );
              })}
            </div>
          </section>

          <section className="grid gap-4 md:grid-cols-2">
            <div className="border border-console-rule2 px-4 py-4">
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">
                Remote preference
              </div>
              <button
                type="button"
                onClick={() => setDraft((current) => ({ ...current, remoteOnly: !current.remoteOnly }))}
                className={`mt-3 border px-3 py-2 font-mono text-[10px] uppercase tracking-[0.14em] ${
                  draft.remoteOnly
                    ? "border-console-blue bg-[rgba(80,112,176,0.08)] text-console-blue"
                    : "border-console-rule3 text-console-dim"
                }`}
              >
                {draft.remoteOnly ? "Remote only" : "Mixed location"}
              </button>
            </div>
            <div className="border border-console-rule2 px-4 py-4">
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-console-dim">
                Preferred locations
              </div>
              <input
                value={locationsInput}
                onChange={(event) => setLocationsInput(event.target.value)}
                className="mt-3 w-full border border-console-rule3 bg-ink-1 px-3 py-2 font-mono text-[11px] text-console-primary outline-none"
                placeholder="remote, chicago, new york"
              />
            </div>
          </section>

          <section className="flex items-center justify-between border border-console-rule2 px-4 py-4">
            <div className="font-mono text-[11px] leading-6 text-console-secondary">
              Saving will persist the profile in the backend and rerank opportunities against these preferences.
            </div>
            <button
              type="button"
              onClick={submit}
              disabled={saving}
              className={`border px-4 py-3 font-mono text-[10px] uppercase tracking-[0.16em] ${
                saving
                  ? "border-console-rule3 text-console-dim"
                  : "border-console-gold text-console-gold hover:bg-[rgba(200,169,110,0.08)]"
              }`}
            >
              {saving ? "Saving..." : "Save profile"}
            </button>
          </section>
        </div>
      </aside>
    </div>
  );
}
