"""
Ingestion service — the glue layer between adapters and the database.

Flow for every ingest run:
  1. Adapter fetches raw data → IngestResult
  2. Service upserts companies via CompanyRepo
  3. Service upserts signals via SignalRepo (dedup)
  4. Service upserts roles via RoleRepo
  5. Scoring engine recomputes company scores
  6. AI engine generates/updates brief if score changed significantly
  7. IngestRun logged

This keeps all DB logic out of the adapters (they return plain dataclasses)
and all adapter logic out of the service (it just calls .run()).
"""

import logging
from datetime import date, datetime
from collections import defaultdict
from typing import Optional
from uuid import UUID

from hirectl.analytics.history import HistoricalAnalyticsService
from hirectl.config import settings
from hirectl.db.models import SignalType
from hirectl.db.repository import (
    CompanyRepo,
    FundingHistoryRepo,
    IngestRunRepo,
    RoleRepo,
    SignalRepo,
)
from hirectl.db.session import get_session
from hirectl.ingestion.base import IngestResult
from hirectl.modeling.service import HiringVelocityModelService
from hirectl.scoring.engine import ScoringEngine
from hirectl.signals.payloads import signal_payload
from hirectl.signals.stream import signal_stream_broker

logger = logging.getLogger(__name__)

class IngestionService:
    """
    Persists ingestion results and triggers downstream scoring.
    Called after every adapter run.
    """

    def __init__(self, scoring_engine: Optional[ScoringEngine] = None):
        self.scoring = scoring_engine or ScoringEngine()
        self.analytics = HistoricalAnalyticsService()
        self.modeling = HiringVelocityModelService()

    async def refresh_all_company_scores(self) -> dict:
        """Recompute blended ranking scores for every company in the database."""
        from sqlalchemy import select
        from hirectl.db.models import Company

        refreshed = 0
        async with get_session() as session:
            companies = list((await session.execute(select(Company.id))).scalars().all())
            for company_id in companies:
                await self._rescore_company(company_id, session)
                refreshed += 1
        return {"ok": True, "companies_refreshed": refreshed}

    async def process(self, result: IngestResult) -> dict:
        """
        Process one IngestResult: upsert everything, rescore companies.
        Returns a summary dict for logging/API response.
        """
        if not result.ok:
            logger.warning(f"Skipping failed ingest result: {result.error}")
            return {"ok": False, "error": result.error}

        summary = {
            "source": result.source,
            "companies_upserted": 0,
            "signals_new": 0,
            "roles_new": 0,
            "roles_updated": 0,
            "companies_rescored": 0,
        }
        published_signals: list[dict] = []

        async with get_session() as session:
            company_repo = CompanyRepo(session)
            signal_repo = SignalRepo(session)
            role_repo = RoleRepo(session)
            run_repo = IngestRunRepo(session)
            funding_history_repo = FundingHistoryRepo(session)

            run = await run_repo.start(result.source)

            try:
                # 1. Upsert companies
                company_ids: dict[str, UUID] = {}
                for co_data in result.companies:
                    company = await company_repo.upsert(co_data)
                    company_ids[co_data.name.lower()] = company.id
                    summary["companies_upserted"] += 1

                # 2. Upsert signals
                for sig_data in result.signals:
                    company_id = await self._resolve_company_id(
                        sig_data.company_name, company_ids, company_repo
                    )
                    if company_id is None:
                        continue
                    signal = await signal_repo.upsert(company_id, sig_data)
                    if signal is not None:
                        summary["signals_new"] += 1
                        published_signals.append(
                            signal_payload(
                                signal_id=signal.id,
                                company_id=company_id,
                                company_name=sig_data.company_name,
                                signal_type=sig_data.type.value,
                                headline=sig_data.headline,
                                detail=sig_data.detail,
                                score=sig_data.score,
                                signal_date=sig_data.signal_date,
                                source_url=sig_data.source_url or "",
                            )
                        )

                        # Update last_signal_at on company
                        from sqlalchemy import update
                        from hirectl.db.models import Company
                        await session.execute(
                            update(Company)
                            .where(Company.id == company_id)
                            .values(last_signal_at=datetime.utcnow())
                        )
                        if sig_data.type == SignalType.FUNDING:
                            await funding_history_repo.record_event(
                                company_id=company_id,
                                announced_at=sig_data.signal_date,
                                round_type=sig_data.funding_round or "",
                                amount_usd=sig_data.funding_amount_usd,
                                source=result.source,
                                source_url=sig_data.source_url or "",
                            )

                # 3. Upsert roles
                for role_data in result.roles:
                    company_id = await self._resolve_company_id(
                        role_data.company_name, company_ids, company_repo
                    )
                    if company_id is None:
                        continue
                    _, is_new = await role_repo.upsert(company_id, role_data)
                    if is_new:
                        summary["roles_new"] += 1
                    else:
                        summary["roles_updated"] += 1

                if result.source == "career_page":
                    active_urls_by_company: dict[str, set[str]] = defaultdict(set)
                    for role_data in result.roles:
                        active_urls_by_company[role_data.company_name.lower()].add(role_data.url)

                    for company_data in result.companies:
                        company_id = await self._resolve_company_id(
                            company_data.name, company_ids, company_repo
                        )
                        if company_id is None:
                            continue
                        await role_repo.mark_inactive(
                            company_id=company_id,
                            active_urls=active_urls_by_company.get(company_data.name.lower(), set()),
                            source=SignalType.CAREER_PAGE,
                        )

                # 4. Rescore all affected companies
                for company_name, company_id in company_ids.items():
                    try:
                        await self._rescore_company(company_id, session)
                        summary["companies_rescored"] += 1
                    except Exception as e:
                        logger.warning(f"Rescore failed for {company_name}: {e}")

                await run_repo.finish(
                    run.id,
                    records_found=result.total_records,
                    records_new=summary["signals_new"] + summary["roles_new"],
                )

            except Exception as e:
                await session.rollback()
                await run_repo.finish(run.id, error=str(e))
                raise

        for payload in published_signals:
            await signal_stream_broker.publish(payload)

        logger.info(
            f"Ingestion processed [{result.source}]: "
            f"{summary['companies_upserted']} companies, "
            f"{summary['signals_new']} new signals, "
            f"{summary['roles_new']} new roles"
        )
        return {**summary, "ok": True}

    async def _resolve_company_id(
        self,
        name: str,
        known_ids: dict[str, UUID],
        repo: CompanyRepo,
    ) -> Optional[UUID]:
        """Resolve a company name to its DB UUID."""
        # Check our in-flight upserts first
        cid = known_ids.get(name.lower())
        if cid:
            return cid

        # Fall back to DB lookup
        company = await repo.get_by_name(name)
        if company:
            known_ids[name.lower()] = company.id
            return company.id

        # Auto-create a minimal company record
        from hirectl.ingestion.base import CompanyResult
        company = await repo.upsert(CompanyResult(name=name))
        known_ids[name.lower()] = company.id
        return company.id

    async def _rescore_company(self, company_id: UUID, session) -> None:
        """
        Load all signals and roles for a company, run the scoring engine,
        and update the company record.
        """
        from hirectl.db.repository import CompanyRepo, RoleRepo
        from hirectl.db.models import Company, SignalType

        company_repo = CompanyRepo(session)
        role_repo = RoleRepo(session)

        company = await company_repo.get_by_id(company_id)
        if not company:
            return

        # Gather inputs for the scoring engine
        roles = await role_repo.list_active(company_id=company_id)
        role_types = list({r.role_type.value for r in roles})
        required_skills = list({
            skill
            for r in roles
            for skill in (r.required_skills or [])
        })

        # Find funding signals
        funding_signals = [
            s for s in (company.signals or [])
            if s.type == SignalType.FUNDING
        ]
        latest_funding = max(
            (s.signal_date for s in funding_signals), default=None
        ) if funding_signals else company.last_funding_date

        latest_funding_amount = (
            funding_signals[0].funding_amount_usd
            if funding_signals else company.funding_amount_usd
        )

        # Find founder post signals
        founder_signals = [
            s for s in (company.signals or [])
            if s.type == SignalType.FOUNDER_POST
        ]
        has_founder_post = bool(founder_signals)
        latest_founder_post = max(
            (s.signal_date for s in founder_signals), default=None
        ) if founder_signals else None

        # Find GitHub spike signals
        github_signals = [
            s for s in (company.signals or [])
            if s.type == SignalType.GITHUB_SPIKE
        ]
        latest_github = max(
            (s.signal_date for s in github_signals), default=None
        ) if github_signals else None
        max_sigma = max(
            (s.score / 10 for s in github_signals), default=0.0
        )

        # Latest role date
        latest_role = max(
            (r.first_seen_at for r in roles), default=None
        ) if roles else None
        oldest_open_days = await role_repo.get_oldest_open_days(company_id)

        score_result = self.scoring.score_company(
            company_name=company.name,
            role_types=role_types,
            required_skills=required_skills,
            funding_stage=company.funding_stage.value if company.funding_stage else "unknown",
            last_funding_date=latest_funding,
            last_role_posted=latest_role,
            oldest_open_role_days=oldest_open_days,
            has_founder_post=has_founder_post,
            founder_post_date=latest_founder_post,
            github_spike_date=latest_github,
            github_spike_sigma=max_sigma,
            has_engineering_blog=False,  # TODO: detect from blog_post signals
            remote_us=company.remote_us or False,
            headcount=company.headcount,
            funding_amount_usd=latest_funding_amount,
        )

        features = await self.analytics.materialize_company_snapshot(
            session,
            company,
            date.today(),
        )
        model_prediction = self.modeling.predict(features)
        blended_composite = self.modeling.blend_score(
            score_result.composite_score,
            model_prediction["model_score"] if model_prediction else None,
        )

        await company_repo.update_scores(
            company_id=company_id,
            fit_score=score_result.fit_score,
            urgency_score=score_result.urgency_score,
            composite_score=blended_composite,
        )

        logger.debug(
            f"Rescored {company.name}: "
            f"composite={blended_composite:.1f} "
            f"(fit={score_result.fit_score:.1f}, urgency={score_result.urgency_score:.1f})"
        )

    async def refresh_company_briefs(self, limit: Optional[int] = None) -> dict:
        """Refresh AI briefs outside the ingest path."""
        if not settings.ai_available:
            return {"ok": True, "candidates": 0, "updated": 0, "skipped": "ai_unavailable"}

        batch_limit = limit or settings.ai_brief_refresh_batch_size
        updated = 0

        async with get_session() as session:
            repo = CompanyRepo(session)
            candidates = await repo.list_brief_candidates(
                min_score=settings.ai_brief_refresh_min_score,
                max_age_hours=settings.ai_brief_refresh_max_age_hours,
                limit=batch_limit,
            )

            for company in candidates:
                try:
                    await self._refresh_company_brief(session, repo, company)
                    updated += 1
                except Exception as e:
                    logger.warning("Brief refresh failed for %s: %s", company.name, e)

        return {"ok": True, "candidates": len(candidates), "updated": updated}

    async def _refresh_company_brief(self, session, repo: CompanyRepo, company) -> None:
        """Generate and store an AI brief for a company."""
        try:
            from hirectl.ai.engine import AIEngine, CompanyContext

            engine = AIEngine()
            ctx = self._build_company_context(company)

            brief = await engine.generate_brief(ctx)

            await repo.update_scores(
                company_id=company.id,
                fit_score=company.fit_score or 0.0,
                urgency_score=company.urgency_score or 0.0,
                composite_score=company.composite_score or 0.0,
                ai_brief=brief,
            )
            await session.flush()

            logger.info("Brief stored for %s", company.name)
        except Exception as e:
            logger.warning("Brief generation failed for %s: %s", company.name, e)

    def _build_company_context(self, company):
        recent_signals = []
        sorted_signals = sorted(
            company.signals or [],
            key=lambda signal: signal.signal_date or datetime.min,
            reverse=True,
        )
        for signal in sorted_signals[:5]:
            label = signal.type.value.replace("_", " ")
            recent_signals.append(f"{label}: {signal.headline or signal.detail or 'activity detected'}")

        open_roles = [
            role.title
            for role in sorted(
                [role for role in (company.roles or []) if role.is_active],
                key=lambda role: role.first_seen_at or datetime.min,
                reverse=True,
            )[:5]
        ]

        fit_notes = []
        urgency_notes = []
        if company.remote_us:
            fit_notes.append("Remote US is enabled")
        if company.tech_stack:
            visible_stack = ", ".join(
                (company.tech_stack.get("languages") or [])[:2]
                + (company.tech_stack.get("frameworks") or [])[:2]
                + (company.tech_stack.get("infra") or [])[:2]
            )
            if visible_stack:
                fit_notes.append(f"Visible stack: {visible_stack}")
        if company.last_signal_at:
            urgency_notes.append(f"Last signal at {company.last_signal_at.isoformat()}")
        if open_roles:
            urgency_notes.append(f"{len(open_roles)} active roles detected")

        return CompanyContext(
            name=company.name,
            description=company.description or "",
            tagline=company.tagline or "",
            funding_stage=company.funding_stage.value if company.funding_stage else "",
            funding_amount=company.funding_amount_usd,
            last_funding_date=company.last_funding_date,
            tech_stack=company.tech_stack or {},
            open_roles=open_roles,
            recent_signals=recent_signals,
            github_org=company.github_org or "",
            headcount=company.headcount,
            remote_us=company.remote_us or False,
            fit_score=company.fit_score or 0.0,
            urgency_score=company.urgency_score or 0.0,
            urgency_label=(company.urgency.value if company.urgency else "medium"),
            fit_notes=fit_notes,
            urgency_notes=urgency_notes,
        )
