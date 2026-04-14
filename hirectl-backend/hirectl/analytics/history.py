"""
Phase 2.5 historical rollups and dataset export.

This materializes point-in-time company features from the existing
signals, roles, and funding history so later model training can avoid
re-deriving everything from raw events every time.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

from sqlalchemy import and_, select

from hirectl.db.models import Company, Signal
from hirectl.db.repository import (
    FeatureSnapshotRepo,
    FundingHistoryRepo,
    RoleDailyRepo,
    RoleRepo,
)
from hirectl.db.session import get_session

FEATURE_VERSION = "v1"


@dataclass
class RoleMetrics:
    active_roles_total: int
    active_remote_roles_total: int
    new_roles_7d: int
    new_roles_30d: int
    removed_roles_30d: int
    role_type_counts: dict[str, int]
    source_counts: dict[str, int]


class HistoricalAnalyticsService:
    """Build daily point-in-time snapshots and export a simple training dataset."""

    async def rollup_day(self, as_of_date: date | None = None) -> dict:
        as_of_date = as_of_date or date.today()
        async with get_session() as session:
            companies = list((await session.execute(select(Company))).scalars().all())

            rolled_up = 0
            for company in companies:
                await self.materialize_company_snapshot(session, company, as_of_date)
                rolled_up += 1

        return {
            "ok": True,
            "as_of_date": as_of_date.isoformat(),
            "companies_rolled_up": rolled_up,
            "feature_version": FEATURE_VERSION,
        }

    async def materialize_company_snapshot(self, session, company, as_of_date: date) -> dict:
        role_repo = RoleRepo(session)
        role_daily_repo = RoleDailyRepo(session)
        feature_snapshot_repo = FeatureSnapshotRepo(session)
        funding_history_repo = FundingHistoryRepo(session)

        roles = await role_repo.list_for_company_as_of(company.id, as_of_date)
        role_metrics = self._compute_role_metrics(roles, as_of_date)
        await role_daily_repo.upsert(
            company_id=company.id,
            as_of_date=as_of_date,
            active_roles_total=role_metrics.active_roles_total,
            active_remote_roles_total=role_metrics.active_remote_roles_total,
            new_roles_7d=role_metrics.new_roles_7d,
            new_roles_30d=role_metrics.new_roles_30d,
            removed_roles_30d=role_metrics.removed_roles_30d,
            role_type_counts=role_metrics.role_type_counts,
            source_counts=role_metrics.source_counts,
        )

        signal_metrics = await self._signal_metrics(session, company.id, as_of_date)
        funding_metrics = await self._funding_metrics(
            funding_history_repo, company.id, as_of_date
        )
        features = self._build_feature_payload(
            company=company,
            as_of_date=as_of_date,
            role_metrics=role_metrics,
            signal_metrics=signal_metrics,
            funding_metrics=funding_metrics,
        )
        await feature_snapshot_repo.upsert(
            company_id=company.id,
            as_of_date=as_of_date,
            feature_version=FEATURE_VERSION,
            features=features,
        )
        return features

    async def export_dataset(
        self,
        *,
        as_of_start: date,
        as_of_end: date,
        output_path: str,
        step_days: int = 7,
    ) -> dict:
        if as_of_end < as_of_start:
            raise ValueError("as_of_end must be on or after as_of_start")
        if step_days <= 0:
            raise ValueError("step_days must be positive")

        current = as_of_start
        while current <= as_of_end:
            await self.rollup_day(current)
            current += timedelta(days=step_days)

        async with get_session() as session:
            snapshots = await FeatureSnapshotRepo(session).list_between(
                as_of_start,
                as_of_end,
                FEATURE_VERSION,
            )
            companies = {
                company.id: company
                for company in list((await session.execute(select(Company))).scalars().all())
            }
            role_repo = RoleRepo(session)

            rows: list[dict[str, object]] = []
            for snapshot in snapshots:
                company = companies.get(snapshot.company_id)
                if company is None:
                    continue
                features = snapshot.features or {}
                next_30d = await role_repo.count_future_new_roles(
                    snapshot.company_id, snapshot.as_of_date, 30
                )
                next_60d = await role_repo.count_future_new_roles(
                    snapshot.company_id, snapshot.as_of_date, 60
                )
                rows.append(
                    {
                        "company_id": str(snapshot.company_id),
                        "company_name": company.name,
                        "as_of_date": snapshot.as_of_date.isoformat(),
                        "feature_version": snapshot.feature_version,
                        "funding_stage": features.get("funding_stage", ""),
                        "headcount": features.get("headcount"),
                        "engineering_headcount": features.get("engineering_headcount"),
                        "active_roles_total": features.get("active_roles_total", 0),
                        "active_remote_roles_total": features.get("active_remote_roles_total", 0),
                        "new_roles_7d": features.get("new_roles_7d", 0),
                        "new_roles_30d": features.get("new_roles_30d", 0),
                        "removed_roles_30d": features.get("removed_roles_30d", 0),
                        "days_since_last_funding": features.get("days_since_last_funding"),
                        "last_funding_amount_usd": features.get("last_funding_amount_usd"),
                        "funding_events_12m": features.get("funding_events_12m", 0),
                        "funding_amount_12m": features.get("funding_amount_12m", 0.0),
                        "signals_30d_total": features.get("signals_30d_total", 0),
                        "max_signal_score_30d": features.get("max_signal_score_30d", 0.0),
                        "signal_counts_30d": json.dumps(features.get("signal_counts_30d", {}), sort_keys=True),
                        "role_type_counts": json.dumps(features.get("role_type_counts", {}), sort_keys=True),
                        "source_counts": json.dumps(features.get("source_counts", {}), sort_keys=True),
                        "label_new_roles_next_30d": next_30d,
                        "label_new_roles_next_60d": next_60d,
                        "label_eng_hiring_spike_next_60d": int(next_60d >= 3),
                    }
                )

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(rows[0].keys()) if rows else [
            "company_id",
            "company_name",
            "as_of_date",
            "feature_version",
        ]
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        return {
            "ok": True,
            "output_path": str(output),
            "rows_written": len(rows),
            "feature_version": FEATURE_VERSION,
            "as_of_start": as_of_start.isoformat(),
            "as_of_end": as_of_end.isoformat(),
            "step_days": step_days,
        }

    def _compute_role_metrics(self, roles: list, as_of_date: date) -> RoleMetrics:
        end_of_day = datetime.combine(as_of_date, time.max)
        start_7d = end_of_day - timedelta(days=6)
        start_30d = end_of_day - timedelta(days=29)

        active_roles = [
            role
            for role in roles
            if role.first_seen_at <= end_of_day and (role.removed_at is None or role.removed_at > end_of_day)
        ]
        new_7d = [role for role in roles if start_7d <= role.first_seen_at <= end_of_day]
        new_30d = [role for role in roles if start_30d <= role.first_seen_at <= end_of_day]
        removed_30d = [
            role
            for role in roles
            if role.removed_at is not None and start_30d <= role.removed_at <= end_of_day
        ]

        role_type_counts = Counter(
            (role.role_type.value if hasattr(role.role_type, "value") else str(role.role_type))
            for role in active_roles
            if role.role_type
        )
        source_counts = Counter(
            (role.source.value if hasattr(role.source, "value") else str(role.source))
            for role in active_roles
            if role.source
        )

        return RoleMetrics(
            active_roles_total=len(active_roles),
            active_remote_roles_total=sum(1 for role in active_roles if role.is_remote_us),
            new_roles_7d=len(new_7d),
            new_roles_30d=len(new_30d),
            removed_roles_30d=len(removed_30d),
            role_type_counts=dict(role_type_counts),
            source_counts=dict(source_counts),
        )

    async def _signal_metrics(self, session, company_id, as_of_date: date) -> dict:
        window_end = datetime.combine(as_of_date, time.max)
        window_start = window_end - timedelta(days=29)
        signals = list(
            (
                await session.execute(
                    select(Signal).where(
                        and_(
                            Signal.company_id == company_id,
                            Signal.signal_date >= window_start,
                            Signal.signal_date <= window_end,
                        )
                    )
                )
            ).scalars().all()
        )
        counts = Counter(
            signal.type.value if hasattr(signal.type, "value") else str(signal.type)
            for signal in signals
            if signal.type
        )
        return {
            "signals_30d_total": len(signals),
            "signal_counts_30d": dict(counts),
            "max_signal_score_30d": max((signal.score or 0.0 for signal in signals), default=0.0),
        }

    async def _funding_metrics(
        self,
        funding_repo: FundingHistoryRepo,
        company_id,
        as_of_date: date,
    ) -> dict:
        history = await funding_repo.list_before(company_id, as_of_date)
        last_round = history[0] if history else None
        last_12m_cutoff = as_of_date - timedelta(days=365)
        trailing_12m = [row for row in history if row.announced_at.date() >= last_12m_cutoff]

        return {
            "days_since_last_funding": (
                (as_of_date - last_round.announced_at.date()).days if last_round else None
            ),
            "last_funding_amount_usd": last_round.amount_usd if last_round else None,
            "last_funding_round_type": last_round.round_type if last_round else None,
            "funding_events_12m": len(trailing_12m),
            "funding_amount_12m": sum(row.amount_usd or 0.0 for row in trailing_12m),
        }

    def _build_feature_payload(
        self,
        *,
        company,
        as_of_date: date,
        role_metrics: RoleMetrics,
        signal_metrics: dict,
        funding_metrics: dict,
    ) -> dict:
        return {
            "as_of_date": as_of_date.isoformat(),
            "funding_stage": company.funding_stage.value if company.funding_stage else "unknown",
            "headcount": company.headcount,
            "engineering_headcount": company.engineering_headcount,
            "remote_us": bool(company.remote_us),
            "active_roles_total": role_metrics.active_roles_total,
            "active_remote_roles_total": role_metrics.active_remote_roles_total,
            "new_roles_7d": role_metrics.new_roles_7d,
            "new_roles_30d": role_metrics.new_roles_30d,
            "removed_roles_30d": role_metrics.removed_roles_30d,
            "role_type_counts": role_metrics.role_type_counts,
            "source_counts": role_metrics.source_counts,
            **signal_metrics,
            **funding_metrics,
        }
