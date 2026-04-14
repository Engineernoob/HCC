"""Shared feature vectorization for Phase 3 training and inference."""

from __future__ import annotations

import json
from typing import Any, Mapping

from hirectl.db.models import SignalType

STAGE_ORDER = {
    "unknown": 0.0,
    "seed": 1.0,
    "series_a": 2.0,
    "series_b": 3.0,
    "series_c": 4.0,
    "series_d_plus": 5.0,
    "public": 6.0,
}

ROLE_TYPE_KEYS = [
    "backend",
    "fullstack",
    "ai_ml",
    "infra",
    "platform",
    "distributed",
    "frontend",
    "mobile",
    "data",
    "unknown",
]

ROLE_SOURCE_KEYS = [
    SignalType.ATS_GREENHOUSE.value,
    SignalType.ATS_ASHBY.value,
    SignalType.ATS_LEVER.value,
    SignalType.CAREER_PAGE.value,
    SignalType.YC_JOBS.value,
    SignalType.WELLFOUND.value,
]

SIGNAL_COUNT_KEYS = [
    SignalType.FUNDING.value,
    SignalType.FOUNDER_POST.value,
    SignalType.GITHUB_SPIKE.value,
    SignalType.BLOG_POST.value,
    SignalType.NEWS.value,
    SignalType.CAREER_PAGE.value,
    SignalType.ATS_GREENHOUSE.value,
    SignalType.ATS_ASHBY.value,
    SignalType.ATS_LEVER.value,
    SignalType.YC_JOBS.value,
    SignalType.WELLFOUND.value,
]

FEATURE_COLUMNS = [
    "funding_stage_ord",
    "headcount",
    "engineering_headcount",
    "active_roles_total",
    "active_remote_roles_total",
    "new_roles_7d",
    "new_roles_30d",
    "removed_roles_30d",
    "days_since_last_funding",
    "last_funding_amount_usd",
    "funding_events_12m",
    "funding_amount_12m",
    "signals_30d_total",
    "max_signal_score_30d",
    "headcount_missing",
    "engineering_headcount_missing",
] + [f"role_type__{key}" for key in ROLE_TYPE_KEYS] + [
    f"role_source__{key}" for key in ROLE_SOURCE_KEYS
] + [f"signal_count__{key}" for key in SIGNAL_COUNT_KEYS]


def parse_counts(raw: Any) -> dict[str, float]:
    if isinstance(raw, dict):
        return {str(key): float(value or 0.0) for key, value in raw.items()}
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): float(value or 0.0) for key, value in data.items()}


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value in (None, "", "null"):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _base_feature_payload(features: Mapping[str, Any]) -> dict[str, float]:
    vector: dict[str, float] = {
        "funding_stage_ord": STAGE_ORDER.get(
            str(features.get("funding_stage", "unknown")).lower(),
            0.0,
        ),
        "headcount": _safe_float(features.get("headcount")),
        "engineering_headcount": _safe_float(features.get("engineering_headcount")),
        "active_roles_total": _safe_float(features.get("active_roles_total")),
        "active_remote_roles_total": _safe_float(features.get("active_remote_roles_total")),
        "new_roles_7d": _safe_float(features.get("new_roles_7d")),
        "new_roles_30d": _safe_float(features.get("new_roles_30d")),
        "removed_roles_30d": _safe_float(features.get("removed_roles_30d")),
        "days_since_last_funding": _safe_float(features.get("days_since_last_funding"), 365.0),
        "last_funding_amount_usd": _safe_float(features.get("last_funding_amount_usd")),
        "funding_events_12m": _safe_float(features.get("funding_events_12m")),
        "funding_amount_12m": _safe_float(features.get("funding_amount_12m")),
        "signals_30d_total": _safe_float(features.get("signals_30d_total")),
        "max_signal_score_30d": _safe_float(features.get("max_signal_score_30d")),
        "headcount_missing": 1.0 if features.get("headcount") in (None, "", "null") else 0.0,
        "engineering_headcount_missing": (
            1.0 if features.get("engineering_headcount") in (None, "", "null") else 0.0
        ),
    }

    role_type_counts = parse_counts(features.get("role_type_counts"))
    for key in ROLE_TYPE_KEYS:
        vector[f"role_type__{key}"] = role_type_counts.get(key, 0.0)

    source_counts = parse_counts(features.get("source_counts"))
    for key in ROLE_SOURCE_KEYS:
        vector[f"role_source__{key}"] = source_counts.get(key, 0.0)

    signal_counts = parse_counts(features.get("signal_counts_30d"))
    for key in SIGNAL_COUNT_KEYS:
        vector[f"signal_count__{key}"] = signal_counts.get(key, 0.0)

    return vector


def feature_vector_from_payload(features: Mapping[str, Any]) -> list[float]:
    vector = _base_feature_payload(features)
    return [vector[column] for column in FEATURE_COLUMNS]


def feature_vector_from_csv_row(row: Mapping[str, Any]) -> list[float]:
    return feature_vector_from_payload(row)

