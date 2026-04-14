"""
Helpers for shaping signal payloads for APIs and live streams.
"""

from datetime import datetime
from typing import Any
from uuid import UUID


TYPE_LABELS: dict[str, str] = {
    "funding": "Funding Event",
    "founder_post": "Founder Post",
    "ats_greenhouse": "ATS — Greenhouse",
    "ats_lever": "ATS — Lever",
    "ats_ashby": "ATS — Ashby",
    "career_page": "Career Page Diff",
    "github_spike": "GitHub Activity",
    "blog_post": "Engineering Blog",
    "yc_jobs": "YC Jobs",
    "wellfound": "Wellfound",
    "news": "News",
}


def score_variant(score: float) -> str:
    if score >= 75:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def signal_payload(
    *,
    signal_id: UUID | str,
    company_id: UUID | str,
    company_name: str,
    signal_type: str,
    headline: str,
    detail: str,
    score: float,
    signal_date: datetime,
    source_url: str,
) -> dict[str, Any]:
    return {
        "id": str(signal_id),
        "company_id": str(company_id),
        "company_name": company_name,
        "type": signal_type,
        "type_label": TYPE_LABELS.get(signal_type, signal_type.replace("_", " ").title()),
        "headline": headline,
        "detail": detail,
        "score": score,
        "score_variant": score_variant(score),
        "signal_date": signal_date.isoformat(),
        "source_url": source_url,
    }


def signal_payload_from_model(signal, company_name: str) -> dict[str, Any]:
    signal_type = signal.type.value if hasattr(signal.type, "value") else str(signal.type)
    return signal_payload(
        signal_id=signal.id,
        company_id=signal.company_id,
        company_name=company_name,
        signal_type=signal_type,
        headline=signal.headline or "",
        detail=signal.detail or "",
        score=signal.score or 0.0,
        signal_date=signal.signal_date,
        source_url=signal.source_url or "",
    )
