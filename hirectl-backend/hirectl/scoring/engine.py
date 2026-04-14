"""
Scoring engine for HIRE INTEL.

Computes three scores for each company:
  1. Fit score (0–100): how well the company's roles match YOUR profile
  2. Urgency score (0–100): how actively/urgently they are hiring RIGHT NOW
  3. Composite score: weighted blend used for the priority queue ranking

Design principles:
  - Scores are recomputed on every new signal (incremental, not batch)
  - All sub-scores are interpretable (logged for debugging)
  - Weights are configurable via .env
  - No black-box ML in MVP — pure heuristic scoring that you understand

Fit sub-scores:
  - Stack match (35%): overlap between your skills and role requirements
  - Domain match (25%): your declared domains vs role type
  - Seniority match (20%): your target level vs role level
  - Culture proxy (20%): eng blog, founder on GitHub, company size, remote

Urgency sub-scores:
  - Funding recency (30 pts max): decays over 60 days
  - Founder post (25 pts max): decays over 14 days
  - New role posting (20 pts max): decays over 30 days
  - Role aging (15 pts): >30 days unfilled = desperation signal
  - GitHub spike (10 pts max): decays over 7 days
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class UserProfile:
    """Your engineering profile — drives all fit scoring."""

    # Primary skills (high weight in stack match)
    primary_skills: list[str] = field(default_factory=lambda: [
        "go", "golang", "python", "rust",
        "distributed systems", "backend",
        "fastapi", "grpc",
    ])

    # Secondary skills (lower weight)
    secondary_skills: list[str] = field(default_factory=lambda: [
        "typescript", "javascript", "sql", "postgres",
        "redis", "docker", "kubernetes",
    ])

    # Domain preferences (ordered by preference)
    preferred_domains: list[str] = field(default_factory=lambda: [
        "distributed", "ai_ml", "infra", "backend", "platform", "fullstack"
    ])

    # Seniority target
    target_seniority: list[str] = field(default_factory=lambda: [
        "senior", "mid", "staff", "lead"
    ])

    # Company stage preferences
    preferred_stages: list[str] = field(default_factory=lambda: [
        "seed", "series_a", "series_b"
    ])

    # Location preferences
    require_remote: bool = True
    require_us: bool = True


@dataclass
class FitBreakdown:
    """Detailed breakdown of fit score components."""
    stack_match: float = 0.0         # 0–35
    domain_match: float = 0.0        # 0–25
    seniority_match: float = 0.0     # 0–20
    culture_proxy: float = 0.0       # 0–20
    total: float = 0.0

    matching_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    domain_label: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass
class UrgencyBreakdown:
    """Detailed breakdown of urgency score components."""
    funding_points: float = 0.0      # 0–30
    founder_post_points: float = 0.0  # 0–25
    new_role_points: float = 0.0     # 0–20
    role_aging_points: float = 0.0   # 0–15
    github_points: float = 0.0       # 0–10
    total: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class ScoreResult:
    """Full scoring result for a company."""
    company_name: str
    fit_score: float
    urgency_score: float
    composite_score: float
    fit_breakdown: FitBreakdown
    urgency_breakdown: UrgencyBreakdown
    urgency_label: str  # "critical" | "high" | "medium" | "low"


class ScoringEngine:
    """
    Computes fit and urgency scores for companies and roles.
    Stateless — can be called from any context.
    """

    # Score weights (configurable via settings)
    FIT_WEIGHT = 0.60
    URGENCY_WEIGHT = 0.40

    def __init__(self, profile: Optional[UserProfile] = None):
        self.profile = profile or UserProfile()

    # ── Company scoring ────────────────────────────────────────────

    def score_company(
        self,
        company_name: str,
        role_types: list[str],
        required_skills: list[str],
        funding_stage: str,
        last_funding_date: Optional[datetime],
        last_role_posted: Optional[datetime],
        oldest_open_role_days: int,
        has_founder_post: bool,
        founder_post_date: Optional[datetime],
        github_spike_date: Optional[datetime],
        github_spike_sigma: float,
        has_engineering_blog: bool,
        remote_us: bool,
        headcount: Optional[int],
        funding_amount_usd: Optional[float] = None,
    ) -> ScoreResult:
        fit = self._compute_fit(
            role_types=role_types,
            required_skills=required_skills,
            funding_stage=funding_stage,
            has_engineering_blog=has_engineering_blog,
            remote_us=remote_us,
            headcount=headcount,
        )
        urgency = self._compute_urgency(
            last_funding_date=last_funding_date,
            last_role_posted=last_role_posted,
            oldest_open_role_days=oldest_open_role_days,
            has_founder_post=has_founder_post,
            founder_post_date=founder_post_date,
            github_spike_date=github_spike_date,
            github_spike_sigma=github_spike_sigma,
            funding_amount_usd=funding_amount_usd,
        )

        composite = (
            self.FIT_WEIGHT * fit.total
            + self.URGENCY_WEIGHT * urgency.total
        )

        return ScoreResult(
            company_name=company_name,
            fit_score=round(fit.total, 1),
            urgency_score=round(urgency.total, 1),
            composite_score=round(composite, 1),
            fit_breakdown=fit,
            urgency_breakdown=urgency,
            urgency_label=self._urgency_label(urgency.total),
        )

    # ── Fit score ─────────────────────────────────────────────────

    def _compute_fit(
        self,
        role_types: list[str],
        required_skills: list[str],
        funding_stage: str,
        has_engineering_blog: bool,
        remote_us: bool,
        headcount: Optional[int],
    ) -> FitBreakdown:
        bd = FitBreakdown()

        # 1. Stack match (max 35 pts)
        req_lower = [s.lower() for s in required_skills]
        primary_hits = [s for s in self.profile.primary_skills if s in req_lower]
        secondary_hits = [s for s in self.profile.secondary_skills if s in req_lower]

        primary_score = min(len(primary_hits) * 8, 28)
        secondary_score = min(len(secondary_hits) * 2, 7)
        bd.stack_match = min(primary_score + secondary_score, 35)
        bd.matching_skills = primary_hits + secondary_hits

        # Penalize if NO matching skills
        if not primary_hits and not secondary_hits:
            bd.stack_match = 5.0
            bd.notes.append("No direct stack overlap detected")

        # 2. Domain match (max 25 pts)
        if role_types:
            domain_scores = {
                domain: (len(self.profile.preferred_domains) - i) * 4
                for i, domain in enumerate(self.profile.preferred_domains)
            }
            best_domain_score = max(
                (domain_scores.get(rt, 5) for rt in role_types),
                default=5,
            )
            bd.domain_match = min(best_domain_score, 25)
            bd.domain_label = role_types[0] if role_types else "unknown"
        else:
            bd.domain_match = 8.0

        # 3. Seniority match (max 20 pts)
        # Without explicit role seniority, assume mid-senior — give partial credit
        bd.seniority_match = 15.0  # Updated per-role in role scoring

        # 4. Culture proxy (max 20 pts)
        culture = 0.0
        if remote_us:
            culture += 8.0
            bd.notes.append("Remote US role")
        if has_engineering_blog:
            culture += 5.0
            bd.notes.append("Active engineering blog")
        if funding_stage in self.profile.preferred_stages:
            culture += 4.0
            bd.notes.append(f"Preferred stage: {funding_stage}")
        if headcount and headcount < 100:
            culture += 3.0
            bd.notes.append(f"Small team ({headcount})")
        bd.culture_proxy = min(culture, 20.0)

        bd.total = min(
            bd.stack_match + bd.domain_match + bd.seniority_match + bd.culture_proxy,
            100.0,
        )
        return bd

    def score_role_fit(
        self,
        role_title: str,
        role_type: str,
        required_skills: list[str],
        seniority: str,
        is_remote_us: bool,
    ) -> FitBreakdown:
        """Score an individual role against the user profile."""
        bd = self._compute_fit(
            role_types=[role_type],
            required_skills=required_skills,
            funding_stage="unknown",
            has_engineering_blog=False,
            remote_us=is_remote_us,
            headcount=None,
        )

        # Adjust seniority match based on actual role level
        if seniority in self.profile.target_seniority:
            bd.seniority_match = 20.0
        elif seniority in ("mid", "unknown"):
            bd.seniority_match = 14.0
        elif seniority == "junior":
            bd.seniority_match = 5.0
        else:
            bd.seniority_match = 10.0

        bd.total = min(
            bd.stack_match + bd.domain_match + bd.seniority_match + bd.culture_proxy,
            100.0,
        )
        return bd

    # ── Urgency score ──────────────────────────────────────────────

    def _compute_urgency(
        self,
        last_funding_date: Optional[datetime],
        last_role_posted: Optional[datetime],
        oldest_open_role_days: int,
        has_founder_post: bool,
        founder_post_date: Optional[datetime],
        github_spike_date: Optional[datetime],
        github_spike_sigma: float,
        funding_amount_usd: Optional[float] = None,
    ) -> UrgencyBreakdown:
        bd = UrgencyBreakdown()
        now = datetime.utcnow()

        # 1. Funding recency (max 30 pts, decays over 60 days)
        if last_funding_date:
            days_since = (now - last_funding_date).days
            if days_since <= 0:
                days_since = 0
            decay = max(0.0, 1.0 - (days_since / 60.0))
            base = 30.0

            # Bonus for larger rounds
            if funding_amount_usd:
                if funding_amount_usd >= 50_000_000:
                    base = 30.0
                elif funding_amount_usd >= 20_000_000:
                    base = 26.0
                else:
                    base = 20.0

            bd.funding_points = base * decay
            if bd.funding_points > 0:
                bd.notes.append(
                    f"Funded {days_since}d ago "
                    f"({'${:,.0f}M'.format(funding_amount_usd/1e6) if funding_amount_usd else 'amount unknown'})"
                )

        # 2. Founder post (max 25 pts, decays over 14 days)
        if has_founder_post and founder_post_date:
            days_since = (now - founder_post_date).days
            decay = max(0.0, 1.0 - (days_since / 14.0))
            bd.founder_post_points = 25.0 * decay
            if bd.founder_post_points > 1:
                bd.notes.append(f"Founder hiring post {days_since}d ago")
        elif has_founder_post:
            bd.founder_post_points = 15.0
            bd.notes.append("Founder hiring post detected")

        # 3. New role posting (max 20 pts, decays over 30 days)
        if last_role_posted:
            days_since = (now - last_role_posted).days
            decay = max(0.0, 1.0 - (days_since / 30.0))
            bd.new_role_points = 20.0 * decay
            if bd.new_role_points > 1:
                bd.notes.append(f"Role posted {days_since}d ago")

        # 4. Role aging — desperation signal (max 15 pts)
        # 30–60 days unfilled = high urgency; >60 = stale
        if 20 <= oldest_open_role_days <= 60:
            bd.role_aging_points = min(
                15.0 * ((oldest_open_role_days - 20) / 40.0), 15.0
            )
            bd.notes.append(f"Role open {oldest_open_role_days}d — unfilled urgency")
        elif oldest_open_role_days > 60:
            bd.role_aging_points = 5.0  # Stale, but still some signal
            bd.notes.append(f"Role open {oldest_open_role_days}d — possibly stale")

        # 5. GitHub spike (max 10 pts, decays over 7 days)
        if github_spike_date and github_spike_sigma >= 2.0:
            days_since = (now - github_spike_date).days
            decay = max(0.0, 1.0 - (days_since / 7.0))
            sigma_bonus = min((github_spike_sigma - 2.0) * 2, 5.0)
            bd.github_points = (5.0 + sigma_bonus) * decay
            if bd.github_points > 0:
                bd.notes.append(f"GitHub spike {github_spike_sigma:.1f}σ, {days_since}d ago")

        bd.total = min(
            bd.funding_points
            + bd.founder_post_points
            + bd.new_role_points
            + bd.role_aging_points
            + bd.github_points,
            100.0,
        )
        return bd

    # ── Utilities ──────────────────────────────────────────────────

    def _urgency_label(self, urgency_score: float) -> str:
        if urgency_score >= 75:
            return "critical"
        if urgency_score >= 50:
            return "high"
        if urgency_score >= 25:
            return "medium"
        return "low"

    def compute_signal_score(
        self,
        signal_type: str,
        signal_date: datetime,
        extra_data: Optional[dict] = None,
    ) -> float:
        """
        Compute the score for a raw signal event.
        Used during ingestion before company-level scoring runs.
        """
        now = datetime.utcnow()
        days_old = (now - signal_date).days
        extra = extra_data or {}

        if signal_type == "funding":
            amount = extra.get("amount_usd", 0)
            base = 70.0 if amount >= 20_000_000 else 50.0
            decay = max(0.0, 1.0 - days_old / 60.0)
            return base * decay

        if signal_type == "founder_post":
            decay = max(0.0, 1.0 - days_old / 14.0)
            return 80.0 * decay

        if signal_type in ("ats_greenhouse", "ats_lever", "ats_ashby"):
            decay = max(0.0, 1.0 - days_old / 30.0)
            base = 65.0
            if extra.get("batch_posting"):
                base = 85.0
            return base * decay

        if signal_type == "career_page":
            decay = max(0.0, 1.0 - days_old / 14.0)
            return 60.0 * decay  # Higher than ATS because direct listing

        if signal_type == "github_spike":
            sigma = extra.get("sigma", 2.0)
            decay = max(0.0, 1.0 - days_old / 7.0)
            return min(40.0 + sigma * 6, 75.0) * decay

        if signal_type == "blog_post":
            decay = max(0.0, 1.0 - days_old / 30.0)
            return 35.0 * decay

        return 30.0  # Default

    def explain(self, result: ScoreResult) -> str:
        """Return a human-readable explanation of the score breakdown."""
        lines = [
            f"{'─' * 50}",
            f"  {result.company_name}",
            f"  Composite: {result.composite_score:.1f}  |  "
            f"Fit: {result.fit_score:.1f}  |  "
            f"Urgency: {result.urgency_score:.1f} [{result.urgency_label.upper()}]",
            f"{'─' * 50}",
            "  Fit breakdown:",
            f"    Stack match:      {result.fit_breakdown.stack_match:.1f}/35",
            f"    Domain match:     {result.fit_breakdown.domain_match:.1f}/25",
            f"    Seniority match:  {result.fit_breakdown.seniority_match:.1f}/20",
            f"    Culture proxy:    {result.fit_breakdown.culture_proxy:.1f}/20",
        ]
        if result.fit_breakdown.matching_skills:
            lines.append(f"    Matching skills: {', '.join(result.fit_breakdown.matching_skills)}")
        lines += [
            "  Urgency breakdown:",
            f"    Funding:          {result.urgency_breakdown.funding_points:.1f}/30",
            f"    Founder post:     {result.urgency_breakdown.founder_post_points:.1f}/25",
            f"    New role:         {result.urgency_breakdown.new_role_points:.1f}/20",
            f"    Role aging:       {result.urgency_breakdown.role_aging_points:.1f}/15",
            f"    GitHub spike:     {result.urgency_breakdown.github_points:.1f}/10",
        ]
        if result.urgency_breakdown.notes:
            lines.append(f"    Notes: {'; '.join(result.urgency_breakdown.notes)}")
        lines.append(f"{'─' * 50}")
        return "\n".join(lines)
