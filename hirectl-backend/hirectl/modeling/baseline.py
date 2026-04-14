"""Train and use a baseline hiring velocity model."""

from __future__ import annotations

import csv
import math
import pickle
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from hirectl.modeling.features import FEATURE_COLUMNS, feature_vector_from_csv_row


@dataclass
class TrainingDataset:
    rows: list[dict[str, Any]]
    x: list[list[float]]
    y: list[float]


def load_training_dataset(dataset_path: str) -> TrainingDataset:
    with open(dataset_path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    rows = [row for row in rows if row.get("label_new_roles_next_30d") not in (None, "")]
    rows.sort(key=lambda row: row.get("as_of_date", ""))

    x = [feature_vector_from_csv_row(row) for row in rows]
    y = [float(row["label_new_roles_next_30d"]) for row in rows]
    return TrainingDataset(rows=rows, x=x, y=y)


def _split_index(count: int) -> int:
    if count < 8:
        raise ValueError("Need at least 8 dataset rows to train a baseline model")
    return max(1, min(count - 1, int(count * 0.8)))


def train_baseline_model(
    *,
    dataset_path: str,
    artifact_path: str,
    target_column: str = "label_new_roles_next_30d",
) -> dict[str, Any]:
    dataset = load_training_dataset(dataset_path)
    split_idx = _split_index(len(dataset.rows))

    train_x = dataset.x[:split_idx]
    train_y = dataset.y[:split_idx]
    valid_x = dataset.x[split_idx:]
    valid_y = dataset.y[split_idx:]

    model = RandomForestRegressor(
        n_estimators=200,
        min_samples_leaf=2,
        random_state=42,
    )
    model.fit(train_x, train_y)

    train_pred = model.predict(train_x)
    valid_pred = model.predict(valid_x)

    score_scale = max(3.0, sorted(dataset.y)[max(0, math.ceil(len(dataset.y) * 0.9) - 1)])
    artifact = {
        "trained_at": datetime.utcnow().isoformat(),
        "target_column": target_column,
        "feature_columns": FEATURE_COLUMNS,
        "score_scale": float(score_scale),
        "row_count": len(dataset.rows),
        "split_index": split_idx,
        "model": model,
    }

    output = Path(artifact_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        pickle.dump(artifact, handle)

    metrics = {
        "train_mae": round(mean_absolute_error(train_y, train_pred), 4),
        "train_rmse": round(math.sqrt(mean_squared_error(train_y, train_pred)), 4),
        "train_r2": round(r2_score(train_y, train_pred), 4),
        "valid_mae": round(mean_absolute_error(valid_y, valid_pred), 4),
        "valid_rmse": round(math.sqrt(mean_squared_error(valid_y, valid_pred)), 4),
        "valid_r2": round(r2_score(valid_y, valid_pred), 4),
    }
    return {
        "ok": True,
        "dataset_path": dataset_path,
        "artifact_path": str(output),
        "rows": len(dataset.rows),
        "train_rows": len(train_x),
        "valid_rows": len(valid_x),
        "metrics": metrics,
    }


def load_artifact(artifact_path: str) -> dict[str, Any]:
    with open(artifact_path, "rb") as handle:
        return pickle.load(handle)

