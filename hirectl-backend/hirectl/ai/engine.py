"""
AI brief generation and outreach drafting.

Supports three backends:
  1. Anthropic (claude-sonnet-4-6) — highest quality
  2. OpenAI (gpt-4o) — alternative
  3. Ollama (local, zero cost) — for development/offline use

All prompts are grounded in real signal data — no hallucination.
The LLM is a synthesizer, not an inventor.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from typing import Optional

from hirectl.config import settings

logger = logging.getLogger(__name__)
_provider_cooldowns: dict[str, float] = {}


@dataclass
class CompanyContext:
    """All the data we pass to the LLM for grounding."""
    name: str
    tagline: str = ""
    description: str = ""
    funding_stage: str = ""
    funding_amount: Optional[float] = None
    last_funding_date: Optional[datetime] = None
    tech_stack: dict = None
    open_roles: list[str] = None
    recent_signals: list[str] = None  # Human-readable signal summaries
    github_org: str = ""
    headcount: Optional[int] = None
    remote_us: bool = False
    fit_score: float = 0.0
    urgency_score: float = 0.0
    urgency_label: str = "medium"
    fit_notes: list[str] = None
    urgency_notes: list[str] = None

    def __post_init__(self):
        self.tech_stack = self.tech_stack or {}
        self.open_roles = self.open_roles or []
        self.recent_signals = self.recent_signals or []
        self.fit_notes = self.fit_notes or []
        self.urgency_notes = self.urgency_notes or []

    def to_context_string(self) -> str:
        """Render as a structured context block for the LLM prompt."""
        stack_str = ", ".join(
            self.tech_stack.get("languages", [])
            + self.tech_stack.get("frameworks", [])
            + self.tech_stack.get("infra", [])
        ) or "unknown"

        funding_str = ""
        if self.funding_amount:
            m = self.funding_amount / 1_000_000
            funding_str = f"${m:.0f}M {self.funding_stage}"
        elif self.funding_stage:
            funding_str = self.funding_stage

        lines = [
            f"Company: {self.name}",
            f"Description: {self.description or self.tagline}",
            f"Funding: {funding_str or 'unknown'}",
            f"Team size: {self.headcount or 'unknown'}",
            f"Remote US: {'yes' if self.remote_us else 'no'}",
            f"Tech stack: {stack_str}",
            f"Open roles: {', '.join(self.open_roles) or 'none listed'}",
            f"Fit score: {self.fit_score:.0f}/100",
            f"Urgency: {self.urgency_label} ({self.urgency_score:.0f}/100)",
            f"Recent signals:",
        ]
        for sig in self.recent_signals[:5]:
            lines.append(f"  - {sig}")
        if self.fit_notes:
            lines.append(f"Fit notes: {'; '.join(self.fit_notes)}")
        if self.urgency_notes:
            lines.append(f"Urgency notes: {'; '.join(self.urgency_notes)}")
        return "\n".join(lines)


@dataclass
class UserContext:
    """Your profile — used to personalize AI output."""
    name: str = "Taahirah"
    skills: list[str] = None
    domains: list[str] = None
    notable_work: str = ""
    github: str = ""
    bio: str = ""

    def __post_init__(self):
        self.skills = self.skills or [
            "Go", "Python", "Rust", "distributed systems",
            "backend engineering", "AI/ML infrastructure",
            "FastAPI", "Ollama", "RAG pipelines",
        ]
        self.domains = self.domains or [
            "distributed systems", "AI backends", "platform engineering",
        ]
        self.notable_work = self.notable_work or (
            "Built a local agentic coding assistant (Claude Code-style), "
            "a macOS invisible AI interview assistant in Go with CGo/Objective-C bridges, "
            "and a Rust terminal IDE. Strong systems programming background."
        )

    def to_context_string(self) -> str:
        return (
            f"Candidate: {self.name}\n"
            f"Skills: {', '.join(self.skills)}\n"
            f"Focus: {', '.join(self.domains)}\n"
            f"Notable work: {self.notable_work}\n"
            f"GitHub: {self.github or 'not specified'}"
        )


class AIEngine:
    """
    Generates intelligence briefs and outreach drafts.
    Grounded in real signal data — the LLM synthesizes, doesn't invent.
    """

    def __init__(self, user: Optional[UserContext] = None):
        self.user = user or UserContext()
        self._client = None

    async def generate_brief(self, company: CompanyContext) -> str:
        """
        Generate a 150–200 word intelligence brief explaining:
        - What this company actually does
        - Why now is specifically the right time to reach out
        - What kind of engineering they need
        - The specific angle that makes your outreach non-generic
        """
        system = (
            "You are a tactical job search intelligence system. "
            "You generate concise, grounded intelligence briefs for a software engineer "
            "evaluating companies to approach. "
            "You write in a direct, analytical style — no corporate language, no fluff. "
            "Every claim must be grounded in the provided signal data. "
            "Never invent facts. If you don't know something, say so briefly."
        )

        user_prompt = f"""Generate a 150-200 word intelligence brief for this company.

COMPANY DATA:
{company.to_context_string()}

CANDIDATE PROFILE:
{self.user.to_context_string()}

BRIEF FORMAT:
- First sentence: what they build and why it matters technically
- Second paragraph: why NOW is the right time (cite specific signals)
- Third paragraph: the specific outreach angle — what you know about their technical work that makes your message non-generic
- Do NOT use bullet points
- Do NOT use flattery ("exciting company", "love their work")
- Do NOT invent details not present in the data
- Tone: direct, analytical, like an intelligence analyst writing for another engineer"""

        return await self._complete(
            system,
            user_prompt,
            max_tokens=350,
            fallback=self._fallback_brief(company),
        )

    async def generate_outreach_draft(
        self,
        company: CompanyContext,
        contact_role: str = "engineering lead",
        specific_angle: str = "",
    ) -> str:
        """
        Generate a 100–150 word cold outreach message.

        Principles:
        - Reference something specific about their technical work
        - Make a clear, non-generic claim about fit
        - No flattery, no "I've always admired"
        - Direct engineer-to-engineer tone
        - Concrete ask (15 min call, not "let me know if you're interested")
        """
        system = (
            "You write cold outreach messages for software engineers targeting startups. "
            "Your messages are short (100–150 words), technically specific, and direct. "
            "They reference something concrete about the company's technical work — "
            "a specific repo, a recent blog post, a specific engineering challenge. "
            "No flattery. No vague claims. No corporate language. "
            "Always end with a specific, low-friction ask."
        )

        angle_context = f"\nSpecific angle to reference: {specific_angle}" if specific_angle else ""

        user_prompt = f"""Write a cold outreach message from {self.user.name} to a {contact_role} at {company.name}.

COMPANY DATA:
{company.to_context_string()}

CANDIDATE PROFILE:
{self.user.to_context_string()}
{angle_context}

REQUIREMENTS:
- 100-150 words maximum
- Reference something specific about their technical work (from the signals/stack data)
- State clearly why the candidate is relevant (from skills/domains)
- One specific, low-friction ask at the end (15 min call / Zoom)
- Subject line included at top: "Subject: [line]"
- No bullet points in the message body
- No "I hope this message finds you well" or similar
- Sign off as {self.user.name}"""

        return await self._complete(
            system,
            user_prompt,
            max_tokens=300,
            fallback=self._fallback_outreach(company, contact_role, specific_angle),
        )

    async def generate_fit_gap_analysis(
        self,
        company: CompanyContext,
        role_title: str,
        role_description: str,
    ) -> str:
        """
        Analyze fit vs gap for a specific role.
        Returns: what matches, what partially matches, what's missing,
        and how to frame the partial matches.
        """
        system = (
            "You perform honest fit/gap analysis for software engineers evaluating job roles. "
            "Be direct about gaps. Suggest honest framings for partial matches. "
            "Never suggest claiming skills you don't have."
        )

        user_prompt = f"""Analyze the fit and gaps between this candidate and role.

ROLE: {role_title} at {company.name}
ROLE DESCRIPTION (excerpt):
{role_description[:1000]}

CANDIDATE:
{self.user.to_context_string()}

OUTPUT FORMAT (plain text, no headers):
1. Strong matches (2-3 sentences)
2. Partial matches — honest framing suggestions (2-3 sentences)  
3. Gaps — be direct (1-2 sentences)
4. Overall recommendation: apply / apply with caveats / pass"""

        return await self._complete(
            system,
            user_prompt,
            max_tokens=400,
            fallback=self._fallback_fit_gap_analysis(company, role_title, role_description),
        )

    async def generate_daily_brief(
        self,
        top_companies: list[CompanyContext],
        new_signals_count: int,
        outreach_due: int,
    ) -> str:
        """Generate the daily morning digest summary."""
        system = (
            "You write a daily intelligence digest for a software engineer running "
            "a targeted job search. Tone: crisp, tactical, like a morning briefing. "
            "Focus on what requires action today."
        )

        companies_str = "\n\n".join(
            f"#{i+1} {c.name} (fit: {c.fit_score:.0f}, urgency: {c.urgency_label})\n"
            f"  Signals: {'; '.join(c.recent_signals[:2])}"
            for i, c in enumerate(top_companies[:5])
        )

        user_prompt = f"""Generate a daily intelligence digest.

DATE: {datetime.utcnow().strftime('%A, %B %d, %Y')}
NEW SIGNALS (24h): {new_signals_count}
OUTREACH DUE: {outreach_due}

TOP TARGETS:
{companies_str}

FORMAT:
- 2-3 sentence overall situation summary
- Top 3 action items for today (numbered, one line each)
- One company to prioritize and why (2 sentences)
- Total length: 120-150 words
- Tone: direct morning briefing, not a newsletter"""

        return await self._complete(
            system,
            user_prompt,
            max_tokens=300,
            fallback=self._fallback_daily_brief(top_companies, new_signals_count, outreach_due),
        )

    # ── LLM client ────────────────────────────────────────────────

    async def _complete(
        self,
        system: str,
        user_prompt: str,
        max_tokens: int = 400,
        fallback: str | None = None,
    ) -> str:
        """Route to the configured AI provider."""
        provider = settings.ai_provider
        cooldown_until = _provider_cooldowns.get(provider, 0.0)

        if cooldown_until > monotonic():
            logger.debug("AI provider %s is in cooldown; using deterministic fallback.", provider)
            return fallback or f"[AI unavailable — {provider} cooling down]"

        try:
            if provider == "anthropic":
                return await self._anthropic_complete(system, user_prompt, max_tokens)
            elif provider == "openai":
                return await self._openai_complete(system, user_prompt, max_tokens)
            else:
                return await self._ollama_complete(system, user_prompt, max_tokens)
        except Exception as e:
            _provider_cooldowns[provider] = monotonic() + settings.ai_failure_cooldown_seconds
            logger.warning(
                "AI completion unavailable (%s): %s. Using deterministic fallback.",
                provider,
                type(e).__name__,
            )
            return fallback or f"[AI unavailable — {type(e).__name__}]"

    async def _anthropic_complete(
        self, system: str, user_prompt: str, max_tokens: int
    ) -> str:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        msg = await client.messages.create(
            model=settings.ai_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return msg.content[0].text.strip()

    async def _openai_complete(
        self, system: str, user_prompt: str, max_tokens: int
    ) -> str:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        resp = await client.chat.completions.create(
            model="gpt-4o",
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
        )
        return resp.choices[0].message.content.strip()

    async def _ollama_complete(
        self, system: str, user_prompt: str, max_tokens: int
    ) -> str:
        """Call local Ollama — zero cost, works offline."""
        import httpx
        payload = {
            "model": settings.ollama_model,
            "prompt": f"{system}\n\n{user_prompt}",
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        timeout = httpx.Timeout(settings.ollama_timeout_seconds, connect=min(settings.ollama_timeout_seconds, 3.0))
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/generate",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()

    def _fallback_brief(self, company: CompanyContext) -> str:
        stack = ", ".join(
            company.tech_stack.get("languages", [])
            + company.tech_stack.get("frameworks", [])
            + company.tech_stack.get("infra", [])
        ) or "an incomplete visible stack"
        roles = ", ".join(company.open_roles[:3]) or "no confirmed role titles yet"
        signals = "; ".join(company.recent_signals[:3]) or "signal coverage is currently light"

        return (
            f"{company.name} matters because the current signal set points to active engineering demand rather than passive background noise. "
            f"The visible technical footprint is {stack}, and the strongest current role evidence is {roles}. "
            f"Right now the timing case is driven by {signals}. "
            f"The practical angle is to lead with concrete overlap in backend, distributed systems, or infrastructure work and reference the freshest signal directly instead of sending a generic startup note."
        )

    def _fallback_outreach(
        self,
        company: CompanyContext,
        contact_role: str,
        specific_angle: str,
    ) -> str:
        roles = ", ".join(company.open_roles[:2]) or "your current engineering hiring motion"
        signals = "; ".join(company.recent_signals[:2]) or "the latest hiring signal"
        angle = specific_angle or "backend, distributed systems, and infrastructure overlap"

        return (
            f"Subject: {company.name} — quick note\n\n"
            f"I’m reaching out because {signals.lower()} and {roles.lower()} make the timing concrete. "
            f"My background is strongest in {angle}, which looks aligned with the kind of engineering work {company.name} is scaling right now.\n\n"
            f"If it’s useful, I’d be happy to do a short 15 minute call and compare what you need on the {contact_role} side with the systems work I’ve been shipping recently.\n\n"
            f"{self.user.name}"
        )

    def _fallback_fit_gap_analysis(
        self,
        company: CompanyContext,
        role_title: str,
        role_description: str,
    ) -> str:
        skills = ", ".join(self.user.skills[:5])
        description = role_description.strip()[:240] or "role details are limited"
        return (
            f"1. Strong matches: The candidate is strongest in {skills}, which is directionally aligned with {role_title} at {company.name}.\n"
            f"2. Partial matches: Use concrete systems and backend work to bridge into adjacent requirements rather than claiming perfect overlap.\n"
            f"3. Gaps: The missing pieces need to be validated against the role description excerpt: {description}.\n"
            f"4. Overall recommendation: apply with caveats."
        )

    def _fallback_daily_brief(
        self,
        top_companies: list[CompanyContext],
        new_signals_count: int,
        outreach_due: int,
    ) -> str:
        lead = top_companies[0].name if top_companies else "the watchlist"
        return (
            f"Signal flow is active with {new_signals_count} new signals and {outreach_due} outreach items due. "
            f"Prioritize {lead} first, then work down the highest-urgency companies with confirmed hiring motion. "
            f"Today’s rule is simple: move on fresh roles and direct operator signals, and avoid spending time on weak or stale listings."
        )
