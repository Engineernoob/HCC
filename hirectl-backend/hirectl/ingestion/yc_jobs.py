"""
YC Jobs ingestion adapter.

Parses the current Work at a Startup jobs page.
YC jobs are the highest signal-to-noise source for startup engineering roles.
"""

import json
import logging
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

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
from hirectl.db.models import FundingStage, RoleType

logger = logging.getLogger(__name__)

# Current Work at a Startup public jobs page. The page server-renders a `data-page`
# attribute containing the initial jobs array, which is more stable than the old
# removed `/companies/fetch-jobs` endpoint.
WORKATASTARTUP_JOBS_URL = "https://www.workatastartup.com/jobs"


class YCJobsAdapter(BaseIngestionAdapter):
    """
    Fetches engineering roles from YC's Work at a Startup board.
    Parses the server-rendered jobs payload embedded in the public page.
    """

    source_name = "yc_jobs"

    TARGET_ROLE_TYPES = {
        "android",
        "backend",
        "data science",
        "devops",
        "embedded systems",
        "engineering manager",
        "frontend",
        "full stack",
        "ios",
        "machine learning",
        "qa engineer",
        "robotics",
        "hardware",
        "electrical",
        "mechanical",
        "bioengineering",
        "chemical engineering",
    }

    async def fetch(self) -> IngestResult:
        result = IngestResult(source=self.source_name)

        try:
            jobs_data = await self._fetch_jobs()
        except Exception as e:
            result.error = f"Failed to fetch YC jobs: {e}"
            return result

        companies_by_slug: dict[str, dict[str, Any]] = {}

        for job_data in jobs_data:
            if not self._is_target_job(job_data):
                continue

            try:
                company_slug = (job_data.get("companySlug") or "").strip()
                company_name = (job_data.get("companyName") or "").strip()
                if not company_slug or not company_name:
                    continue

                company_record = companies_by_slug.setdefault(
                    company_slug,
                    {
                        "name": company_name,
                        "slug": company_slug,
                        "one_liner": job_data.get("companyOneLiner", ""),
                        "batch": job_data.get("companyBatch", ""),
                        "remote_friendly": False,
                        "remote_us": False,
                    },
                )
                company_record["remote_friendly"] = (
                    company_record["remote_friendly"] or self._job_is_remote(job_data)
                )
                company_record["remote_us"] = (
                    company_record["remote_us"] or self._job_is_remote_us(job_data)
                )

                role = self._parse_role(job_data, company_name)
                result.roles.append(role)
                result.signals.append(self._make_role_signal(role, company_name))

            except Exception as e:
                logger.warning(f"Failed to parse YC job: {e}")
                continue

        for company_data in companies_by_slug.values():
            try:
                result.companies.append(self._parse_company(company_data))
            except Exception as e:
                logger.warning(f"Failed to parse YC company: {e}")

        return result

    async def _fetch_jobs(self) -> list[dict[str, Any]]:
        """Fetch the server-rendered jobs payload from Work at a Startup."""
        resp = await self._get(
            WORKATASTARTUP_JOBS_URL,
            params={"role": "eng"},
        )
        soup = BeautifulSoup(resp.text, "lxml")
        page_div = soup.select_one("div[data-page][id^='jobs/public/pages/JobsPage-react-component']")
        if page_div is None:
            raise ValueError("Work at a Startup jobs payload not found in page")

        raw_payload = page_div.get("data-page")
        if not raw_payload:
            raise ValueError("Work at a Startup jobs payload is empty")

        payload = json.loads(raw_payload)
        jobs = payload.get("props", {}).get("jobs", [])
        if not isinstance(jobs, list):
            raise ValueError("Work at a Startup jobs payload is malformed")

        return jobs

    def _parse_company(self, data: dict[str, Any]) -> CompanyResult:
        return CompanyResult(
            name=data.get("name", "").strip(),
            career_page_url=f"https://www.workatastartup.com/companies/{data.get('slug', '').strip()}",
            description=data.get("one_liner", ""),
            hq_city="",
            hq_country=data.get("country", "United States"),
            remote_friendly=data.get("remote_friendly", False),
            remote_us=data.get("remote_us", False),
            funding_stage=FundingStage.UNKNOWN,
            tech_stack=extract_tech_stack(data.get("one_liner", "")),
        )

    def _parse_role(self, data: dict[str, Any], company_name: str) -> RoleResult:
        title = data.get("title", "").strip()
        description = data.get("companyOneLiner", "")
        location = data.get("location", "")
        job_id = data.get("id")
        url = f"https://www.workatastartup.com/jobs/{job_id}" if job_id else ""
        role_type = extract_role_type(title)
        if role_type == RoleType.UNKNOWN:
            role_type = self._map_waas_role_type(data.get("roleType", ""))

        return RoleResult(
            company_name=company_name,
            title=title,
            url=url,
            source=SignalType.YC_JOBS,
            description_raw=description,
            role_type=role_type,
            seniority=extract_seniority(title),
            is_remote=self._job_is_remote(data),
            is_remote_us=self._job_is_remote_us(data),
            location=location,
            external_id=str(job_id or ""),
            tech_stack=extract_tech_stack(description),
            required_skills=extract_tech_stack(description).get("languages", []),
        )

    def _make_role_signal(self, role: RoleResult, company_name: str) -> SignalResult:
        return SignalResult(
            company_name=company_name,
            type=SignalType.YC_JOBS,
            headline=f"{role.title} — {role.location or 'Remote'}",
            detail=f"YC-backed company · Source: Work at a Startup · {role.role_type.value} role",
            source_url=role.url,
            signal_date=datetime.utcnow(),
            score=55.0,  # Base score — will be updated by scoring engine
        )

    def _is_target_job(self, data: dict[str, Any]) -> bool:
        title = (data.get("title") or "").strip()
        role_type = (data.get("roleType") or "").strip().lower()
        job_type = (data.get("jobType") or "").strip().lower()

        if job_type in {"intern", "internship"}:
            return False

        if is_target_role(title):
            return True

        if any(keyword in title.lower() for keyword in (
            "founding engineer",
            "founding full stack",
            "founding ai engineer",
            "founding backend",
            "platform engineer",
            "reliability engineer",
            "software engineer",
        )):
            return True

        return role_type in self.TARGET_ROLE_TYPES

    def _job_is_remote(self, data: dict[str, Any]) -> bool:
        location = (data.get("location") or "").lower()
        return any(keyword in location for keyword in ("remote", "anywhere", "worldwide"))

    def _job_is_remote_us(self, data: dict[str, Any]) -> bool:
        location = (data.get("location") or "").lower()
        return "remote" in location and any(
            keyword in location for keyword in ("us", "united states", "america")
        )

    def _map_waas_role_type(self, role_type: str) -> RoleType:
        normalized = role_type.strip().lower()
        mapping = {
            "backend": RoleType.BACKEND,
            "full stack": RoleType.FULLSTACK,
            "frontend": RoleType.FRONTEND,
            "machine learning": RoleType.AI_ML,
            "data science": RoleType.DATA,
            "devops": RoleType.INFRA,
            "engineering manager": RoleType.PLATFORM,
            "android": RoleType.MOBILE,
            "ios": RoleType.MOBILE,
        }
        return mapping.get(normalized, RoleType.UNKNOWN)

    def _parse_funding_stage(self, stage_str: str) -> FundingStage:
        s = stage_str.lower()
        if "seed" in s:
            return FundingStage.SEED
        if "series a" in s:
            return FundingStage.SERIES_A
        if "series b" in s:
            return FundingStage.SERIES_B
        if "series c" in s:
            return FundingStage.SERIES_C
        if "public" in s or "ipo" in s:
            return FundingStage.PUBLIC
        return FundingStage.UNKNOWN
