"""
GitHub organization activity watcher.

Monitors tracked company GitHub orgs for:
  1. Commit velocity spikes (2σ above 14-day baseline)
  2. New repository creation (especially infra/platform repos)
  3. Contributor count growth
  4. Language composition changes (signals actual vs stated stack)

All of these are pre-hiring signals that appear before ATS postings.
Requires a GitHub token for higher rate limits (5000 req/hr vs 60).
"""

import asyncio
import logging
from datetime import datetime, timedelta
from statistics import mean, stdev
from typing import Any, Optional

from hirectl.config import settings
from hirectl.ingestion.base import (
    BaseIngestionAdapter,
    CompanyResult,
    IngestResult,
    SignalResult,
    SignalType,
)
from hirectl.tracked_companies import tracked_github_orgs

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

# Companies to watch — (company_name, github_org_slug)
# Add new companies as you discover them
GITHUB_ORGS: list[tuple[str, str]] = tracked_github_orgs()

# Spike detection: commits in last 72h vs 14-day rolling average
SPIKE_WINDOW_DAYS = 3
BASELINE_WINDOW_DAYS = 14
SPIKE_THRESHOLD_SIGMA = 2.0  # Alert if commits > mean + 2σ


class GitHubWatcher(BaseIngestionAdapter):
    """
    Watches GitHub orgs for pre-hiring activity signals.

    Runs every hour. Computes rolling baselines and fires signals
    only when activity is statistically significant.
    """

    source_name = "github"

    def __init__(self, orgs: list[tuple[str, str]] | None = None):
        super().__init__()
        self.orgs = orgs or GITHUB_ORGS
        self._headers = self._make_headers()

    def _make_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if settings.github_available:
            headers["Authorization"] = f"Bearer {settings.github_token}"
        return headers

    async def fetch(self) -> IngestResult:
        result = IngestResult(source=self.source_name)

        if not settings.github_available:
            logger.warning(
                "No GitHub token configured — rate limited to 60 req/hr. "
                "Set GITHUB_TOKEN in .env for full access."
            )

        # Process orgs concurrently (but respect rate limits)
        tasks = [self._watch_org(name, org, result) for name, org in self.orgs]
        await asyncio.gather(*tasks, return_exceptions=True)

        return result

    async def _watch_org(
        self,
        company_name: str,
        org_slug: str,
        result: IngestResult,
    ) -> None:
        try:
            # Get org repos
            repos = await self._get_repos(org_slug)
            if not repos:
                return

            # Compute commit stats
            stats = await self._get_commit_stats(org_slug, repos)

            if not stats:
                return

            # Check for spike
            spike = self._detect_spike(stats)
            new_repos = self._find_new_repos(repos)
            lang_stack = await self._get_language_stack(org_slug, repos[:5])

            # Add company record with inferred stack
            result.companies.append(
                CompanyResult(
                    name=company_name,
                    github_org=org_slug,
                    tech_stack=lang_stack,
                )
            )

            # Emit signals
            if spike:
                result.signals.append(
                    SignalResult(
                        company_name=company_name,
                        type=SignalType.GITHUB_SPIKE,
                        headline=(
                            f"{spike['recent_commits']} commits in 72h — "
                            f"{spike['sigma']:.1f}σ above 14-day baseline"
                        ),
                        detail=(
                            f"Org commit velocity significantly elevated. "
                            f"Baseline: ~{spike['baseline']:.0f} commits/72h. "
                            f"Active repos: {', '.join(spike['active_repos'][:3])}."
                        ),
                        source_url=f"https://github.com/{org_slug}",
                        signal_date=datetime.utcnow(),
                        score=self._score_spike(spike),
                        github_commit_count=spike["recent_commits"],
                    )
                )

            for repo in new_repos:
                result.signals.append(
                    SignalResult(
                        company_name=company_name,
                        type=SignalType.GITHUB_SPIKE,
                        headline=f"New repository opened: {repo['name']}",
                        detail=(
                            f"New public repo '{repo['name']}' created — "
                            f"{'infra/platform work' if self._is_infra_repo(repo['name']) else 'new project'}. "
                            f"Description: {repo.get('description', 'none')[:80]}."
                        ),
                        source_url=repo["html_url"],
                        signal_date=datetime.utcnow(),
                        score=45.0,
                        github_repo_name=repo["name"],
                    )
                )

        except Exception as e:
            logger.warning(f"GitHub watcher failed for {company_name} ({org_slug}): {e}")

    async def _get_repos(self, org: str) -> list[dict[str, Any]]:
        """Get all public repos for an org, sorted by recent push."""
        resp = await self._get(
            f"{GITHUB_API}/orgs/{org}/repos",
            headers=self._headers,
            params={"sort": "pushed", "direction": "desc", "per_page": 30},
        )
        return resp.json() if isinstance(resp.json(), list) else []

    async def _get_commit_stats(
        self,
        org: str,
        repos: list[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        """
        Compute rolling commit stats across the org's top repos.
        Returns counts per day for the last BASELINE_WINDOW_DAYS days.
        """
        now = datetime.utcnow()
        baseline_start = now - timedelta(days=BASELINE_WINDOW_DAYS)
        spike_start = now - timedelta(days=SPIKE_WINDOW_DAYS)

        daily_counts: dict[str, int] = {}
        active_repos: list[str] = []

        # Check top 10 most recently pushed repos
        for repo in repos[:10]:
            repo_name = repo["name"]
            if repo.get("fork") or repo.get("archived"):
                continue

            try:
                resp = await self._get(
                    f"{GITHUB_API}/repos/{org}/{repo_name}/commits",
                    headers=self._headers,
                    params={
                        "since": baseline_start.isoformat() + "Z",
                        "per_page": 100,
                    },
                )
                commits = resp.json()
                if not isinstance(commits, list):
                    continue

                if commits:
                    active_repos.append(repo_name)

                for commit in commits:
                    date_str = (
                        commit.get("commit", {})
                        .get("author", {})
                        .get("date", "")[:10]
                    )
                    if date_str:
                        daily_counts[date_str] = daily_counts.get(date_str, 0) + 1

            except Exception:
                continue

        if not daily_counts:
            return None

        # Split into baseline vs recent window
        all_counts = [
            daily_counts.get(
                (baseline_start + timedelta(days=i)).strftime("%Y-%m-%d"), 0
            )
            for i in range(BASELINE_WINDOW_DAYS)
        ]
        recent_total = sum(
            daily_counts.get(
                (spike_start + timedelta(days=i)).strftime("%Y-%m-%d"), 0
            )
            for i in range(SPIKE_WINDOW_DAYS)
        )
        baseline_per_window = [
            sum(all_counts[i : i + SPIKE_WINDOW_DAYS])
            for i in range(0, BASELINE_WINDOW_DAYS - SPIKE_WINDOW_DAYS, SPIKE_WINDOW_DAYS)
        ]

        if not baseline_per_window:
            return None

        baseline_mean = mean(baseline_per_window)
        baseline_std = stdev(baseline_per_window) if len(baseline_per_window) > 1 else 1.0

        return {
            "recent_commits": recent_total,
            "baseline": baseline_mean,
            "std": baseline_std,
            "sigma": (recent_total - baseline_mean) / max(baseline_std, 0.1),
            "active_repos": active_repos,
        }

    def _detect_spike(self, stats: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Return stats if commit velocity is above threshold, else None."""
        if stats["sigma"] >= SPIKE_THRESHOLD_SIGMA and stats["recent_commits"] >= 10:
            return stats
        return None

    def _find_new_repos(self, repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Find repos created in the last 7 days."""
        cutoff = datetime.utcnow() - timedelta(days=7)
        new = []
        for repo in repos:
            created_str = repo.get("created_at", "")
            if not created_str:
                continue
            try:
                from dateutil.parser import parse
                created = parse(created_str).replace(tzinfo=None)
                if created >= cutoff and not repo.get("fork"):
                    new.append(repo)
            except Exception:
                continue
        return new

    async def _get_language_stack(
        self,
        org: str,
        repos: list[dict[str, Any]],
    ) -> dict[str, list[str]]:
        """Aggregate language usage across repos to infer actual tech stack."""
        lang_totals: dict[str, int] = {}

        for repo in repos:
            if repo.get("fork") or repo.get("archived"):
                continue
            try:
                resp = await self._get(
                    f"{GITHUB_API}/repos/{org}/{repo['name']}/languages",
                    headers=self._headers,
                )
                langs = resp.json()
                if isinstance(langs, dict):
                    for lang, bytes_count in langs.items():
                        lang_totals[lang] = lang_totals.get(lang, 0) + bytes_count
            except Exception:
                continue

        # Return top languages (>5% of total code)
        total = sum(lang_totals.values()) or 1
        top_langs = [
            lang.lower()
            for lang, count in sorted(lang_totals.items(), key=lambda x: -x[1])
            if count / total > 0.05
        ]

        return {"languages": top_langs[:6], "frameworks": [], "infra": []}

    def _score_spike(self, spike: dict[str, Any]) -> float:
        """Score a commit spike signal based on sigma and absolute count."""
        base = 40.0
        sigma_bonus = min(spike["sigma"] * 8, 30.0)
        volume_bonus = min(spike["recent_commits"] / 5, 20.0)
        return min(base + sigma_bonus + volume_bonus, 90.0)

    def _is_infra_repo(self, repo_name: str) -> bool:
        """Return True if repo name suggests infrastructure work."""
        keywords = [
            "infra", "platform", "deploy", "k8s", "helm", "terraform",
            "ops", "gateway", "proxy", "runtime", "scheduler", "agent",
        ]
        return any(k in repo_name.lower() for k in keywords)
