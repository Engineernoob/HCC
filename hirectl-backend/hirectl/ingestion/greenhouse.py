"""
Greenhouse ATS scraper.

Greenhouse exposes public job boards at:
  https://boards.greenhouse.io/{company_token}/jobs

And a JSON API at:
  https://boards-api.greenhouse.io/v1/boards/{company_token}/jobs?content=true

We scrape a curated list of tracked companies. Each company's Greenhouse
token is stored in the watchlist. New companies discovered from other
sources are added automatically if they use Greenhouse.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select

from hirectl.config import settings
from hirectl.db.models import Company
from hirectl.db.session import get_session
from hirectl.ingestion.base import (
    BaseIngestionAdapter,
    CompanyResult,
    IngestResult,
    RoleResult,
    SignalResult,
    SignalType,
    extract_role_type,
    extract_seniority,
    extract_tech_stack,
    is_target_role,
    make_client,
)
from hirectl.tracked_companies import (
    tracked_discovery_candidates,
    tracked_greenhouse_companies,
)

logger = logging.getLogger(__name__)

GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
GREENHOUSE_JOB_URL = "https://job-boards.greenhouse.io/{token}/jobs/{job_id}"
GREENHOUSE_TOKEN_PATTERNS = [
    re.compile(r"https?://boards\.greenhouse\.io/([a-z0-9_-]+)", re.IGNORECASE),
    re.compile(r"https?://job-boards\.greenhouse\.io/([a-z0-9_-]+)", re.IGNORECASE),
    re.compile(r"https?://boards-api\.greenhouse\.io/v1/boards/([a-z0-9_-]+)", re.IGNORECASE),
    re.compile(r"[?&]for=([a-z0-9_-]+)", re.IGNORECASE),
]
CAREER_LINK_HINTS = ("career", "careers", "jobs", "join", "open-roles", "work-with-us", "workwithus")

# Curated list of validated public Greenhouse boards.
# Keep this list intentionally short. Most guessed board tokens 404,
# which wastes time and adds noise. Add entries only after confirming
# the public JSON API resolves successfully.
# Format: (company_name, greenhouse_token)
TRACKED_COMPANIES: list[tuple[str, str]] = tracked_greenhouse_companies()


class GreenhouseAdapter(BaseIngestionAdapter):
    """
    Fetches jobs from Greenhouse's public JSON API for tracked companies.

    Detects batch postings (multiple roles on same day) as urgency signals.
    Tracks when a role goes from open to closed (unfilled signal).
    """

    source_name = "greenhouse"
    batch_size = 8

    def __init__(self, extra_companies: list[tuple[str, str]] | None = None):
        super().__init__()
        self.batch_size = settings.job_board_batch_size
        self.companies = TRACKED_COMPANIES.copy()
        if extra_companies:
            self.companies.extend(extra_companies)

    async def fetch(self) -> IngestResult:
        result = IngestResult(source=self.source_name)
        company_targets = self._dedupe_company_tokens(
            self.companies
            + await self._load_stored_greenhouse_boards()
            + await self._discover_greenhouse_boards()
        )

        for i in range(0, len(company_targets), self.batch_size):
            batch = company_targets[i : i + self.batch_size]
            tasks = [
                self._fetch_company_safe(company_name, token, result)
                for company_name, token in batch
            ]
            await asyncio.gather(*tasks)

        # Detect batch postings — same company, multiple roles, same day
        self._detect_batch_signals(result)

        return result

    async def _load_stored_greenhouse_boards(self) -> list[tuple[str, str]]:
        async with get_session() as session:
            rows = (
                await session.execute(
                    select(Company.name, Company.career_page_url)
                    .where(Company.career_page_url.is_not(None))
                )
            ).all()

        stored: list[tuple[str, str]] = []
        for name, career_page_url in rows:
            if not name or not career_page_url:
                continue
            token = self._extract_greenhouse_token(career_page_url)
            if token:
                stored.append((name, token))
        return stored

    async def _discover_greenhouse_boards(self) -> list[tuple[str, str]]:
        candidates = await self._load_discovery_candidates()
        if not candidates:
            return []

        discovered: list[tuple[str, str]] = []
        async with make_client(timeout=15.0) as client:
            for i in range(0, len(candidates), self.batch_size):
                batch = candidates[i : i + self.batch_size]
                tokens = await asyncio.gather(
                    *(self._discover_company_token(client, candidate) for candidate in batch)
                )
                discovered.extend(token for token in tokens if token)

        if discovered:
            logger.info(f"Greenhouse discovery found {len(discovered)} candidate boards")
        return discovered

    async def _load_discovery_candidates(self) -> list[dict[str, str]]:
        candidates: list[dict[str, str]] = []
        tracked_names = {name.lower() for name, _ in self.companies}

        for candidate in tracked_discovery_candidates():
            if candidate["name"].lower() in tracked_names:
                continue
            if self._extract_greenhouse_token(candidate.get("career_page_url", "")):
                continue
            website_host = urlparse(candidate.get("website", "")).netloc.lower()
            if website_host.endswith("workatastartup.com"):
                continue
            candidates.append(candidate)

        async with get_session() as session:
            rows = (
                await session.execute(
                    select(Company.name, Company.website, Company.career_page_url)
                    .where((Company.website.is_not(None)) | (Company.career_page_url.is_not(None)))
                )
            ).all()

        for name, website, career_page_url in rows:
            if not name:
                continue
            if any(existing_name.lower() == name.lower() for existing_name, _ in self.companies):
                continue
            if self._extract_greenhouse_token(career_page_url or ""):
                continue
            website_host = urlparse(website or "").netloc.lower()
            if website_host.endswith("workatastartup.com"):
                continue
            candidates.append(
                {
                    "name": name,
                    "website": website or "",
                    "career_page_url": career_page_url or "",
                }
            )
        return candidates

    async def _discover_company_token(
        self,
        client: httpx.AsyncClient,
        candidate: dict[str, str],
    ) -> tuple[str, str] | None:
        company_name = candidate["name"]
        direct_token = self._extract_greenhouse_token(candidate.get("career_page_url", ""))
        if direct_token:
            return company_name, direct_token

        direct_token = self._extract_greenhouse_token(candidate.get("website", ""))
        if direct_token:
            return company_name, direct_token

        for url in self._candidate_urls(candidate):
            token = await self._discover_token_from_url(client, url)
            if token:
                return company_name, token

        return None

    def _candidate_urls(self, candidate: dict[str, str]) -> list[str]:
        urls: list[str] = []
        for raw in (candidate.get("career_page_url", ""), candidate.get("website", "")):
            if raw and raw.startswith(("http://", "https://")) and raw not in urls:
                urls.append(raw)
        return urls

    async def _discover_token_from_url(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> str | None:
        token = self._extract_greenhouse_token(url)
        if token:
            return token

        response = await self._safe_fetch_page(client, url)
        if response is None:
            return None

        token = self._extract_greenhouse_token(str(response.url))
        if token:
            return token

        token = self._extract_greenhouse_token(response.text)
        if token:
            return token

        soup = BeautifulSoup(response.text, "lxml")
        follow_links: list[str] = []
        for link in soup.select("a[href]"):
            href = link.get("href", "").strip()
            if not href:
                continue
            absolute = urljoin(str(response.url), href)
            token = self._extract_greenhouse_token(absolute)
            if token:
                return token

            anchor_text = link.get_text(" ", strip=True).lower()
            href_lower = absolute.lower()
            if any(hint in anchor_text for hint in CAREER_LINK_HINTS) or any(hint in href_lower for hint in CAREER_LINK_HINTS):
                if absolute not in follow_links:
                    follow_links.append(absolute)

        origin_host = urlparse(str(response.url)).netloc
        for follow_url in follow_links[:3]:
            follow_host = urlparse(follow_url).netloc
            if follow_host and origin_host and follow_host != origin_host and "greenhouse" not in follow_host:
                continue
            follow_response = await self._safe_fetch_page(client, follow_url)
            if follow_response is None:
                continue
            token = self._extract_greenhouse_token(str(follow_response.url))
            if token:
                return token
            token = self._extract_greenhouse_token(follow_response.text)
            if token:
                return token

        return None

    async def _safe_fetch_page(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> httpx.Response | None:
        try:
            response = await client.get(url)
            if response.status_code >= 400:
                return None
            return response
        except Exception:
            return None

    def _extract_greenhouse_token(self, text: str) -> str | None:
        for pattern in GREENHOUSE_TOKEN_PATTERNS:
            match = pattern.search(text or "")
            if match:
                return match.group(1).strip().lower()
        return None

    def _dedupe_company_tokens(
        self,
        company_tokens: list[tuple[str, str]],
    ) -> list[tuple[str, str]]:
        deduped: list[tuple[str, str]] = []
        seen_tokens: set[str] = set()
        for company_name, token in company_tokens:
            normalized = token.strip().lower()
            if not normalized or normalized in seen_tokens:
                continue
            seen_tokens.add(normalized)
            deduped.append((company_name, normalized))
        return deduped

    async def _fetch_company_safe(
        self,
        company_name: str,
        token: str,
        result: IngestResult,
    ) -> None:
        try:
            await self._fetch_company(company_name, token, result)
        except Exception as exc:
            logger.warning(f"Greenhouse failed for {company_name} ({token}): {exc}")

    async def _fetch_company(
        self,
        company_name: str,
        token: str,
        result: IngestResult,
    ) -> None:
        url = GREENHOUSE_API.format(token=token)
        resp = await self._get_board(url)
        if resp is None:
            return
        data = resp.json()
        board_url = f"https://boards.greenhouse.io/{token}"

        # Persist validated Greenhouse board URLs so future runs can load them
        # directly from the DB instead of recrawling the company site.
        result.companies.append(
            CompanyResult(
                name=company_name,
                career_page_url=board_url,
            )
        )

        jobs = data.get("jobs", [])
        target_jobs = [j for j in jobs if is_target_role(j.get("title", ""))]

        if not target_jobs:
            return

        today_jobs = []
        for job in target_jobs:
            role = self._parse_role(job, company_name, token)
            result.roles.append(role)

            # Individual signal per new role
            signal = self._make_signal(job, company_name, token, role)
            result.signals.append(signal)

            # Track for batch detection
            if self._is_recent(job.get("updated_at", "")):
                today_jobs.append(job)

        # Batch signal if 3+ roles posted same day
        if len(today_jobs) >= 3:
            result.signals.append(
                SignalResult(
                    company_name=company_name,
                    type=SignalType.ATS_GREENHOUSE,
                    headline=(
                        f"{len(today_jobs)} engineering roles posted simultaneously "
                        f"— {', '.join(j['title'] for j in today_jobs[:3])}"
                    ),
                    detail=(
                        "Same-day batch posting signals headcount budget approval, "
                        "not organic backfill. High-urgency window — move within 48h."
                    ),
                    source_url=f"https://boards.greenhouse.io/{token}",
                    signal_date=datetime.utcnow(),
                    score=88.0,
                )
            )

        logger.info(f"Greenhouse {company_name}: {len(target_jobs)} target roles")

    async def _get_board(self, url: str) -> httpx.Response | None:
        async with make_client(timeout=20.0) as client:
            response = await client.get(url, params={"content": "true"})
            if response.status_code == 404:
                logger.debug(f"Greenhouse board not found: {url}")
                return None
            if response.status_code in {401, 403}:
                logger.debug(f"Greenhouse board blocked: {url} ({response.status_code})")
                return None
            if response.status_code == 429:
                logger.warning(f"Greenhouse rate limited: {url}")
                return None
            response.raise_for_status()
            return response

    def _parse_role(
        self,
        job: dict[str, Any],
        company_name: str,
        token: str,
    ) -> RoleResult:
        title = job.get("title", "").strip()
        job_id = job.get("id", "")
        content = job.get("content", "")
        location = job.get("location", {}).get("name", "")

        is_remote = any(
            k in location.lower()
            for k in ("remote", "anywhere", "distributed")
        )

        return RoleResult(
            company_name=company_name,
            title=title,
            url=GREENHOUSE_JOB_URL.format(token=token, job_id=job_id),
            source=SignalType.ATS_GREENHOUSE,
            description_raw=content,
            role_type=extract_role_type(title),
            seniority=extract_seniority(title),
            is_remote=is_remote,
            is_remote_us=is_remote and (
                "us" in location.lower() or location == "" or "remote" in location.lower()
            ),
            location=location,
            external_id=str(job_id),
            tech_stack=extract_tech_stack(content),
            required_skills=extract_tech_stack(content).get("languages", []),
        )

    def _make_signal(
        self,
        job: dict[str, Any],
        company_name: str,
        token: str,
        role: RoleResult,
    ) -> SignalResult:
        updated_at_str = job.get("updated_at", "")
        try:
            from dateutil.parser import parse
            signal_date = parse(updated_at_str) if updated_at_str else datetime.utcnow()
        except Exception:
            signal_date = datetime.utcnow()

        return SignalResult(
            company_name=company_name,
            type=SignalType.ATS_GREENHOUSE,
            headline=f"{role.title} — {role.location or 'Remote'}",
            detail=f"Captured from public Greenhouse board · {role.role_type.value} role",
            source_url=role.url,
            signal_date=signal_date,
            score=65.0,
        )

    def _detect_batch_signals(self, result: IngestResult) -> None:
        """
        Post-process: if a company has 3+ new signals today, upgrade the
        urgency score of all its signals.
        """
        from collections import defaultdict
        today = datetime.utcnow().date()
        company_today: defaultdict[str, int] = defaultdict(int)

        for sig in result.signals:
            if sig.signal_date.date() == today:
                company_today[sig.company_name] += 1

        for sig in result.signals:
            if company_today[sig.company_name] >= 3:
                sig.score = min(sig.score * 1.3, 100.0)

    def _is_recent(self, date_str: str, days: int = 2) -> bool:
        """Return True if date_str is within the last N days."""
        if not date_str:
            return False
        try:
            from dateutil.parser import parse
            dt = parse(date_str)
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None)
            return (datetime.utcnow() - dt).days <= days
        except Exception:
            return False
