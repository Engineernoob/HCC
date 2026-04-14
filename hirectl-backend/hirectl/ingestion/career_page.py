"""
Career page diff crawler.

Monitors company career pages directly for new job postings.
This is the highest-signal source because:
  1. Roles appear here BEFORE they're syndicated to job boards
  2. A direct listing means no applicant pile yet
  3. The diff catches removals too (role filled = company is hiring successfully)

Strategy:
  - Fetch the career page HTML every 6 hours
  - Store a normalized fingerprint of job listings
  - Diff against previous fingerprint
  - On new listings: emit SignalResult + RoleResult
  - On removed listings: emit a "role filled" signal (company is hiring)

Works with common ATS patterns: Greenhouse iframes, Lever embeds,
Ashby embeds, Workable, and raw HTML job lists.
"""

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

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
    is_target_role,
    make_client,
)
from hirectl.tracked_companies import tracked_career_pages, tracked_discovery_candidates

logger = logging.getLogger(__name__)


@dataclass
class CareerPageSnapshot:
    """A normalized snapshot of a company's career page at a point in time."""
    company_name: str
    url: str
    captured_at: datetime
    job_fingerprints: dict[str, str]  # {title_slug: content_hash}
    raw_jobs: list[dict]              # [{title, url, location, description}]
    page_hash: str = ""               # Full page hash for quick change detection

    def job_slugs(self) -> set[str]:
        return set(self.job_fingerprints.keys())


# Companies to crawl directly — (name, career_page_url)
# These are companies that may not be on standard ATS boards
CAREER_PAGES: list[tuple[str, str]] = tracked_career_pages()


class CareerPageCrawler(BaseIngestionAdapter):
    """
    Diffs company career pages against stored snapshots.
    """

    source_name = "career_page"
    batch_size = 5

    def __init__(
        self,
        pages: list[tuple[str, str]] | None = None,
        snapshot_store: Optional["SnapshotStore"] = None,
    ):
        super().__init__()
        self.pages = pages or CAREER_PAGES
        self.batch_size = settings.career_page_batch_size
        self.store = snapshot_store or PostgresSnapshotStore()
        self._playwright = None
        self._browser = None

    async def fetch(self) -> IngestResult:
        result = IngestResult(source=self.source_name)
        pages = self._dedupe_pages(
            await self._load_stored_pages()
            + self.pages
            + await self._discover_career_pages()
        )

        try:
            for i in range(0, len(pages), self.batch_size):
                batch = pages[i : i + self.batch_size]
                tasks = [
                    self._crawl_page(name, url, result)
                    for name, url in batch
                ]
                await asyncio.gather(*tasks, return_exceptions=True)
                # Polite delay between batches
                if i + self.batch_size < len(pages):
                    await asyncio.sleep(settings.career_page_batch_delay_seconds)

            return result
        finally:
            await self._shutdown_browser()

    async def _load_stored_pages(self) -> list[tuple[str, str]]:
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
            stored.append((name, career_page_url))
        return stored

    async def _discover_career_pages(self) -> list[tuple[str, str]]:
        candidates = await self._load_discovery_candidates()
        if not candidates:
            return []

        discovered: list[tuple[str, str]] = []
        async with make_client(timeout=15.0) as client:
            for i in range(0, len(candidates), self.batch_size):
                batch = candidates[i : i + self.batch_size]
                pages = await asyncio.gather(
                    *(self._discover_candidate_page(client, candidate) for candidate in batch)
                )
                discovered.extend(page for page in pages if page)

        if discovered:
            logger.info(f"Career page discovery found {len(discovered)} candidate pages")
        return discovered

    async def _load_discovery_candidates(self) -> list[dict[str, str]]:
        candidates: list[dict[str, str]] = []
        tracked_names = {name.lower() for name, _ in self.pages}

        for candidate in tracked_discovery_candidates():
            if candidate["name"].lower() in tracked_names:
                continue
            if candidate.get("career_page_url"):
                continue
            website_host = urlparse(candidate.get("website", "")).netloc.lower()
            if website_host.endswith("workatastartup.com"):
                continue
            if candidate.get("website"):
                candidates.append(
                    {
                        "name": candidate["name"],
                        "website": candidate["website"],
                    }
                )

        async with get_session() as session:
            rows = (
                await session.execute(
                    select(Company.name, Company.website, Company.career_page_url)
                    .where(Company.website.is_not(None))
                )
            ).all()

        for name, website, career_page_url in rows:
            if not name or not website:
                continue
            if career_page_url:
                continue
            if any(existing_name.lower() == name.lower() for existing_name, _ in self.pages):
                continue
            website_host = urlparse(website).netloc.lower()
            if website_host.endswith("workatastartup.com"):
                continue
            candidates.append(
                {
                    "name": name,
                    "website": website,
                }
            )
        return candidates

    async def _discover_candidate_page(
        self,
        client,
        candidate: dict[str, str],
    ) -> tuple[str, str] | None:
        url = candidate["website"]
        company_name = candidate["name"]

        response = await self._safe_fetch_page(client, url)
        if response is None:
            return None

        discovered_urls = self._extract_candidate_page_urls(response.text, str(response.url))
        for discovered_url in discovered_urls[:5]:
            probe = await self._safe_fetch_page(client, discovered_url)
            if probe is None:
                continue
            final_url = str(probe.url)
            if self._looks_like_career_page(probe.text, final_url):
                return company_name, final_url

        return None

    async def _safe_fetch_page(self, client, url: str):
        try:
            response = await client.get(url)
            if response.status_code >= 400:
                return None
            return response
        except Exception:
            return None

    def _extract_candidate_page_urls(self, html: str, base_url: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []

        if self._looks_like_career_page(html, base_url):
            urls.append(base_url)

        for link in soup.select("a[href]"):
            href = link.get("href", "").strip()
            if not href:
                continue
            absolute = urljoin(base_url, href)
            anchor_text = link.get_text(" ", strip=True).lower()
            href_lower = absolute.lower()
            if any(hint in anchor_text for hint in ("career", "careers", "jobs", "join", "open roles", "open positions")) or any(
                hint in href_lower for hint in ("career", "careers", "jobs", "greenhouse", "lever", "ashby", "workable")
            ):
                if absolute not in urls:
                    urls.append(absolute)

        return urls

    def _looks_like_career_page(self, html: str, url: str) -> bool:
        url_lower = url.lower()
        if any(token in url_lower for token in ("career", "careers", "jobs", "greenhouse", "lever", "ashby", "workable")):
            return True

        html_lower = html.lower()
        return any(
            token in html_lower
            for token in (
                "open roles",
                "open positions",
                "job openings",
                "join our team",
                "greenhouse.io",
                "jobs.ashbyhq.com",
                "jobs.lever.co",
                "workable.com",
            )
        )

    def _dedupe_pages(self, pages: list[tuple[str, str]]) -> list[tuple[str, str]]:
        deduped: list[tuple[str, str]] = []
        seen_names: set[str] = set()
        seen_urls: set[str] = set()
        for company_name, url in pages:
            normalized_name = company_name.lower().strip()
            normalized_url = url.strip()
            if not normalized_name or not normalized_url:
                continue
            if normalized_name in seen_names or normalized_url in seen_urls:
                continue
            seen_names.add(normalized_name)
            seen_urls.add(normalized_url)
            deduped.append((company_name, normalized_url))
        return deduped

    async def _crawl_page(
        self,
        company_name: str,
        url: str,
        result: IngestResult,
    ) -> None:
        try:
            html, final_url = await self._fetch_page_document(url)
            canonical_url = self._canonical_page_url(url, final_url)
        except Exception as e:
            logger.debug(f"Career page fetch failed {company_name}: {e}")
            return

        try:
            snapshot = self._parse_page(company_name, canonical_url, html)
        except Exception as e:
            logger.debug(f"Career page parse failed {company_name}: {e}")
            return

        result.companies.append(CompanyResult(name=company_name, career_page_url=canonical_url))

        current_target_jobs = [
            job for job in snapshot.raw_jobs if is_target_role(job.get("title", ""))
        ]
        for job in current_target_jobs:
            result.roles.append(self._job_to_role(job, company_name))

        prev = await self.store.get(company_name)
        await self.store.save(company_name, snapshot)

        if prev is None:
            # First crawl — baseline, no diff
            logger.info(f"Career page baseline: {company_name} — {len(snapshot.raw_jobs)} jobs")
            return

        if prev.page_hash == snapshot.page_hash:
            logger.debug(f"Career page unchanged: {company_name}")
            return

        # Compute diff
        added_slugs = snapshot.job_slugs() - prev.job_slugs()
        removed_slugs = prev.job_slugs() - snapshot.job_slugs()

        # Map slugs back to job dicts
        slug_to_job = {self._slug(j["title"]): j for j in snapshot.raw_jobs}
        prev_slug_to_job = {self._slug(j["title"]): j for j in prev.raw_jobs}

        # New roles
        new_target_jobs = [
            slug_to_job[s]
            for s in added_slugs
            if s in slug_to_job and is_target_role(slug_to_job[s].get("title", ""))
        ]

        for job in new_target_jobs:
            signal = SignalResult(
                company_name=company_name,
                type=SignalType.CAREER_PAGE,
                headline=(
                    f"{job['title']} — direct listing, not yet syndicated to job boards"
                ),
                detail=(
                    f"Detected via career page diff on {canonical_url}. "
                    f"This role has not appeared on Greenhouse, Lever, or LinkedIn Jobs yet. "
                    f"Early signal — no applicant pile. "
                    f"Location: {job.get('location', 'not specified')}."
                ),
                source_url=job.get("url", canonical_url),
                signal_date=datetime.utcnow(),
                score=72.0,  # High score — direct = early signal
            )
            result.signals.append(signal)

        # Removed roles (filled signal)
        removed_target = [
            prev_slug_to_job[s] for s in removed_slugs
            if s in prev_slug_to_job and is_target_role(prev_slug_to_job[s].get("title", ""))
        ]

        for job in removed_target:
            # A filled engineering role means the company IS hiring successfully
            result.signals.append(
                SignalResult(
                    company_name=company_name,
                    type=SignalType.CAREER_PAGE,
                    headline=f"{job['title']} removed — role filled or paused",
                    detail=(
                        "Engineering role disappeared from career page. "
                        "If filled: confirms company is actively hiring. "
                        "Watch for new postings in same role family."
                    ),
                    source_url=canonical_url,
                    signal_date=datetime.utcnow(),
                    score=25.0,
                )
            )

        if new_target_jobs:
            logger.info(
                f"Career page diff {company_name}: "
                f"+{len(new_target_jobs)} new, -{len(removed_target)} removed"
            )

    def _parse_page(
        self,
        company_name: str,
        url: str,
        html: str,
    ) -> CareerPageSnapshot:
        """
        Extract job listings from career page HTML.
        Handles common patterns: ATS iframes, semantic job lists, JSON-LD.
        """
        soup = BeautifulSoup(html, "lxml")
        jobs: list[dict] = []

        # Strategy 1: JSON-LD structured data (best quality)
        jobs.extend(self._extract_json_ld(soup, url))

        # Strategy 2: Common ATS embed patterns
        if not jobs:
            jobs.extend(self._extract_ats_patterns(soup, url))

        # Strategy 3: Semantic HTML patterns
        if not jobs:
            jobs.extend(self._extract_semantic_patterns(soup, url))

        # Strategy 4: Generic link-based extraction
        if not jobs:
            jobs.extend(self._extract_links(soup, url))

        # Build fingerprints
        fingerprints = {}
        for job in jobs:
            slug = self._slug(job.get("title", ""))
            if slug:
                content = f"{job.get('title', '')}:{job.get('location', '')}:{job.get('url', '')}"
                fingerprints[slug] = hashlib.md5(content.encode()).hexdigest()[:8]

        page_hash = hashlib.md5(html.encode()).hexdigest()[:16]

        return CareerPageSnapshot(
            company_name=company_name,
            url=url,
            captured_at=datetime.utcnow(),
            job_fingerprints=fingerprints,
            raw_jobs=jobs,
            page_hash=page_hash,
        )

    def _extract_json_ld(self, soup: BeautifulSoup, base_url: str) -> list[dict]:
        """Extract JobPosting schema.org data."""
        import json
        jobs = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict) and data.get("@graph"):
                    items = data["@graph"]
                else:
                    items = [data]

                for item in items:
                    if item.get("@type") == "JobPosting":
                        jobs.append({
                            "title": item.get("title", ""),
                            "url": item.get("url", base_url),
                            "location": (
                                item.get("jobLocation", {})
                                .get("address", {})
                                .get("addressLocality", "")
                                if isinstance(item.get("jobLocation"), dict)
                                else ""
                            ),
                            "description": item.get("description", "")[:500],
                        })
            except Exception:
                continue
        return jobs

    def _extract_ats_patterns(self, soup: BeautifulSoup, base_url: str) -> list[dict]:
        """Extract from common ATS embed patterns."""
        jobs = []

        # Greenhouse embed: div.opening
        for div in soup.select("div.opening, .opening a"):
            a = div if div.name == "a" else div.find("a")
            if a and a.get_text(strip=True):
                href = a.get("href", "")
                jobs.append({
                    "title": a.get_text(strip=True),
                    "url": href if href.startswith("http") else urljoin(base_url, href),
                    "location": "",
                    "description": "",
                })

        # Lever: .posting-title
        for item in soup.select(".posting"):
            title_el = item.select_one(".posting-title h5, .posting-name")
            link_el = item.select_one("a[href]")
            loc_el = item.select_one(".posting-categories .location")
            if title_el:
                href = link_el.get("href", "") if link_el else ""
                jobs.append({
                    "title": title_el.get_text(strip=True),
                    "url": href if href.startswith("http") else urljoin(base_url, href),
                    "location": loc_el.get_text(strip=True) if loc_el else "",
                    "description": "",
                })

        # Ashby: data-job-id attributes
        for item in soup.select("[data-job-id], .ashby-job-posting-brief-title"):
            title_el = item.select_one(".ashby-job-posting-brief-title, h3, h4")
            link_el = item.find("a")
            if title_el:
                href = link_el.get("href", "") if link_el else ""
                jobs.append({
                    "title": title_el.get_text(strip=True),
                    "url": href if href.startswith("http") else urljoin(base_url, href),
                    "location": "",
                    "description": "",
                })

        return jobs

    def _extract_semantic_patterns(self, soup: BeautifulSoup, base_url: str) -> list[dict]:
        """Extract from semantic HTML patterns common on hand-rolled career pages."""
        jobs = []

        # Pattern: <li> or <div> with role-sounding text + link
        for container in soup.select("ul.jobs li, ol.jobs li, .jobs-list li, .careers-list li"):
            a = container.find("a")
            if a:
                title = a.get_text(strip=True)
                if len(title) > 5:
                    href = a.get("href", "")
                    jobs.append({
                        "title": title,
                        "url": href if href.startswith("http") else urljoin(base_url, href),
                        "location": "",
                        "description": "",
                    })

        # Pattern: heading tags near job-sounding links
        for h in soup.find_all(["h3", "h4", "h5"]):
            text = h.get_text(strip=True)
            if is_target_role(text) and 10 < len(text) < 100:
                a = h.find("a") or h.find_next("a")
                href = a.get("href", "") if a else ""
                jobs.append({
                    "title": text,
                    "url": href if href.startswith("http") else urljoin(base_url, href),
                    "location": "",
                    "description": "",
                })

        return jobs

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> list[dict]:
        """
        Last resort: find all links whose text looks like job titles.
        Conservative — only match clear engineering role patterns.
        """
        jobs = []
        seen = set()

        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a.get("href", "")

            if not text or len(text) < 10 or len(text) > 100:
                continue
            if text in seen:
                continue
            if not is_target_role(text):
                continue

            # Must look like a job link (contains /job/ /career/ /role/ etc.)
            if not any(k in href.lower() for k in (
                "/job", "/career", "/role", "/opening", "/position",
                "lever.co", "greenhouse.io", "ashby", "workable",
            )):
                continue

            seen.add(text)
            jobs.append({
                "title": text,
                "url": href if href.startswith("http") else urljoin(base_url, href),
                "location": "",
                "description": "",
            })

        return jobs[:30]  # Cap at 30 to avoid garbage

    def _job_to_role(self, job: dict, company_name: str) -> RoleResult:
        title = job.get("title", "")
        location = job.get("location", "")
        description = job.get("description", "")

        is_remote = any(k in location.lower() for k in ("remote", "anywhere", "distributed"))

        return RoleResult(
            company_name=company_name,
            title=title,
            url=job.get("url", ""),
            source=SignalType.CAREER_PAGE,
            description_raw=description,
            role_type=extract_role_type(title),
            seniority=extract_seniority(title),
            is_remote=is_remote,
            is_remote_us=is_remote,
            location=location,
        )

    def _slug(self, title: str) -> str:
        """Normalize a job title to a stable slug for diffing."""
        return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]

    def _canonical_page_url(self, original_url: str, final_url: str) -> str:
        original_lower = original_url.lower()
        final_lower = final_url.lower()
        original_has_career_hint = any(token in original_lower for token in ("career", "careers", "jobs"))
        final_has_career_hint = any(token in final_lower for token in ("career", "careers", "jobs"))

        if original_has_career_hint and not final_has_career_hint:
            return original_url
        return final_url

    def _should_render_with_playwright(self, html: str, url: str) -> bool:
        html_lower = html.lower()
        text_content = re.sub(
            r"\s+",
            " ",
            BeautifulSoup(html, "lxml").get_text(" ", strip=True),
        ).lower()

        if any(
            marker in html_lower
            for marker in (
                "jobs.ashbyhq.com",
                "boards.greenhouse.io",
                "job-boards.greenhouse.io",
                "jobs.lever.co",
                "workable.com",
                '"@type":"jobposting"',
                '"@type": "jobposting"',
            )
        ):
            return False

        if any(
            marker in text_content
            for marker in ("open roles", "open positions", "job openings", "join our team")
        ):
            return False

        return any(
            marker in html_lower
            for marker in (
                "enable javascript",
                "please turn on javascript",
                "__next_data__",
                "__nuxt",
                "id=\"__next\"",
                "id=\"root\"",
            )
        ) or len(text_content) < 200

    async def _fetch_page_document(self, url: str) -> tuple[str, str]:
        if settings.career_page_renderer == "playwright":
            try:
                return await self._render_with_playwright(url)
            except ImportError:
                logger.debug("Playwright not installed; falling back to HTTP fetch")
            except Exception as exc:
                logger.debug(f"Playwright render failed for {url}: {exc}")

        response = await self._get(url)
        html = response.text
        final_url = str(response.url)

        if (
            settings.career_page_renderer == "auto"
            and self._should_render_with_playwright(html, final_url)
        ):
            try:
                return await self._render_with_playwright(final_url)
            except ImportError:
                logger.debug("Playwright not installed; using HTTP response")
            except Exception as exc:
                logger.debug(f"Playwright render failed for {final_url}: {exc}")

        return html, final_url

    async def _render_with_playwright(self, url: str) -> tuple[str, str]:
        browser = await self._ensure_browser()
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=settings.playwright_timeout_ms)
            await page.wait_for_timeout(500)
            return await page.content(), page.url
        finally:
            await page.close()

    async def _ensure_browser(self):
        if self._browser is not None:
            return self._browser

        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        return self._browser

    async def _shutdown_browser(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None


# ── Snapshot store ─────────────────────────────────────────────────

class SnapshotStore:
    """Abstract snapshot persistence interface."""

    async def get(self, company_name: str) -> Optional[CareerPageSnapshot]:
        raise NotImplementedError

    async def save(self, company_name: str, snapshot: CareerPageSnapshot) -> None:
        raise NotImplementedError


class InMemorySnapshotStore(SnapshotStore):
    """In-memory store for development. Loses state on restart."""

    def __init__(self):
        self._store: dict[str, CareerPageSnapshot] = {}

    async def get(self, company_name: str) -> Optional[CareerPageSnapshot]:
        return self._store.get(company_name)

    async def save(self, company_name: str, snapshot: CareerPageSnapshot) -> None:
        self._store[company_name] = snapshot


class PostgresSnapshotStore(SnapshotStore):
    """
    Persists latest snapshots to PostgreSQL with an in-memory fallback cache.
    """

    def __init__(self):
        self._cache: dict[str, CareerPageSnapshot] = {}

    async def get(self, company_name: str) -> Optional[CareerPageSnapshot]:
        # Check memory cache first
        if company_name in self._cache:
            return self._cache[company_name]

        try:
            from sqlalchemy import select

            from hirectl.db.models import CareerPageSnapshotRecord

            async with get_session() as session:
                result = await session.execute(
                    select(CareerPageSnapshotRecord).where(
                        CareerPageSnapshotRecord.company_name == company_name
                    )
                )
                record = result.scalar_one_or_none()
        except Exception as exc:
            logger.debug(f"Snapshot load failed for {company_name}: {exc}")
            return None

        if record is None:
            return None

        snapshot = self._record_to_snapshot(record)
        self._cache[company_name] = snapshot
        return snapshot

    async def save(self, company_name: str, snapshot: CareerPageSnapshot) -> None:
        self._cache[company_name] = snapshot
        try:
            from sqlalchemy import select

            from hirectl.db.models import CareerPageSnapshotRecord

            async with get_session() as session:
                result = await session.execute(
                    select(CareerPageSnapshotRecord).where(
                        CareerPageSnapshotRecord.company_name == company_name
                    )
                )
                record = result.scalar_one_or_none()
                if record is None:
                    record = CareerPageSnapshotRecord(
                        company_name=company_name,
                        page_url=snapshot.url,
                        page_hash=snapshot.page_hash,
                        job_fingerprints=snapshot.job_fingerprints,
                        raw_jobs=snapshot.raw_jobs,
                        captured_at=snapshot.captured_at,
                    )
                    session.add(record)
                else:
                    record.page_url = snapshot.url
                    record.page_hash = snapshot.page_hash
                    record.job_fingerprints = snapshot.job_fingerprints
                    record.raw_jobs = snapshot.raw_jobs
                    record.captured_at = snapshot.captured_at
                    record.updated_at = datetime.utcnow()
        except Exception as exc:
            logger.debug(f"Snapshot save failed for {company_name}: {exc}")

    def _record_to_snapshot(self, record: Any) -> CareerPageSnapshot:
        return CareerPageSnapshot(
            company_name=record.company_name,
            url=record.page_url,
            captured_at=record.captured_at,
            job_fingerprints=record.job_fingerprints or {},
            raw_jobs=record.raw_jobs or [],
            page_hash=record.page_hash or "",
        )
