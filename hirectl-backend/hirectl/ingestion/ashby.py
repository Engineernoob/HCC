"""
Ashby ATS adapter.

Ashby exposes a public job-board API at:
  https://api.ashbyhq.com/posting-api/job-board/{org_slug}
"""

import asyncio
import logging
import re
from collections import defaultdict
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
    tracked_ashby_companies,
    tracked_discovery_candidates,
)

logger = logging.getLogger(__name__)

ASHBY_API = "https://api.ashbyhq.com/posting-api/job-board/{slug}"
ASHBY_JOB_URL = "https://jobs.ashbyhq.com/{slug}/{job_id}"
ASHBY_TOKEN_PATTERNS = [
    re.compile(r"https?://jobs\.ashbyhq\.com/([^\"'/?#\s]+)", re.IGNORECASE),
    re.compile(r"https?://api\.ashbyhq\.com/posting-api/job-board/([^\"'/?#\s]+)", re.IGNORECASE),
]
CAREER_LINK_HINTS = ("career", "careers", "jobs", "join", "open-roles", "work-with-us", "workwithus")

TRACKED_COMPANIES: list[tuple[str, str]] = tracked_ashby_companies()


class AshbyAdapter(BaseIngestionAdapter):
    """Fetch engineering roles from Ashby's public job-board API."""

    source_name = "ashby"
    batch_size = 8

    def __init__(self, extra_companies: list[tuple[str, str]] | None = None):
        super().__init__()
        self.batch_size = settings.job_board_batch_size
        self.companies = TRACKED_COMPANIES.copy()
        if extra_companies:
            self.companies.extend(extra_companies)

    async def fetch(self) -> IngestResult:
        result = IngestResult(source=self.source_name)
        company_targets = self._dedupe_company_slugs(
            self.companies
            + await self._load_stored_ashby_boards()
            + await self._discover_ashby_boards()
        )

        for i in range(0, len(company_targets), self.batch_size):
            batch = company_targets[i : i + self.batch_size]
            tasks = [
                self._fetch_company_safe(company_name, slug, result)
                for company_name, slug in batch
            ]
            await asyncio.gather(*tasks)

        self._detect_batch_signals(result)
        return result

    async def _load_stored_ashby_boards(self) -> list[tuple[str, str]]:
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
            slug = self._extract_ashby_slug(career_page_url)
            if slug:
                stored.append((name, slug))
        return stored

    async def _discover_ashby_boards(self) -> list[tuple[str, str]]:
        candidates = await self._load_discovery_candidates()
        if not candidates:
            return []

        discovered: list[tuple[str, str]] = []
        async with make_client(timeout=15.0) as client:
            for i in range(0, len(candidates), self.batch_size):
                batch = candidates[i : i + self.batch_size]
                slugs = await asyncio.gather(
                    *(self._discover_company_slug(client, candidate) for candidate in batch)
                )
                discovered.extend(slug for slug in slugs if slug)

        if discovered:
            logger.info(f"Ashby discovery found {len(discovered)} candidate boards")
        return discovered

    async def _load_discovery_candidates(self) -> list[dict[str, str]]:
        candidates: list[dict[str, str]] = []
        tracked_names = {name.lower() for name, _ in self.companies}

        for candidate in tracked_discovery_candidates():
            if candidate["name"].lower() in tracked_names:
                continue
            if self._extract_ashby_slug(candidate.get("career_page_url", "")):
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
            if self._extract_ashby_slug(career_page_url or ""):
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

    async def _discover_company_slug(
        self,
        client: httpx.AsyncClient,
        candidate: dict[str, str],
    ) -> tuple[str, str] | None:
        company_name = candidate["name"]
        direct_slug = self._extract_ashby_slug(candidate.get("career_page_url", ""))
        if direct_slug:
            return company_name, direct_slug

        direct_slug = self._extract_ashby_slug(candidate.get("website", ""))
        if direct_slug:
            return company_name, direct_slug

        for url in self._candidate_urls(candidate):
            slug = await self._discover_slug_from_url(client, url)
            if slug:
                return company_name, slug

        return None

    def _candidate_urls(self, candidate: dict[str, str]) -> list[str]:
        urls: list[str] = []
        for raw in (candidate.get("career_page_url", ""), candidate.get("website", "")):
            if raw and raw.startswith(("http://", "https://")) and raw not in urls:
                urls.append(raw)
        return urls

    async def _discover_slug_from_url(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> str | None:
        slug = self._extract_ashby_slug(url)
        if slug:
            return slug

        response = await self._safe_fetch_page(client, url)
        if response is None:
            return None

        slug = self._extract_ashby_slug(str(response.url))
        if slug:
            return slug

        slug = self._extract_ashby_slug(response.text)
        if slug:
            return slug

        soup = BeautifulSoup(response.text, "lxml")
        follow_links: list[str] = []
        for link in soup.select("a[href]"):
            href = link.get("href", "").strip()
            if not href:
                continue
            absolute = urljoin(str(response.url), href)
            slug = self._extract_ashby_slug(absolute)
            if slug:
                return slug

            anchor_text = link.get_text(" ", strip=True).lower()
            href_lower = absolute.lower()
            if any(hint in anchor_text for hint in CAREER_LINK_HINTS) or any(hint in href_lower for hint in CAREER_LINK_HINTS):
                if absolute not in follow_links:
                    follow_links.append(absolute)

        origin_host = urlparse(str(response.url)).netloc
        for follow_url in follow_links[:3]:
            follow_host = urlparse(follow_url).netloc
            if follow_host and origin_host and follow_host != origin_host and "ashbyhq.com" not in follow_host:
                continue
            follow_response = await self._safe_fetch_page(client, follow_url)
            if follow_response is None:
                continue
            slug = self._extract_ashby_slug(str(follow_response.url))
            if slug:
                return slug
            slug = self._extract_ashby_slug(follow_response.text)
            if slug:
                return slug

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

    def _extract_ashby_slug(self, text: str) -> str | None:
        for pattern in ASHBY_TOKEN_PATTERNS:
            match = pattern.search(text or "")
            if match:
                return match.group(1).strip()
        return None

    def _dedupe_company_slugs(
        self,
        company_slugs: list[tuple[str, str]],
    ) -> list[tuple[str, str]]:
        deduped: list[tuple[str, str]] = []
        seen_slugs: set[str] = set()
        for company_name, slug in company_slugs:
            normalized = slug.strip()
            if not normalized or normalized in seen_slugs:
                continue
            seen_slugs.add(normalized)
            deduped.append((company_name, normalized))
        return deduped

    async def _fetch_company_safe(
        self,
        company_name: str,
        slug: str,
        result: IngestResult,
    ) -> None:
        try:
            await self._fetch_company(company_name, slug, result)
        except Exception as exc:
            logger.debug(f"Ashby failed for {company_name} ({slug}): {exc}")

    async def _fetch_company(
        self,
        company_name: str,
        slug: str,
        result: IngestResult,
    ) -> None:
        resp = await self._get_board(slug)
        if resp is None:
            return
        data = resp.json()

        job_board = data.get("jobBoard", {})
        company_url = job_board.get("jobBoardUrl", f"https://jobs.ashbyhq.com/{slug}")

        result.companies.append(
            CompanyResult(
                name=company_name,
                career_page_url=company_url,
            )
        )

        jobs = data.get("jobs", [])
        if not jobs:
            return

        target_jobs = [job for job in jobs if is_target_role(job.get("title", ""))]
        if not target_jobs:
            return

        recent_jobs: list[dict[str, Any]] = []
        for job in target_jobs:
            role = self._parse_role(job, company_name, slug)
            result.roles.append(role)
            result.signals.append(self._make_signal(job, company_name, slug, role))

            if self._is_recent(job.get("publishedAt", "")):
                recent_jobs.append(job)

        if len(recent_jobs) >= 3:
            titles = ", ".join(job.get("title", "") for job in recent_jobs[:3])
            result.signals.append(
                SignalResult(
                    company_name=company_name,
                    type=SignalType.ATS_ASHBY,
                    headline=f"{len(recent_jobs)} engineering roles posted simultaneously — {titles}",
                    detail=(
                        "Same-window batch posting signals headcount budget approval. "
                        "High-urgency window — move within 48h."
                    ),
                    source_url=company_url,
                    signal_date=datetime.utcnow(),
                    score=88.0,
                )
            )

        logger.info(
            f"Ashby {company_name}: {len(target_jobs)} target roles ({len(recent_jobs)} recent)"
        )

    async def _get_board(self, slug: str) -> httpx.Response | None:
        async with make_client(timeout=20.0) as client:
            response = await client.get(ASHBY_API.format(slug=slug))
            if response.status_code == 404:
                logger.debug(f"Ashby board not found: {slug}")
                return None
            if response.status_code in {401, 403}:
                logger.debug(f"Ashby board blocked: {slug} ({response.status_code})")
                return None
            if response.status_code == 429:
                logger.warning(f"Ashby rate limited: {slug}")
                return None
            response.raise_for_status()
            return response

    def _parse_role(
        self,
        job: dict[str, Any],
        company_name: str,
        slug: str,
    ) -> RoleResult:
        title = job.get("title", "").strip()
        job_id = job.get("id", "")
        description = job.get("descriptionHtml", "") or job.get("description", "")
        location = job.get("location", "") or job.get("locationName", "")

        location_lower = (location or "").lower()
        is_remote = any(
            token in location_lower
            for token in ("remote", "anywhere", "distributed", "worldwide")
        ) or job.get("isRemote", False)
        is_remote_us = (
            is_remote
            and any(token in location_lower for token in ("us", "united states", "america", "usa"))
        ) or (is_remote and not location)

        tech_stack = extract_tech_stack(description or "")
        return RoleResult(
            company_name=company_name,
            title=title,
            url=ASHBY_JOB_URL.format(slug=slug, job_id=job_id),
            source=SignalType.ATS_ASHBY,
            description_raw=description[:5000] if description else "",
            role_type=extract_role_type(title),
            seniority=extract_seniority(title),
            is_remote=is_remote,
            is_remote_us=is_remote_us,
            location=location or "",
            external_id=str(job_id),
            tech_stack=tech_stack,
            required_skills=tech_stack.get("languages", []),
        )

    def _make_signal(
        self,
        job: dict[str, Any],
        company_name: str,
        slug: str,
        role: RoleResult,
    ) -> SignalResult:
        published = job.get("publishedAt", "")
        try:
            from dateutil.parser import parse

            signal_date = (
                parse(published).replace(tzinfo=None) if published else datetime.utcnow()
            )
        except Exception:
            signal_date = datetime.utcnow()

        days_old = (datetime.utcnow() - signal_date).days
        score = max(70.0 - (days_old * 1.5), 20.0)

        return SignalResult(
            company_name=company_name,
            type=SignalType.ATS_ASHBY,
            headline=f"{role.title} — {role.location or 'Remote'}",
            detail=(
                f"Captured from Ashby job board (jobs.ashbyhq.com/{slug}). "
                "Ashby boards usually have lower candidate volume than LinkedIn or Greenhouse."
            ),
            source_url=role.url,
            signal_date=signal_date,
            score=score,
        )

    def _detect_batch_signals(self, result: IngestResult) -> None:
        """Boost same-day Ashby signals for companies posting in bulk."""
        today = datetime.utcnow().date()
        company_today: defaultdict[str, int] = defaultdict(int)

        for signal in result.signals:
            if signal.signal_date.date() == today:
                company_today[signal.company_name] += 1

        for signal in result.signals:
            if company_today[signal.company_name] >= 3:
                signal.score = min(signal.score * 1.3, 100.0)

    def _is_recent(self, date_str: str, days: int = 2) -> bool:
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


async def discover_ashby_slug(company_name: str, careers_url: str) -> str | None:
    """
    Best-effort discovery for Ashby-hosted career pages referenced from a site.
    """
    del company_name  # Reserved for future heuristics.

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(careers_url)
    except Exception:
        return None

    html = response.text
    for pattern in ASHBY_TOKEN_PATTERNS:
        match = pattern.search(html)
        if match:
            return match.group(1)

    return None
