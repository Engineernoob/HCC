"""
Portfolio job board ingestion.

Targets multi-company hiring boards such as:
  - a16z Jobs (Consider-powered)

For Consider boards we use the same JSON endpoint the frontend uses rather than
browser automation. That is materially faster, lower-memory, and easier to
extend to similar portfolio boards.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

from hirectl.config import settings
from hirectl.db.models import FundingStage
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
)
from hirectl.tracked_companies import TrackedPortfolioBoard, tracked_portfolio_boards


@dataclass(frozen=True)
class PortfolioJob:
    company_name: str
    title: str
    url: str
    location: str = ""
    description: str = ""
    remote: bool = False
    stage: FundingStage = FundingStage.UNKNOWN
    posted_at: datetime | None = None
    tech_stack: dict[str, list[str]] | None = None
    required_skills: list[str] | None = None


class PortfolioBoardsAdapter(BaseIngestionAdapter):
    source_name = "portfolio_boards"

    def __init__(self) -> None:
        super().__init__()
        self.boards = tracked_portfolio_boards()

    async def fetch(self) -> IngestResult:
        result = IngestResult(source=self.source_name)

        for board in self.boards:
            try:
                jobs = await self._fetch_board_jobs(board)
            except Exception as exc:
                self.logger.warning("%s failed: %s", board.name, exc)
                continue

            if jobs:
                self.logger.info("%s: %s candidate jobs", board.name, len(jobs))
            self._append_jobs(result, board, jobs)

        return result

    async def _fetch_board_jobs(self, board: TrackedPortfolioBoard) -> list[PortfolioJob]:
        if board.provider == "consider":
            return await self._fetch_consider_jobs(board)
        raise ValueError(f"Unsupported portfolio board provider: {board.provider}")

    async def _fetch_consider_jobs(self, board: TrackedPortfolioBoard) -> list[PortfolioJob]:
        endpoint = urljoin(board.board_url, "/api-boards/search-jobs")
        page_size = max(25, min(board.page_size or 100, 250))
        jobs: list[PortfolioJob] = []
        seen_urls: set[str] = set()
        sequence: str | None = None

        while True:
            payload: dict[str, Any] = {
                "meta": {"size": page_size},
                "board": {
                    "id": board.board_id,
                    "isParent": board.is_parent,
                },
                "query": {},
                "grouped": False,
            }
            if sequence:
                payload["meta"]["after"] = sequence

            response = await self._post(
                endpoint,
                json=payload,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Origin": board.board_url.rstrip("/jobs"),
                    "Referer": board.board_url,
                },
            )
            data = response.json()
            batch = data.get("jobs") or []
            if not isinstance(batch, list) or not batch:
                break

            new_jobs = 0
            for item in batch:
                job = self._job_from_consider_item(item, board)
                if not job or job.url in seen_urls:
                    continue
                seen_urls.add(job.url)
                jobs.append(job)
                new_jobs += 1

            sequence = self._next_sequence(data)
            if new_jobs == 0 or not sequence or len(batch) < page_size:
                break

        return jobs

    def _job_from_consider_item(
        self,
        item: dict[str, Any],
        board: TrackedPortfolioBoard,
    ) -> PortfolioJob | None:
        title = self._string(item.get("title"))
        company_name = self._string(item.get("companyName"))
        url = self._string(item.get("url")) or self._string(item.get("applyUrl"))
        if not title or not company_name or not url:
            return None

        normalized_url = urljoin(board.board_url, url)
        skills = self._flatten_strings(item.get("requiredSkills")) + self._flatten_strings(
            item.get("preferredSkills")
        )
        markets = self._flatten_strings(item.get("markets"))
        location = self._extract_location(item)
        remote = bool(item.get("remote")) or "remote" in location.lower()
        if bool(item.get("hybrid")) and location:
            location = f"{location} · Hybrid"

        summary_parts = []
        if markets:
            summary_parts.append(f"Markets: {', '.join(markets[:4])}")
        if skills:
            summary_parts.append(f"Skills: {', '.join(skills[:6])}")
        description = " | ".join(summary_parts)

        tech_stack = extract_tech_stack(" ".join([title, description, *skills]))
        return PortfolioJob(
            company_name=company_name,
            title=title,
            url=normalized_url,
            location=location,
            description=description,
            remote=remote,
            stage=self._funding_stage(item.get("fundingLV")),
            posted_at=self._parse_datetime(item.get("timeStamp")),
            tech_stack=tech_stack,
            required_skills=skills[:12],
        )

    def _append_jobs(
        self,
        result: IngestResult,
        board: TrackedPortfolioBoard,
        jobs: list[PortfolioJob],
    ) -> None:
        companies_seen: set[str] = set()

        for job in jobs:
            if not is_target_role(job.title):
                continue

            if job.company_name not in companies_seen:
                result.companies.append(
                    CompanyResult(
                        name=job.company_name,
                        career_page_url=board.board_url,
                        funding_stage=job.stage,
                        remote_friendly=job.remote,
                        remote_us=job.remote,
                        tech_stack=job.tech_stack or {},
                    )
                )
                companies_seen.add(job.company_name)

            result.roles.append(
                RoleResult(
                    company_name=job.company_name,
                    title=job.title,
                    url=job.url,
                    source=SignalType.CAREER_PAGE,
                    description_raw=job.description,
                    role_type=extract_role_type(job.title),
                    seniority=extract_seniority(job.title),
                    is_remote=job.remote,
                    is_remote_us=job.remote,
                    location=job.location,
                    tech_stack=job.tech_stack or {},
                    required_skills=job.required_skills or [],
                )
            )

            result.signals.append(
                SignalResult(
                    company_name=job.company_name,
                    type=SignalType.CAREER_PAGE,
                    headline=f"{job.title} listed on {board.name}",
                    detail=(
                        f"Captured from {board.name}. "
                        "This role is visible on a multi-company portfolio hiring board."
                    ),
                    source_url=job.url,
                    raw_content=job.description or job.title,
                    signal_date=job.posted_at or datetime.utcnow(),
                    score=60.0 if job.remote else 57.0,
                )
            )

    def _next_sequence(self, payload: dict[str, Any]) -> str | None:
        meta = payload.get("meta")
        if isinstance(meta, dict):
            sequence = meta.get("sequence")
            if isinstance(sequence, str) and sequence.strip():
                return sequence
        return None

    def _extract_location(self, item: dict[str, Any]) -> str:
        locations = self._flatten_strings(item.get("locations"))
        if locations:
            return ", ".join(locations[:3])

        normalized = item.get("normalizedLocations")
        if isinstance(normalized, list):
            parts = []
            for entry in normalized:
                if not isinstance(entry, dict):
                    continue
                city = self._string(entry.get("name"))
                country = self._string(entry.get("country"))
                label = ", ".join(part for part in (city, country) if part)
                if label:
                    parts.append(label)
            if parts:
                return ", ".join(parts[:3])

        return ""

    def _flatten_strings(self, value: Any) -> list[str]:
        parts: list[str] = []
        if isinstance(value, str):
            text = value.strip()
            if text:
                parts.append(text)
        elif isinstance(value, dict):
            for candidate in ("label", "name", "value", "title"):
                text = self._string(value.get(candidate))
                if text:
                    parts.append(text)
                    break
        elif isinstance(value, list):
            for item in value:
                parts.extend(self._flatten_strings(item))
        return parts

    def _funding_stage(self, funding: Any) -> FundingStage:
        label = ""
        if isinstance(funding, dict):
            label = self._string(funding.get("label")) or ""
        elif isinstance(funding, str):
            label = funding

        text = label.lower()
        if "seed" in text:
            return FundingStage.SEED
        if "series a" in text:
            return FundingStage.SERIES_A
        if "series b" in text:
            return FundingStage.SERIES_B
        if "series c" in text:
            return FundingStage.SERIES_C
        if any(token in text for token in ("series d", "series e", "series f", "growth", "late")):
            return FundingStage.SERIES_D_PLUS
        if any(token in text for token in ("public", "ipo")):
            return FundingStage.PUBLIC
        return FundingStage.UNKNOWN

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is not None:
            return parsed.astimezone().replace(tzinfo=None)
        return parsed

    def _string(self, value: Any) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None
