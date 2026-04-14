"""
SQLAlchemy ORM models for HIRE INTEL.
All tables use UUIDs as primary keys.
"""

import uuid
from datetime import date, datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey,
    Integer, String, Text, JSON, Enum, Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ─── Enums ───────────────────────────────────────────────────────

class UrgencyLevel(PyEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FundingStage(PyEnum):
    SEED = "seed"
    SERIES_A = "series_a"
    SERIES_B = "series_b"
    SERIES_C = "series_c"
    SERIES_D_PLUS = "series_d_plus"
    PUBLIC = "public"
    UNKNOWN = "unknown"


class SignalType(PyEnum):
    FUNDING = "funding"
    FOUNDER_POST = "founder_post"
    ATS_GREENHOUSE = "ats_greenhouse"
    ATS_LEVER = "ats_lever"
    ATS_ASHBY = "ats_ashby"
    CAREER_PAGE = "career_page"
    GITHUB_SPIKE = "github_spike"
    BLOG_POST = "blog_post"
    NEWS = "news"
    YC_JOBS = "yc_jobs"
    WELLFOUND = "wellfound"


class RoleType(PyEnum):
    BACKEND = "backend"
    FULLSTACK = "fullstack"
    AI_ML = "ai_ml"
    INFRA = "infra"
    PLATFORM = "platform"
    DISTRIBUTED = "distributed"
    FRONTEND = "frontend"
    MOBILE = "mobile"
    DATA = "data"
    UNKNOWN = "unknown"


class OutreachStatus(PyEnum):
    IDENTIFIED = "identified"
    DRAFTED = "drafted"
    SENT = "sent"
    RESPONDED = "responded"
    SCREENING = "screening"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    CLOSED = "closed"


class ExecutionStatus(PyEnum):
    TRACKING = "tracking"
    REACHED_OUT = "reached_out"
    APPLIED = "applied"
    FOLLOW_UP = "follow_up"
    INTERVIEW = "interview"
    OFFER = "offer"
    CLOSED = "closed"


# ─── Core models ─────────────────────────────────────────────────

class Company(Base):
    """Canonical company record — deduplicated across all sources."""
    __tablename__ = "companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True, index=True)
    slug = Column(String(255), nullable=False, unique=True, index=True)

    # Metadata
    website = Column(String(512))
    career_page_url = Column(String(512))
    linkedin_url = Column(String(512))
    github_org = Column(String(255))
    description = Column(Text)
    tagline = Column(String(512))

    # Funding
    funding_stage = Column(Enum(FundingStage), default=FundingStage.UNKNOWN)
    funding_amount_usd = Column(Float)
    last_funding_date = Column(DateTime)
    investors = Column(JSON, default=list)

    # Team
    headcount = Column(Integer)
    headcount_updated_at = Column(DateTime)
    engineering_headcount = Column(Integer)
    founded_year = Column(Integer)

    # Location
    hq_city = Column(String(255))
    hq_country = Column(String(255), default="United States")
    remote_friendly = Column(Boolean, default=False)
    remote_us = Column(Boolean, default=False)

    # Tech stack (inferred from JDs + GitHub)
    tech_stack = Column(JSON, default=dict)  # {languages: [], frameworks: [], infra: []}

    # Scores (recomputed on each signal)
    fit_score = Column(Float, default=0.0)
    urgency_score = Column(Float, default=0.0)
    composite_score = Column(Float, default=0.0, index=True)

    # AI content
    ai_brief = Column(Text)
    ai_brief_generated_at = Column(DateTime)
    outreach_angle = Column(Text)

    # Watchlist
    on_watchlist = Column(Boolean, default=False, index=True)
    watchlist_added_at = Column(DateTime)
    watchlist_priority = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_signal_at = Column(DateTime)

    # Relationships
    signals = relationship("Signal", back_populates="company", cascade="all, delete-orphan")
    roles = relationship("Role", back_populates="company", cascade="all, delete-orphan")
    outreach = relationship("OutreachRecord", back_populates="company", cascade="all, delete-orphan")
    execution = relationship("ExecutionRecord", back_populates="company", uselist=False, cascade="all, delete-orphan")
    funding_history = relationship(
        "CompanyFundingHistory", back_populates="company", cascade="all, delete-orphan"
    )
    role_daily = relationship(
        "CompanyRoleDaily", back_populates="company", cascade="all, delete-orphan"
    )
    feature_snapshots = relationship(
        "CompanyFeatureSnapshot", back_populates="company", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Company {self.name} score={self.composite_score:.1f}>"

    @property
    def urgency(self) -> UrgencyLevel:
        if self.urgency_score >= 80:
            return UrgencyLevel.CRITICAL
        if self.urgency_score >= 60:
            return UrgencyLevel.HIGH
        if self.urgency_score >= 35:
            return UrgencyLevel.MEDIUM
        return UrgencyLevel.LOW

class Signal(Base):
    """A single hiring-relevant event for a company."""
    __tablename__ = "signals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)

    type = Column(Enum(SignalType), nullable=False, index=True)
    source_url = Column(String(2048))
    raw_content = Column(Text)

    # Parsed fields
    headline = Column(String(512))
    detail = Column(Text)
    score = Column(Float, default=0.0, index=True)

    # Type-specific metadata
    funding_amount_usd = Column(Float)
    funding_round = Column(String(64))
    github_commit_count = Column(Integer)
    github_repo_name = Column(String(255))
    poster_handle = Column(String(255))  # X/LinkedIn handle for founder posts

    # Timestamps
    signal_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    ingested_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    company = relationship("Company", back_populates="signals")

    def __repr__(self) -> str:
        return f"<Signal {self.type.value} company={self.company_id} score={self.score}>"

    __table_args__ = (
        Index("ix_signals_company_date", "company_id", "signal_date"),
        Index("ix_signals_type_date", "type", "signal_date"),
    )


class Role(Base):
    """An individual job posting scraped from any source."""
    __tablename__ = "roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)

    # Basic info
    title = Column(String(512), nullable=False)
    url = Column(String(2048), nullable=False, unique=True)
    source = Column(Enum(SignalType))
    external_id = Column(String(255))  # ATS job ID

    # Classification
    role_type = Column(Enum(RoleType), default=RoleType.UNKNOWN, index=True)
    seniority = Column(String(64))  # "senior", "mid", "lead", "staff", "principal"
    is_remote = Column(Boolean, default=False, index=True)
    is_remote_us = Column(Boolean, default=False)
    location = Column(String(255))

    # Content
    description_raw = Column(Text)
    description_clean = Column(Text)  # stripped HTML

    # Extracted data
    tech_stack = Column(JSON, default=dict)
    required_skills = Column(JSON, default=list)
    preferred_skills = Column(JSON, default=list)
    salary_min = Column(Integer)
    salary_max = Column(Integer)

    # Scoring
    fit_score = Column(Float, default=0.0)
    fit_breakdown = Column(JSON, default=dict)

    # Status
    is_active = Column(Boolean, default=True, index=True)
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    removed_at = Column(DateTime)
    days_open = Column(Integer, default=0)

    # Relationship
    company = relationship("Company", back_populates="roles")

    def __repr__(self) -> str:
        return f"<Role {self.title!r} @ {self.company_id}>"

    __table_args__ = (
        Index("ix_roles_company_active", "company_id", "is_active"),
        Index("ix_roles_type_remote", "role_type", "is_remote"),
        Index("ix_roles_fit_score", "fit_score"),
    )


class OutreachRecord(Base):
    """CRM record for a contact attempt at a company."""
    __tablename__ = "outreach"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)

    # Contact
    contact_name = Column(String(255))
    contact_role = Column(String(255))  # "Founder", "VP Eng", "Recruiter"
    contact_linkedin = Column(String(512))
    contact_twitter = Column(String(255))
    contact_email = Column(String(255))

    # Message
    draft = Column(Text)
    sent_message = Column(Text)
    subject_line = Column(String(512))

    # Status tracking
    status = Column(Enum(OutreachStatus), default=OutreachStatus.IDENTIFIED, index=True)
    sent_at = Column(DateTime)
    responded_at = Column(DateTime)
    follow_up_due = Column(DateTime)
    notes = Column(Text)

    # Context
    trigger_signal_id = Column(UUID(as_uuid=True), ForeignKey("signals.id"))
    outreach_angle = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("Company", back_populates="outreach")

    def __repr__(self) -> str:
        return f"<Outreach {self.company_id} status={self.status.value}>"


class ExecutionRecord(Base):
    """Operator execution ledger for a company."""
    __tablename__ = "execution_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, unique=True, index=True)

    status = Column(Enum(ExecutionStatus), default=ExecutionStatus.TRACKING, index=True)
    notes = Column(Text)
    target_role_title = Column(String(512))
    target_role_url = Column(String(2048))
    follow_up_due = Column(DateTime)
    last_event_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("Company", back_populates="execution")
    events = relationship("ExecutionEvent", back_populates="execution", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ExecutionRecord {self.company_id} status={self.status.value}>"


class ExecutionEvent(Base):
    """Immutable event log for operator actions."""
    __tablename__ = "execution_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_id = Column(UUID(as_uuid=True), ForeignKey("execution_records.id"), nullable=False, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)

    status = Column(Enum(ExecutionStatus), nullable=False, index=True)
    label = Column(String(255))
    notes = Column(Text)
    target_role_title = Column(String(512))
    target_role_url = Column(String(2048))
    follow_up_due = Column(DateTime)
    occurred_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    execution = relationship("ExecutionRecord", back_populates="events")

    __table_args__ = (
        Index("ix_execution_events_company_date", "company_id", "occurred_at"),
    )


class UserProfile(Base):
    """Your engineering profile — used for scoring and AI personalization."""
    __tablename__ = "user_profile"

    id = Column(Integer, primary_key=True, default=1)  # single row

    # Skills
    primary_skills = Column(JSON, default=list)    # ["Go", "Python", "Rust"]
    secondary_skills = Column(JSON, default=list)  # ["TypeScript", "SQL"]
    domains = Column(JSON, default=list)           # ["distributed", "ai_ml", "backend"]

    # Preferences
    preferred_stages = Column(JSON, default=list)  # ["seed", "series_a", "series_b"]
    preferred_remote = Column(Boolean, default=True)
    preferred_locations = Column(JSON, default=list)
    target_seniority = Column(JSON, default=list)  # ["senior", "staff"]

    # Context (used in AI brief/outreach prompts)
    bio_summary = Column(Text)
    notable_projects = Column(Text)
    github_handle = Column(String(255))
    linkedin_url = Column(String(512))

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class IngestRun(Base):
    """Log of every ingestion run — for debugging and rate limiting."""
    __tablename__ = "ingest_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String(64), nullable=False, index=True)
    status = Column(String(32), default="running")  # running | success | error
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    records_found = Column(Integer, default=0)
    records_new = Column(Integer, default=0)
    error_message = Column(Text)

    __table_args__ = (
        Index("ix_ingest_source_date", "source", "started_at"),
    )


class CareerPageSnapshotRecord(Base):
    """Latest persisted career-page snapshot per company."""
    __tablename__ = "career_page_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_name = Column(String(255), nullable=False, unique=True, index=True)
    page_url = Column(String(2048), nullable=False)
    page_hash = Column(String(64), nullable=False, index=True)
    job_fingerprints = Column(JSON, default=dict)
    raw_jobs = Column(JSON, default=list)
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<CareerPageSnapshotRecord {self.company_name} hash={self.page_hash}>"


class CompanyFundingHistory(Base):
    """Historical funding events for point-in-time modeling."""
    __tablename__ = "company_funding_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    announced_at = Column(DateTime, nullable=False, index=True)
    round_type = Column(String(64))
    amount_usd = Column(Float)
    lead_investors = Column(JSON, default=list)
    source = Column(String(64), nullable=False)
    source_url = Column(String(2048))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    company = relationship("Company", back_populates="funding_history")

    __table_args__ = (
        Index("ix_company_funding_history_company_date", "company_id", "announced_at"),
    )


class CompanyRoleDaily(Base):
    """Daily role-state rollup used for historical analysis and model features."""
    __tablename__ = "company_role_daily"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    as_of_date = Column(Date, nullable=False, index=True)
    active_roles_total = Column(Integer, default=0, nullable=False)
    active_remote_roles_total = Column(Integer, default=0, nullable=False)
    new_roles_7d = Column(Integer, default=0, nullable=False)
    new_roles_30d = Column(Integer, default=0, nullable=False)
    removed_roles_30d = Column(Integer, default=0, nullable=False)
    role_type_counts = Column(JSON, default=dict)
    source_counts = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("Company", back_populates="role_daily")

    __table_args__ = (
        Index("ix_company_role_daily_company_date", "company_id", "as_of_date"),
        Index("ix_company_role_daily_unique", "company_id", "as_of_date", unique=True),
    )


class CompanyFeatureSnapshot(Base):
    """Point-in-time feature payloads for downstream model training."""
    __tablename__ = "company_feature_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    as_of_date = Column(Date, nullable=False, index=True)
    feature_version = Column(String(32), nullable=False, default="v1")
    features = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("Company", back_populates="feature_snapshots")

    __table_args__ = (
        Index("ix_company_feature_snapshots_company_date", "company_id", "as_of_date"),
        Index(
            "ix_company_feature_snapshots_unique",
            "company_id",
            "as_of_date",
            "feature_version",
            unique=True,
        ),
    )
