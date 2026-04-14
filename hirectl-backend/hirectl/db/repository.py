"""
Repository layer — all database queries live here.

Keeps query logic out of the API and ingestion layers.
Every method is async. Returns domain objects, not raw ORM rows.

Pattern: one Repository class per major entity.
"""

import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, asc, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hirectl.db.models import (
    Company, Signal, Role, OutreachRecord, UserProfile,
    IngestRun, FundingStage, SignalType, RoleType, OutreachStatus, ExecutionStatus,
    ExecutionRecord, ExecutionEvent,
    CompanyFundingHistory, CompanyRoleDaily, CompanyFeatureSnapshot,
)
from hirectl.ingestion.base import CompanyResult, SignalResult, RoleResult

logger = logging.getLogger(__name__)


def _normalize_db_datetime(value: Optional[datetime]) -> Optional[datetime]:
    """Convert aware datetimes to naive UTC for TIMESTAMP WITHOUT TIME ZONE columns."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


# ─── Company Repository ───────────────────────────────────────────

class CompanyRepo:
    def __init__(self, session: AsyncSession):
        self.db = session

    async def upsert(self, data: CompanyResult) -> Company:
        """
        Insert or update a company by slug.
        On conflict: update non-null fields only (don't overwrite good data with empty).
        """
        stmt = select(Company).where(Company.slug == data.slug)
        result = await self.db.execute(stmt)
        company = result.scalar_one_or_none()

        if company is None:
            company = Company(
                name=data.name,
                slug=data.slug,
                website=data.website or None,
                career_page_url=data.career_page_url or None,
                github_org=data.github_org or None,
                description=data.description or None,
                funding_stage=data.funding_stage,
                funding_amount_usd=data.funding_amount_usd,
                last_funding_date=data.last_funding_date,
                hq_city=data.hq_city or None,
                hq_country=data.hq_country or "United States",
                remote_friendly=data.remote_friendly,
                remote_us=data.remote_us,
                headcount=data.headcount,
                tech_stack=data.tech_stack,
                investors=data.investors,
            )
            self.db.add(company)
        else:
            # Update only non-null incoming fields
            if data.website:
                company.website = data.website
            if data.career_page_url:
                company.career_page_url = data.career_page_url
            if data.github_org:
                company.github_org = data.github_org
            if data.description:
                company.description = data.description
            if data.funding_stage != FundingStage.UNKNOWN:
                company.funding_stage = data.funding_stage
            if data.funding_amount_usd:
                company.funding_amount_usd = data.funding_amount_usd
            if data.last_funding_date:
                company.last_funding_date = data.last_funding_date
            if data.headcount:
                company.headcount = data.headcount
            if data.tech_stack:
                # Merge stacks rather than overwrite
                existing = company.tech_stack or {}
                for key, vals in data.tech_stack.items():
                    existing_vals = existing.get(key, [])
                    merged = list(set(existing_vals + vals))
                    existing[key] = merged
                company.tech_stack = existing
            if data.remote_us:
                company.remote_us = True
            if data.remote_friendly:
                company.remote_friendly = True

            company.updated_at = datetime.utcnow()

        await self.db.flush()
        return company

    async def get_by_id(self, company_id: UUID) -> Optional[Company]:
        stmt = (
            select(Company)
            .where(Company.id == company_id)
            .options(
                selectinload(Company.signals),
                selectinload(Company.roles),
                selectinload(Company.outreach),
                selectinload(Company.execution),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[Company]:
        stmt = select(Company).where(Company.slug == slug)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Company]:
        # Case-insensitive name lookup
        stmt = select(Company).where(
            func.lower(Company.name) == name.lower()
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_ranked(
        self,
        stage: Optional[str] = None,
        remote_us: Optional[bool] = None,
        min_score: float = 0.0,
        role_type: Optional[str] = None,
        watchlist_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Company]:
        """Return companies ranked by composite_score descending."""
        stmt = select(Company).where(Company.composite_score >= min_score)

        if stage:
            try:
                stmt = stmt.where(Company.funding_stage == FundingStage(stage))
            except ValueError:
                pass

        if remote_us is not None:
            stmt = stmt.where(Company.remote_us == remote_us)

        if watchlist_only:
            stmt = stmt.where(Company.on_watchlist == True)

        # Role type filter requires a join to roles
        if role_type:
            try:
                rt = RoleType(role_type)
                stmt = stmt.join(
                    Role,
                    and_(Role.company_id == Company.id, Role.role_type == rt, Role.is_active == True),
                )
            except ValueError:
                pass

        stmt = stmt.order_by(desc(Company.composite_score)).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_scores(
        self,
        company_id: UUID,
        fit_score: float,
        urgency_score: float,
        composite_score: float,
        ai_brief: Optional[str] = None,
        outreach_angle: Optional[str] = None,
    ) -> None:
        values: dict = {
            "fit_score": fit_score,
            "urgency_score": urgency_score,
            "composite_score": composite_score,
            "updated_at": datetime.utcnow(),
        }
        if ai_brief:
            values["ai_brief"] = ai_brief
            values["ai_brief_generated_at"] = datetime.utcnow()
        if outreach_angle:
            values["outreach_angle"] = outreach_angle

        stmt = update(Company).where(Company.id == company_id).values(**values)
        await self.db.execute(stmt)

    async def set_watchlist(self, company_id: UUID, on_watchlist: bool) -> None:
        values: dict = {"on_watchlist": on_watchlist, "updated_at": datetime.utcnow()}
        if on_watchlist:
            values["watchlist_added_at"] = datetime.utcnow()
        else:
            values["watchlist_priority"] = 0
        stmt = update(Company).where(Company.id == company_id).values(**values)
        await self.db.execute(stmt)

    async def set_watchlist_priority(self, company_id: UUID, priority: int) -> None:
        stmt = (
            update(Company)
            .where(Company.id == company_id)
            .values(
                watchlist_priority=priority,
                updated_at=datetime.utcnow(),
            )
        )
        await self.db.execute(stmt)

    async def count(self) -> int:
        result = await self.db.execute(select(func.count(Company.id)))
        return result.scalar_one()

    async def count_watchlist(self) -> int:
        result = await self.db.execute(
            select(func.count(Company.id)).where(Company.on_watchlist == True)
        )
        return result.scalar_one()

    async def list_brief_candidates(
        self,
        *,
        min_score: float,
        max_age_hours: int,
        limit: int,
    ) -> list[Company]:
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        stmt = (
            select(Company)
            .where(Company.composite_score >= min_score)
            .where(
                (Company.ai_brief.is_(None)) |
                (Company.ai_brief_generated_at.is_(None)) |
                (Company.ai_brief_generated_at < cutoff)
            )
            .options(
                selectinload(Company.signals),
                selectinload(Company.roles),
            )
            .order_by(desc(Company.composite_score), desc(Company.last_signal_at))
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())


# ─── Signal Repository ────────────────────────────────────────────

class SignalRepo:
    def __init__(self, session: AsyncSession):
        self.db = session

    async def upsert(self, company_id: UUID, data: SignalResult) -> Optional[Signal]:
        """
        Insert signal, skipping duplicates by dedup_key.
        We store dedup_key in raw_content prefix for now.
        """
        # Check for existing signal with same dedup key
        dedup_key = data.dedup_key
        stmt = select(Signal).where(
            and_(
                Signal.company_id == company_id,
                Signal.raw_content.like(f"DEDUP:{dedup_key}%"),
            )
        )
        existing = await self.db.execute(stmt)
        if existing.scalar_one_or_none():
            return None  # Already ingested

        signal_date = _normalize_db_datetime(data.signal_date) or datetime.utcnow()

        signal = Signal(
            company_id=company_id,
            type=data.type,
            source_url=data.source_url or None,
            raw_content=f"DEDUP:{dedup_key}\n{data.raw_content}",
            headline=data.headline[:512] if data.headline else None,
            detail=data.detail[:2000] if data.detail else None,
            score=data.score,
            funding_amount_usd=data.funding_amount_usd,
            funding_round=data.funding_round,
            github_commit_count=data.github_commit_count,
            github_repo_name=data.github_repo_name,
            poster_handle=data.poster_handle,
            signal_date=signal_date,
            ingested_at=datetime.utcnow(),
        )
        self.db.add(signal)
        await self.db.flush()
        return signal

    async def list_recent(
        self,
        company_id: Optional[UUID] = None,
        signal_type: Optional[str] = None,
        min_score: float = 0.0,
        hours: int = 24 * 7,
        limit: int = 50,
    ) -> list[Signal]:
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        stmt = select(Signal).where(and_(Signal.signal_date >= cutoff, Signal.score >= min_score))

        if company_id:
            stmt = stmt.where(Signal.company_id == company_id)

        if signal_type:
            try:
                stmt = stmt.where(Signal.type == SignalType(signal_type))
            except ValueError:
                pass

        stmt = stmt.order_by(desc(Signal.score), desc(Signal.signal_date)).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_for_company(self, company_id: UUID) -> Optional[Signal]:
        stmt = (
            select(Signal)
            .where(Signal.company_id == company_id)
            .order_by(desc(Signal.signal_date))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def count_last_24h(self) -> int:
        cutoff = datetime.utcnow() - timedelta(hours=24)
        result = await self.db.execute(
            select(func.count(Signal.id)).where(Signal.ingested_at >= cutoff)
        )
        return result.scalar_one()

    async def count_total(self) -> int:
        result = await self.db.execute(select(func.count(Signal.id)))
        return result.scalar_one()

    async def get_funding_signals(
        self, days: int = 30
    ) -> list[Signal]:
        """Get recent funding signals for urgency scoring."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        stmt = (
            select(Signal)
            .where(
                and_(
                    Signal.type == SignalType.FUNDING,
                    Signal.signal_date >= cutoff,
                )
            )
            .order_by(desc(Signal.signal_date))
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_founder_post_signals(self, days: int = 14) -> list[Signal]:
        cutoff = datetime.utcnow() - timedelta(days=days)
        stmt = (
            select(Signal)
            .where(
                and_(
                    Signal.type == SignalType.FOUNDER_POST,
                    Signal.signal_date >= cutoff,
                )
            )
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())


# ─── Historical Analytics Repositories ───────────────────────────

class FundingHistoryRepo:
    def __init__(self, session: AsyncSession):
        self.db = session

    async def record_event(
        self,
        company_id: UUID,
        announced_at: datetime,
        round_type: str,
        amount_usd: Optional[float],
        source: str,
        source_url: str = "",
        lead_investors: Optional[list[str]] = None,
    ) -> CompanyFundingHistory:
        announced_at = _normalize_db_datetime(announced_at) or datetime.utcnow()
        stmt = select(CompanyFundingHistory).where(
            and_(
                CompanyFundingHistory.company_id == company_id,
                CompanyFundingHistory.announced_at == announced_at,
                CompanyFundingHistory.round_type == (round_type or None),
                CompanyFundingHistory.amount_usd == amount_usd,
                CompanyFundingHistory.source == source,
            )
        )
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()

        if record is None:
            record = CompanyFundingHistory(
                company_id=company_id,
                announced_at=announced_at,
                round_type=round_type or None,
                amount_usd=amount_usd,
                lead_investors=lead_investors or [],
                source=source,
                source_url=source_url or None,
            )
            self.db.add(record)
        else:
            record.source_url = source_url or record.source_url
            record.lead_investors = lead_investors or record.lead_investors

        await self.db.flush()
        return record

    async def list_before(self, company_id: UUID, as_of_date: date) -> list[CompanyFundingHistory]:
        cutoff = datetime.combine(as_of_date, time.max)
        stmt = (
            select(CompanyFundingHistory)
            .where(
                and_(
                    CompanyFundingHistory.company_id == company_id,
                    CompanyFundingHistory.announced_at <= cutoff,
                )
            )
            .order_by(desc(CompanyFundingHistory.announced_at))
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())


# ─── Role Repository ──────────────────────────────────────────────

class RoleRepo:
    def __init__(self, session: AsyncSession):
        self.db = session

    async def upsert(self, company_id: UUID, data: RoleResult) -> tuple[Role, bool]:
        """
        Insert or update a role by URL (canonical dedup key).
        Returns (role, is_new).
        """
        stmt = select(Role).where(Role.url == data.url)
        result = await self.db.execute(stmt)
        role = result.scalar_one_or_none()
        is_new = role is None

        if role is None:
            role = Role(
                company_id=company_id,
                title=data.title,
                url=data.url,
                source=data.source,
                external_id=data.external_id or None,
                role_type=data.role_type,
                seniority=data.seniority,
                is_remote=data.is_remote,
                is_remote_us=data.is_remote_us,
                location=data.location or None,
                description_raw=data.description_raw[:10000] if data.description_raw else None,
                tech_stack=data.tech_stack,
                required_skills=data.required_skills,
                is_active=True,
                first_seen_at=datetime.utcnow(),
                last_seen_at=datetime.utcnow(),
            )
            self.db.add(role)
        else:
            role.title = data.title
            role.source = data.source
            role.external_id = data.external_id or role.external_id
            role.role_type = data.role_type
            role.seniority = data.seniority
            role.is_remote = data.is_remote
            role.is_remote_us = data.is_remote_us
            role.location = data.location or role.location
            role.description_raw = (
                data.description_raw[:10000] if data.description_raw else role.description_raw
            )
            role.tech_stack = data.tech_stack
            role.required_skills = data.required_skills
            role.last_seen_at = datetime.utcnow()
            role.is_active = True
            role.removed_at = None
            # Update days_open
            role.days_open = (datetime.utcnow() - role.first_seen_at).days

        await self.db.flush()
        return role, is_new

    async def mark_inactive(
        self,
        company_id: UUID,
        active_urls: set[str],
        source: Optional[SignalType] = None,
    ) -> int:
        """Mark roles not in active_urls as inactive for the selected company/source."""
        conditions = [
            Role.company_id == company_id,
            Role.is_active == True,
        ]
        if source is not None:
            conditions.append(Role.source == source)
        if active_urls:
            conditions.append(Role.url.not_in(active_urls))

        stmt = (
            update(Role)
            .where(and_(*conditions))
            .values(is_active=False, removed_at=datetime.utcnow())
        )
        result = await self.db.execute(stmt)
        return result.rowcount

    async def list_active(
        self,
        company_id: Optional[UUID] = None,
        role_type: Optional[str] = None,
        remote_us: Optional[bool] = None,
        min_fit: float = 0.0,
        limit: int = 50,
    ) -> list[Role]:
        stmt = select(Role).where(Role.is_active == True, Role.fit_score >= min_fit)

        if company_id:
            stmt = stmt.where(Role.company_id == company_id)
        if role_type:
            try:
                stmt = stmt.where(Role.role_type == RoleType(role_type))
            except ValueError:
                pass
        if remote_us is not None:
            stmt = stmt.where(Role.is_remote_us == remote_us)

        stmt = stmt.order_by(desc(Role.fit_score), asc(Role.days_open)).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_fit_score(
        self, role_id: UUID, fit_score: float, fit_breakdown: dict
    ) -> None:
        stmt = (
            update(Role)
            .where(Role.id == role_id)
            .values(fit_score=fit_score, fit_breakdown=fit_breakdown)
        )
        await self.db.execute(stmt)

    async def count_active(self) -> int:
        result = await self.db.execute(
            select(func.count(Role.id)).where(Role.is_active == True)
        )
        return result.scalar_one()

    async def get_avg_days_open(self, company_id: UUID) -> float:
        result = await self.db.execute(
            select(func.avg(Role.days_open)).where(
                and_(Role.company_id == company_id, Role.is_active == True)
            )
        )
        return float(result.scalar_one() or 0)

    async def get_oldest_open_days(self, company_id: UUID) -> int:
        result = await self.db.execute(
            select(func.max(Role.days_open)).where(
                and_(Role.company_id == company_id, Role.is_active == True)
            )
        )
        return int(result.scalar_one() or 0)

    async def list_for_company_as_of(self, company_id: UUID, as_of_date: date) -> list[Role]:
        end_of_day = datetime.combine(as_of_date, time.max)
        stmt = select(Role).where(
            and_(
                Role.company_id == company_id,
                Role.first_seen_at <= end_of_day,
            )
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_future_new_roles(
        self,
        company_id: UUID,
        start_date: date,
        horizon_days: int,
    ) -> int:
        window_start = datetime.combine(start_date + timedelta(days=1), time.min)
        window_end = datetime.combine(start_date + timedelta(days=horizon_days), time.max)
        result = await self.db.execute(
            select(func.count(Role.id)).where(
                and_(
                    Role.company_id == company_id,
                    Role.first_seen_at >= window_start,
                    Role.first_seen_at <= window_end,
                )
            )
        )
        return int(result.scalar_one() or 0)


class RoleDailyRepo:
    def __init__(self, session: AsyncSession):
        self.db = session

    async def upsert(
        self,
        company_id: UUID,
        as_of_date: date,
        *,
        active_roles_total: int,
        active_remote_roles_total: int,
        new_roles_7d: int,
        new_roles_30d: int,
        removed_roles_30d: int,
        role_type_counts: dict,
        source_counts: dict,
    ) -> CompanyRoleDaily:
        stmt = select(CompanyRoleDaily).where(
            and_(
                CompanyRoleDaily.company_id == company_id,
                CompanyRoleDaily.as_of_date == as_of_date,
            )
        )
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()

        if record is None:
            record = CompanyRoleDaily(
                company_id=company_id,
                as_of_date=as_of_date,
                active_roles_total=active_roles_total,
                active_remote_roles_total=active_remote_roles_total,
                new_roles_7d=new_roles_7d,
                new_roles_30d=new_roles_30d,
                removed_roles_30d=removed_roles_30d,
                role_type_counts=role_type_counts,
                source_counts=source_counts,
            )
            self.db.add(record)
        else:
            record.active_roles_total = active_roles_total
            record.active_remote_roles_total = active_remote_roles_total
            record.new_roles_7d = new_roles_7d
            record.new_roles_30d = new_roles_30d
            record.removed_roles_30d = removed_roles_30d
            record.role_type_counts = role_type_counts
            record.source_counts = source_counts
            record.updated_at = datetime.utcnow()

        await self.db.flush()
        return record

    async def list_between(self, start_date: date, end_date: date) -> list[CompanyRoleDaily]:
        stmt = (
            select(CompanyRoleDaily)
            .where(
                and_(
                    CompanyRoleDaily.as_of_date >= start_date,
                    CompanyRoleDaily.as_of_date <= end_date,
                )
            )
            .order_by(asc(CompanyRoleDaily.as_of_date))
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())


class FeatureSnapshotRepo:
    def __init__(self, session: AsyncSession):
        self.db = session

    async def upsert(
        self,
        company_id: UUID,
        as_of_date: date,
        feature_version: str,
        features: dict,
    ) -> CompanyFeatureSnapshot:
        stmt = select(CompanyFeatureSnapshot).where(
            and_(
                CompanyFeatureSnapshot.company_id == company_id,
                CompanyFeatureSnapshot.as_of_date == as_of_date,
                CompanyFeatureSnapshot.feature_version == feature_version,
            )
        )
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()

        if record is None:
            record = CompanyFeatureSnapshot(
                company_id=company_id,
                as_of_date=as_of_date,
                feature_version=feature_version,
                features=features,
            )
            self.db.add(record)
        else:
            record.features = features
            record.updated_at = datetime.utcnow()

        await self.db.flush()
        return record

    async def list_between(
        self,
        start_date: date,
        end_date: date,
        feature_version: str,
    ) -> list[CompanyFeatureSnapshot]:
        stmt = (
            select(CompanyFeatureSnapshot)
            .where(
                and_(
                    CompanyFeatureSnapshot.as_of_date >= start_date,
                    CompanyFeatureSnapshot.as_of_date <= end_date,
                    CompanyFeatureSnapshot.feature_version == feature_version,
                )
            )
            .order_by(asc(CompanyFeatureSnapshot.as_of_date))
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())


# ─── Outreach Repository ──────────────────────────────────────────


class ExecutionRepo:
    def __init__(self, session: AsyncSession):
        self.db = session

    async def get_by_company(self, company_id: UUID) -> Optional[ExecutionRecord]:
        stmt = (
            select(ExecutionRecord)
            .where(ExecutionRecord.company_id == company_id)
            .options(
                selectinload(ExecutionRecord.company),
                selectinload(ExecutionRecord.events),
            )
        )
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()
        if record is None:
            return None
        record.events.sort(key=lambda event: event.occurred_at or datetime.utcnow(), reverse=True)
        return record

    async def list(
        self,
        *,
        company_id: Optional[UUID] = None,
        limit: int = 100,
    ) -> list[ExecutionRecord]:
        stmt = (
            select(ExecutionRecord)
            .options(
                selectinload(ExecutionRecord.company),
                selectinload(ExecutionRecord.events),
            )
            .order_by(desc(ExecutionRecord.updated_at))
            .limit(limit)
        )
        if company_id is not None:
            stmt = stmt.where(ExecutionRecord.company_id == company_id)

        result = await self.db.execute(stmt)
        records = list(result.scalars().unique().all())
        for record in records:
            record.events.sort(key=lambda event: event.occurred_at or datetime.utcnow(), reverse=True)
        return records

    async def upsert(
        self,
        *,
        company_id: UUID,
        status: ExecutionStatus,
        label: str = "",
        notes: str = "",
        target_role_title: str = "",
        target_role_url: str = "",
        follow_up_due: Optional[datetime] = None,
    ) -> ExecutionRecord:
        now = datetime.utcnow()
        stmt = select(ExecutionRecord).where(ExecutionRecord.company_id == company_id)
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()

        if record is None:
            record = ExecutionRecord(
                company_id=company_id,
                status=status,
                notes=notes or None,
                target_role_title=target_role_title or None,
                target_role_url=target_role_url or None,
                follow_up_due=_normalize_db_datetime(follow_up_due),
                last_event_at=now,
            )
            self.db.add(record)
            await self.db.flush()
        else:
            record.status = status
            record.last_event_at = now
            if notes:
                record.notes = notes
            if target_role_title:
                record.target_role_title = target_role_title
            if target_role_url:
                record.target_role_url = target_role_url
            if follow_up_due is not None:
                record.follow_up_due = _normalize_db_datetime(follow_up_due)
            record.updated_at = now
            await self.db.flush()

        event = ExecutionEvent(
            execution_id=record.id,
            company_id=company_id,
            status=status,
            label=label or status.value.replace("_", " "),
            notes=notes or None,
            target_role_title=target_role_title or record.target_role_title,
            target_role_url=target_role_url or record.target_role_url,
            follow_up_due=_normalize_db_datetime(follow_up_due) if follow_up_due is not None else record.follow_up_due,
            occurred_at=now,
        )
        self.db.add(event)
        await self.db.flush()
        return await self.get_by_company(company_id)

    async def count_follow_up_due(self) -> int:
        cutoff = datetime.utcnow()
        result = await self.db.execute(
            select(func.count(ExecutionRecord.id)).where(
                and_(
                    ExecutionRecord.status == ExecutionStatus.FOLLOW_UP,
                    ExecutionRecord.follow_up_due.is_not(None),
                    ExecutionRecord.follow_up_due <= cutoff,
                )
            )
        )
        return result.scalar_one()


# ─── Outreach Repository ──────────────────────────────────────────

class OutreachRepo:
    def __init__(self, session: AsyncSession):
        self.db = session

    async def create(
        self,
        company_id: UUID,
        draft: str,
        contact_role: str = "",
        contact_name: str = "",
        outreach_angle: str = "",
        trigger_signal_id: Optional[UUID] = None,
        follow_up_due: Optional[datetime] = None,
    ) -> OutreachRecord:
        record = OutreachRecord(
            company_id=company_id,
            draft=draft,
            contact_role=contact_role,
            contact_name=contact_name,
            outreach_angle=outreach_angle,
            trigger_signal_id=trigger_signal_id,
            status=OutreachStatus.DRAFTED,
            follow_up_due=follow_up_due,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def has_open_draft(self, company_id: UUID) -> bool:
        stmt = select(OutreachRecord.id).where(
            and_(
                OutreachRecord.company_id == company_id,
                OutreachRecord.status.in_([
                    OutreachStatus.IDENTIFIED,
                    OutreachStatus.DRAFTED,
                    OutreachStatus.SENT,
                ]),
            )
        ).limit(1)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def list_due(self, days_ahead: int = 1) -> list[OutreachRecord]:
        """Return outreach records with a follow-up due within N days."""
        cutoff = datetime.utcnow() + timedelta(days=days_ahead)
        stmt = (
            select(OutreachRecord)
            .where(
                and_(
                    OutreachRecord.follow_up_due <= cutoff,
                    OutreachRecord.status.in_([
                        OutreachStatus.SENT,
                        OutreachStatus.DRAFTED,
                    ]),
                )
            )
            .order_by(asc(OutreachRecord.follow_up_due))
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        record_id: UUID,
        status: OutreachStatus,
        notes: str = "",
    ) -> None:
        values: dict = {"status": status, "updated_at": datetime.utcnow()}
        if notes:
            values["notes"] = notes
        if status == OutreachStatus.SENT:
            values["sent_at"] = datetime.utcnow()
        elif status == OutreachStatus.RESPONDED:
            values["responded_at"] = datetime.utcnow()

        stmt = update(OutreachRecord).where(OutreachRecord.id == record_id).values(**values)
        await self.db.execute(stmt)

    async def count_due(self) -> int:
        cutoff = datetime.utcnow() + timedelta(days=1)
        result = await self.db.execute(
            select(func.count(OutreachRecord.id)).where(
                and_(
                    OutreachRecord.follow_up_due <= cutoff,
                    OutreachRecord.status.in_([
                        OutreachStatus.SENT,
                        OutreachStatus.DRAFTED,
                    ]),
                )
            )
        )
        return result.scalar_one()


# ─── UserProfile Repository ───────────────────────────────────────

class ProfileRepo:
    def __init__(self, session: AsyncSession):
        self.db = session

    async def get(self) -> Optional[UserProfile]:
        result = await self.db.execute(select(UserProfile).where(UserProfile.id == 1))
        return result.scalar_one_or_none()

    async def upsert(self, **fields) -> UserProfile:
        profile = await self.get()
        if profile is None:
            profile = UserProfile(id=1, **fields)
            self.db.add(profile)
        else:
            for key, val in fields.items():
                if hasattr(profile, key):
                    setattr(profile, key, val)
            profile.updated_at = datetime.utcnow()
        await self.db.flush()
        return profile


# ─── IngestRun Repository ─────────────────────────────────────────

class IngestRunRepo:
    def __init__(self, session: AsyncSession):
        self.db = session

    async def start(self, source: str) -> IngestRun:
        run = IngestRun(source=source, status="running")
        self.db.add(run)
        await self.db.flush()
        return run

    async def finish(
        self,
        run_id: UUID,
        records_found: int = 0,
        records_new: int = 0,
        error: Optional[str] = None,
    ) -> None:
        stmt = (
            update(IngestRun)
            .where(IngestRun.id == run_id)
            .values(
                status="error" if error else "success",
                finished_at=datetime.utcnow(),
                records_found=records_found,
                records_new=records_new,
                error_message=error,
            )
        )
        await self.db.execute(stmt)

    async def get_last(self, source: str) -> Optional[IngestRun]:
        stmt = (
            select(IngestRun)
            .where(IngestRun.source == source)
            .order_by(desc(IngestRun.started_at))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
