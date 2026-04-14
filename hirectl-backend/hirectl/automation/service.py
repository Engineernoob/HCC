"""
Rules-based automation for HIRE INTEL.

This is the first automation layer:
  1. Auto-watchlist companies that cross strong score/signal thresholds
  2. Auto-create an outreach draft when a watchlisted company is strong enough

The logic is intentionally explicit and auditable.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from hirectl.ai.engine import AIEngine, CompanyContext
from hirectl.config import settings
from hirectl.db.models import Company
from hirectl.db.repository import CompanyRepo, OutreachRepo, RoleRepo, SignalRepo
from hirectl.db.session import get_session

logger = logging.getLogger(__name__)


class AutomationService:
    """Applies simple automation rules to the current company set."""

    async def run(self) -> dict:
        if not settings.automation_enabled:
            return {"ok": True, "automation_enabled": False}

        summary = {
            "ok": True,
            "automation_enabled": True,
            "companies_scanned": 0,
            "watchlist_added": 0,
            "watchlist_removed": 0,
            "priority_updated": 0,
            "outreach_created": 0,
        }

        async with get_session() as session:
            company_repo = CompanyRepo(session)
            role_repo = RoleRepo(session)
            signal_repo = SignalRepo(session)
            outreach_repo = OutreachRepo(session)

            companies = list((await session.execute(select(Company))).scalars().all())
            ai_engine = AIEngine() if settings.ai_available else None

            for company in companies:
                summary["companies_scanned"] += 1
                roles = await role_repo.list_active(company_id=company.id, limit=100)
                signals = await signal_repo.list_recent(
                    company_id=company.id,
                    hours=24 * 30,
                    limit=50,
                )

                if self._should_watchlist(company, roles, signals):
                    if not company.on_watchlist:
                        await company_repo.set_watchlist(company.id, True)
                        company.on_watchlist = True
                        summary["watchlist_added"] += 1
                elif self._should_remove_from_watchlist(company, roles, signals):
                    await company_repo.set_watchlist(company.id, False)
                    company.on_watchlist = False
                    summary["watchlist_removed"] += 1

                if company.on_watchlist:
                    priority = self._watchlist_priority(company, roles, signals)
                    if priority != (company.watchlist_priority or 0):
                        await company_repo.set_watchlist_priority(company.id, priority)
                        company.watchlist_priority = priority
                        summary["priority_updated"] += 1

                if self._should_create_outreach(company, roles, signals):
                    if await outreach_repo.has_open_draft(company.id):
                        continue

                    contact_role = self._contact_role(company, roles, signals)
                    draft = await self._build_outreach_draft(company, roles, signals, ai_engine)
                    await outreach_repo.create(
                        company_id=company.id,
                        draft=draft,
                        contact_role=contact_role,
                        outreach_angle=self._automation_angle(company, roles, signals),
                        follow_up_due=(
                            datetime.utcnow()
                            + timedelta(days=settings.automation_outreach_follow_up_days)
                        ),
                    )
                    summary["outreach_created"] += 1

        logger.info(
            f"Automation: scanned={summary['companies_scanned']} "
            f"watchlisted={summary['watchlist_added']} "
            f"watchlist_removed={summary['watchlist_removed']} "
            f"priority_updated={summary['priority_updated']} "
            f"outreach_created={summary['outreach_created']}"
        )
        return summary

    def _should_watchlist(self, company, roles, signals) -> bool:
        return (
            (company.composite_score or 0.0) >= settings.automation_watchlist_min_score
            and len(roles) >= settings.automation_watchlist_min_roles
            and len(signals) >= settings.automation_watchlist_min_signals_30d
        )

    def _should_create_outreach(self, company, roles, signals) -> bool:
        return (
            company.on_watchlist
            and (company.composite_score or 0.0) >= settings.automation_outreach_min_score
            and len(roles) >= 1
            and len(signals) >= 1
        )

    def _should_remove_from_watchlist(self, company, roles, signals) -> bool:
        if not company.on_watchlist:
            return False
        if company.watchlist_added_at is None:
            return False

        age_days = (datetime.utcnow() - company.watchlist_added_at).days
        if age_days < settings.automation_stale_watchlist_days:
            return False

        return (
            (company.composite_score or 0.0) <= settings.automation_stale_watchlist_max_score
            and len(roles) <= settings.automation_stale_watchlist_max_roles
            and len(signals) <= settings.automation_stale_watchlist_max_signals_30d
        )

    def _watchlist_priority(self, company, roles, signals) -> int:
        priority = int(min(100, max(0, round(company.composite_score or 0.0))))

        fresh_roles = sum(1 for role in roles if (role.days_open or 0) <= 3)
        founder_signal = any(signal.type == "founder_post" for signal in signals)
        funding_signal = any(signal.type == "funding" for signal in signals)

        priority += min(12, fresh_roles * 4)
        if founder_signal:
            priority += 10
        if funding_signal:
            priority += 6
        if company.remote_us:
            priority += 4

        return max(0, min(100, priority))

    def _contact_role(self, company, roles, signals) -> str:
        if any(signal.type == "founder_post" for signal in signals):
            return "founder"
        if any("recruit" in (signal.headline or "").lower() for signal in signals):
            return "recruiter"
        if roles and any(
            role.role_type and role.role_type.value in {"infra", "distributed", "backend"}
            if hasattr(role.role_type, "value")
            else str(role.role_type) in {"infra", "distributed", "backend"}
            for role in roles
        ):
            return "engineering lead"
        return settings.automation_outreach_contact_role

    async def _build_outreach_draft(self, company, roles, signals, ai_engine: AIEngine | None) -> str:
        if ai_engine is None:
            return self._fallback_outreach(company, roles, signals)

        context = CompanyContext(
            name=company.name,
            tagline=company.tagline or "",
            description=company.description or "",
            funding_stage=company.funding_stage.value if company.funding_stage else "",
            funding_amount=company.funding_amount_usd,
            last_funding_date=company.last_funding_date,
            tech_stack=company.tech_stack or {},
            open_roles=[role.title for role in roles[:5]],
            recent_signals=[signal.headline or "" for signal in signals[:5] if signal.headline],
            github_org=company.github_org or "",
            headcount=company.headcount,
            remote_us=company.remote_us or False,
            fit_score=company.fit_score or 0.0,
            urgency_score=company.urgency_score or 0.0,
            urgency_label=company.urgency.value if hasattr(company, "urgency") else "medium",
        )
        return await ai_engine.generate_outreach_draft(
            company=context,
            contact_role=self._contact_role(company, roles, signals),
            specific_angle=self._automation_angle(company, roles, signals),
        )

    def _automation_angle(self, company, roles, signals) -> str:
        role_hint = roles[0].title if roles else "engineering role growth"
        signal_hint = signals[0].headline if signals else "recent hiring signal"
        return (
            f"Reference the recent signal '{signal_hint}' and tie it to "
            f"the open role '{role_hint}' with a concrete systems/backend fit angle."
        )

    def _fallback_outreach(self, company, roles, signals) -> str:
        top_role = roles[0].title if roles else "engineering role"
        top_signal = signals[0].headline if signals else "recent hiring signal"
        return (
            f"Subject: {company.name} — quick intro\n\n"
            f"I’m reaching out because {top_signal.lower()} and the open {top_role} role "
            f"make the timing concrete. My background is strongest in backend, distributed "
            f"systems, and AI-adjacent infrastructure, which looks aligned with the kind of "
            f"engineering work your team is scaling right now.\n\n"
            f"If it’s useful, I’d be happy to do a short 15 minute call and compare what you "
            f"need on the role with the systems work I’ve been shipping recently.\n\n"
            f"Taahirah"
        )
