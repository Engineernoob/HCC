"""
Base classes for all ingestion adapters.

Every adapter:
  1. Fetches raw data from a source
  2. Normalizes it into SignalResult / RoleResult objects
  3. Upserts companies, signals, and roles into the database
  4. Logs the run in ingest_runs

Adapters are async and use httpx for HTTP.
"""

import hashlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from hirectl.config import settings
from hirectl.db.models import FundingStage, RoleType, SignalType

logger = logging.getLogger(__name__)


# ─── Result types (plain dataclasses, not ORM models) ─────────────

@dataclass
class CompanyResult:
    """Normalized company data from any source."""
    name: str
    website: str = ""
    career_page_url: str = ""
    github_org: str = ""
    description: str = ""
    funding_stage: FundingStage = FundingStage.UNKNOWN
    funding_amount_usd: Optional[float] = None
    last_funding_date: Optional[datetime] = None
    hq_city: str = ""
    hq_country: str = "United States"
    remote_friendly: bool = False
    remote_us: bool = False
    headcount: Optional[int] = None
    tech_stack: dict = field(default_factory=dict)
    investors: list[str] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return (
            self.name.lower()
            .replace(" ", "-")
            .replace(".", "-")
            .replace(",", "")
            .strip("-")
        )


@dataclass
class SignalResult:
    """A single hiring-relevant event."""
    company_name: str
    type: SignalType
    headline: str
    detail: str = ""
    source_url: str = ""
    raw_content: str = ""
    signal_date: datetime = field(default_factory=datetime.utcnow)
    score: float = 0.0

    # Type-specific
    funding_amount_usd: Optional[float] = None
    funding_round: Optional[str] = None
    github_commit_count: Optional[int] = None
    github_repo_name: Optional[str] = None
    poster_handle: Optional[str] = None

    @property
    def dedup_key(self) -> str:
        """Fingerprint for deduplication — prevents re-inserting the same signal."""
        raw = f"{self.company_name}:{self.type.value}:{self.source_url}:{self.signal_date.date()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class RoleResult:
    """A normalized job posting."""
    company_name: str
    title: str
    url: str
    source: SignalType
    description_raw: str = ""
    role_type: RoleType = RoleType.UNKNOWN
    seniority: str = "unknown"
    is_remote: bool = False
    is_remote_us: bool = False
    location: str = ""
    external_id: str = ""
    tech_stack: dict = field(default_factory=dict)
    required_skills: list[str] = field(default_factory=list)

    @property
    def dedup_key(self) -> str:
        """URL is the canonical dedup key for roles."""
        return hashlib.sha256(self.url.encode()).hexdigest()[:16]


# ─── Ingestion result bundle ───────────────────────────────────────

@dataclass
class IngestResult:
    source: str
    companies: list[CompanyResult] = field(default_factory=list)
    signals: list[SignalResult] = field(default_factory=list)
    roles: list[RoleResult] = field(default_factory=list)
    error: Optional[str] = None
    duration_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def total_records(self) -> int:
        return len(self.companies) + len(self.signals) + len(self.roles)


# ─── HTTP client helper ────────────────────────────────────────────

def make_client(timeout: float | None = None) -> httpx.AsyncClient:
    """Create a shared async HTTP client with sensible defaults."""
    return httpx.AsyncClient(
        timeout=timeout or settings.http_timeout_seconds,
        limits=httpx.Limits(
            max_connections=settings.http_max_connections,
            max_keepalive_connections=settings.http_max_keepalive_connections,
            keepalive_expiry=30.0,
        ),
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/json,*/*",
            "Accept-Language": "en-US,en;q=0.9",
        },
        follow_redirects=True,
    )


# ─── Base adapter ─────────────────────────────────────────────────

class BaseIngestionAdapter(ABC):
    """
    Abstract base for all ingestion adapters.

    Subclasses implement `fetch()` which returns an IngestResult.
    The scheduler calls `run()` which wraps fetch with logging + timing.
    """

    source_name: str = "unknown"

    def __init__(self) -> None:
        self.logger = logging.getLogger(f"hirectl.ingestion.{self.source_name}")
        self._client: Optional[httpx.AsyncClient] = None

    @abstractmethod
    async def fetch(self) -> IngestResult:
        """Fetch and normalize data from the source."""
        ...

    async def run(self) -> IngestResult:
        """Execute the adapter with timing, error handling, and logging."""
        start = datetime.utcnow()
        self.logger.info(f"Starting ingest: {self.source_name}")

        try:
            self._client = make_client()
            result = await self.fetch()
        except Exception as exc:
            self.logger.error(f"Ingest failed: {self.source_name}: {exc}", exc_info=True)
            result = IngestResult(source=self.source_name, error=str(exc))
        finally:
            if self._client is not None:
                await self._client.aclose()
                self._client = None

        result.duration_seconds = (datetime.utcnow() - start).total_seconds()
        self.logger.info(
            f"Ingest complete: {self.source_name} — "
            f"{result.total_records} records in {result.duration_seconds:.1f}s"
        )
        return result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Retry-wrapped GET request."""
        if self._client is not None:
            response = await self._client.get(url, **kwargs)
            response.raise_for_status()
            return response

        async with make_client() as client:
            response = await client.get(url, **kwargs)
            response.raise_for_status()
            return response

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _post(self, url: str, **kwargs: Any) -> httpx.Response:
        """Retry-wrapped POST request."""
        if self._client is not None:
            response = await self._client.post(url, **kwargs)
            response.raise_for_status()
            return response

        async with make_client() as client:
            response = await client.post(url, **kwargs)
            response.raise_for_status()
            return response


# ─── Text utilities for all adapters ──────────────────────────────

def extract_role_type(title: str) -> RoleType:
    """Classify a job title into a RoleType."""
    t = title.lower()
    if any(k in t for k in ("machine learning", "ml engineer", "ai engineer", "llm", "applied ai")):
        return RoleType.AI_ML
    if any(k in t for k in ("infrastructure", "infra", "sre", "reliability", "devops", "platform")):
        return RoleType.INFRA
    if any(k in t for k in ("distributed", "systems engineer", "storage", "database")):
        return RoleType.DISTRIBUTED
    if any(k in t for k in ("full stack", "fullstack", "full-stack")):
        return RoleType.FULLSTACK
    if any(k in t for k in ("backend", "back-end", "back end", "server", "api")):
        return RoleType.BACKEND
    if any(k in t for k in ("frontend", "front-end", "react", "vue", "ui engineer")):
        return RoleType.FRONTEND
    if "software engineer" in t or "software developer" in t:
        return RoleType.BACKEND  # default SWE → backend
    return RoleType.UNKNOWN


def extract_seniority(title: str) -> str:
    """Extract seniority level from a job title."""
    t = title.lower()
    if any(k in t for k in ("principal", "distinguished", "fellow")):
        return "principal"
    if any(k in t for k in ("staff", "architect")):
        return "staff"
    if "lead" in t:
        return "lead"
    if "senior" in t or " sr " in t or t.startswith("sr "):
        return "senior"
    if any(k in t for k in ("junior", " jr ", "associate", "entry")):
        return "junior"
    return "mid"


def extract_tech_stack(text: str) -> dict[str, list[str]]:
    """
    Extract tech stack signals from job description text.
    Returns categorized lists of languages, frameworks, and infra tools.
    """
    text_lower = text.lower()

    languages = [
        lang for lang in [
            "go", "golang", "rust", "python", "typescript", "javascript",
            "java", "kotlin", "scala", "c++", "ruby", "elixir", "swift",
        ]
        if lang in text_lower
    ]

    frameworks = [
        fw for fw in [
            "fastapi", "django", "flask", "gin", "axum", "actix", "rails",
            "spring", "grpc", "graphql", "rest", "trpc", "nextjs", "react",
        ]
        if fw in text_lower
    ]

    infra = [
        tool for tool in [
            "kubernetes", "k8s", "docker", "terraform", "aws", "gcp", "azure",
            "postgres", "postgresql", "mysql", "redis", "kafka", "rabbitmq",
            "elasticsearch", "clickhouse", "s3", "lambda", "firecracker",
            "wasm", "webassembly", "cuda", "triton", "ray", "spark",
        ]
        if tool in text_lower
    ]

    return {
        "languages": languages,
        "frameworks": frameworks,
        "infra": infra,
    }


def is_target_role(title: str) -> bool:
    """Return True if the role title is a target engineering role."""
    t = title.lower()
    target_keywords = [
        "software engineer", "backend engineer", "backend developer",
        "full stack", "fullstack", "full-stack",
        "infrastructure engineer", "platform engineer",
        "distributed systems", "systems engineer",
        "ai engineer", "ml engineer", "machine learning",
        "applied ai", "llm engineer",
        "site reliability", "sre",
    ]
    return any(k in t for k in target_keywords)
