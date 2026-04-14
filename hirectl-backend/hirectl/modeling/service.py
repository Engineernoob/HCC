"""Runtime inference helpers for the baseline hiring velocity model."""

from __future__ import annotations

import logging
import math
import statistics
from pathlib import Path
from typing import Any, Mapping

from hirectl.config import settings
from hirectl.modeling.baseline import load_artifact
from hirectl.modeling.features import feature_vector_from_payload

logger = logging.getLogger(__name__)


class HiringVelocityModelService:
    """Loads the trained artifact and produces model-based score adjustments."""

    def __init__(self, artifact_path: str | None = None):
        self.artifact_path = artifact_path or settings.model_artifact_path
        self._artifact_cache: dict[str, Any] | None = None
        self._artifact_mtime: float | None = None

    def is_available(self) -> bool:
        return Path(self.artifact_path).exists()

    def blend_score(self, heuristic_score: float, model_score: float | None) -> float:
        if model_score is None:
            return round(heuristic_score, 1)
        weight = settings.model_score_weight
        blended = ((1.0 - weight) * heuristic_score) + (weight * model_score)
        return round(blended, 1)

    def predict(self, features: Mapping[str, Any]) -> dict[str, float] | None:
        artifact = self._load_artifact()
        if artifact is None:
            return None

        model = artifact["model"]
        vector = feature_vector_from_payload(features)
        prediction = float(model.predict([vector])[0])
        prediction = max(0.0, prediction)

        estimators = getattr(model, "estimators_", [])
        tree_predictions = [float(estimator.predict([vector])[0]) for estimator in estimators]
        deviation = statistics.pstdev(tree_predictions) if len(tree_predictions) > 1 else 0.0
        scale = max(abs(prediction), 2.0)
        confidence = max(0.0, min(100.0, 100.0 * (1.0 - min(deviation / scale, 1.0))))

        score_scale = float(artifact.get("score_scale", 3.0) or 3.0)
        model_score = max(0.0, min(100.0, (prediction / score_scale) * 100.0))

        return {
            "predicted_new_roles_30d": round(prediction, 3),
            "model_score": round(model_score, 1),
            "model_confidence": round(confidence, 1),
            "prediction_stddev": round(deviation, 3),
        }

    def _load_artifact(self) -> dict[str, Any] | None:
        path = Path(self.artifact_path)
        if not path.exists():
            return None

        mtime = path.stat().st_mtime
        if self._artifact_cache is not None and self._artifact_mtime == mtime:
            return self._artifact_cache

        try:
            artifact = load_artifact(str(path))
        except Exception as exc:
            logger.warning(f"Model artifact load failed: {exc}")
            self._artifact_cache = None
            self._artifact_mtime = None
            return None

        self._artifact_cache = artifact
        self._artifact_mtime = mtime
        return artifact
