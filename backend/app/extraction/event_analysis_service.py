"""Runs the event-analysis DSPy signatures (classification, barrier-finding).

Mirrors `app.extraction.brief_service.BriefGenerationService`'s shape,
sharing the same lazily-configured global DSPy/MLflow runtime (see
`app.extraction.dspy_runtime`) so every signature in the app runs
against one consistent LM/adapter configuration per process.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

import dspy
import mlflow

from app.core.config import Settings, get_settings
from app.extraction.barrier_finding_signature import FindBarrierCondition
from app.extraction.dspy_runtime import DspyConfigurationError, ensure_dspy_configured
from app.extraction.event_analysis import EventAnalysisFindings, EventClassification
from app.extraction.event_classification_signature import ClassifyEventDescription


class EventAnalysisError(Exception):
    """Raised when DSPy configuration or an event-analysis call fails."""


class EventClassificationService:
    """Configures and runs the Step A event-classification signature."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        """Initializes the service.

        Args:
            settings: Application settings to configure DSPy/MLflow
                from. Defaults to the process-wide cached `Settings` instance.
        """
        self._settings = settings or get_settings()
        self._predictor: Optional[dspy.Predict] = None

    def _ensure_predictor(self) -> dspy.Predict:
        """Ensures DSPy is configured and this service's predictor exists.

        Returns:
            The `dspy.Predict(ClassifyEventDescription)` instance.

        Raises:
            EventAnalysisError: If DSPy configuration fails.
        """
        if self._predictor is None:
            try:
                ensure_dspy_configured(self._settings)
            except DspyConfigurationError as exc:
                raise EventAnalysisError(str(exc)) from exc
            self._predictor = dspy.Predict(ClassifyEventDescription)
        return self._predictor

    def classify(
        self,
        description: str,
        operation_types: list[str],
        vessel_types: list[str],
        mlflow_experiment_name: Optional[str] = None,
    ) -> EventClassification:
        """Classifies a free-text event description (Step A).

        Args:
            description: The user's free-text event description.
            operation_types: Known operation-type vocabulary to match against.
            vessel_types: Known vessel-type vocabulary to match against.
            mlflow_experiment_name: MLflow experiment to log this call
                under. Defaults to `Settings.MLFLOW_EXPERIMENT_NAME`.

        Returns:
            The classified operation type, vessel type, summary, and severity stage.

        Raises:
            EventAnalysisError: If DSPy configuration or the call itself
                fails, or returns no usable prediction.
        """
        predictor = self._ensure_predictor()
        mlflow.set_experiment(mlflow_experiment_name or self._settings.MLFLOW_EXPERIMENT_NAME)

        try:
            prediction = predictor(
                description=description,
                operation_types=operation_types,
                vessel_types=vessel_types,
            )
        except Exception as exc:  # noqa: BLE001
            raise EventAnalysisError(f"DSPy event classification call raised: {exc}") from exc

        if prediction is None or not hasattr(prediction, "classification"):
            raise EventAnalysisError(
                "DSPy event classification returned no usable prediction -- check "
                "MLflow traces for the underlying LM error."
            )
        return prediction.classification


class BarrierFindingService:
    """Configures and runs the Steps D+E barrier-finding signature."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        """Initializes the service.

        Args:
            settings: Application settings to configure DSPy/MLflow
                from. Defaults to the process-wide cached `Settings` instance.
        """
        self._settings = settings or get_settings()
        self._predictor: Optional[dspy.Predict] = None

    def _ensure_predictor(self) -> dspy.Predict:
        """Ensures DSPy is configured and this service's predictor exists.

        Returns:
            The `dspy.Predict(FindBarrierCondition)` instance.

        Raises:
            EventAnalysisError: If DSPy configuration fails.
        """
        if self._predictor is None:
            try:
                ensure_dspy_configured(self._settings)
            except DspyConfigurationError as exc:
                raise EventAnalysisError(str(exc)) from exc
            self._predictor = dspy.Predict(FindBarrierCondition)
        return self._predictor

    def find_barrier(
        self,
        described_event: str,
        near_miss_context: str,
        fatal_context: str,
        near_miss_count: int,
        serious_count: int,
        fatal_count: int,
        mlflow_experiment_name: Optional[str] = None,
    ) -> EventAnalysisFindings:
        """Finds the barrier condition and recommends one action (Steps D+E).

        Args:
            described_event: The original description plus its classification, for context.
            near_miss_context: Formatted contributing-factors context from the near-miss group.
            fatal_context: Formatted contributing-factors context from the fatal group.
            near_miss_count: Total matching near-miss reports.
            serious_count: Total matching serious (nonfatal injury) reports.
            fatal_count: Total matching fatal reports.
            mlflow_experiment_name: MLflow experiment to log this call
                under. Defaults to `Settings.MLFLOW_EXPERIMENT_NAME`.

        Returns:
            The barrier finding and recommended action, each with citations.

        Raises:
            EventAnalysisError: If DSPy configuration or the call itself
                fails, or returns no usable prediction.
        """
        predictor = self._ensure_predictor()
        mlflow.set_experiment(mlflow_experiment_name or self._settings.MLFLOW_EXPERIMENT_NAME)

        try:
            prediction = predictor(
                described_event=described_event,
                near_miss_context=near_miss_context,
                fatal_context=fatal_context,
                near_miss_count=near_miss_count,
                serious_count=serious_count,
                fatal_count=fatal_count,
            )
        except Exception as exc:  # noqa: BLE001
            raise EventAnalysisError(f"DSPy barrier-finding call raised: {exc}") from exc

        if prediction is None or not hasattr(prediction, "findings"):
            raise EventAnalysisError(
                "DSPy barrier-finding returned no usable prediction -- check "
                "MLflow traces for the underlying LM error."
            )
        return prediction.findings


@lru_cache
def get_event_classification_service() -> EventClassificationService:
    """Returns the process-wide `EventClassificationService` singleton.

    Returns:
        A lazily-configured `EventClassificationService`, cached per process.
    """
    return EventClassificationService()


@lru_cache
def get_barrier_finding_service() -> BarrierFindingService:
    """Returns the process-wide `BarrierFindingService` singleton.

    Returns:
        A lazily-configured `BarrierFindingService`, cached per process.
    """
    return BarrierFindingService()
