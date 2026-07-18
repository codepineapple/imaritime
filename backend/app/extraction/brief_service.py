"""Runs the intelligence brief generation DSPy signature.

Mirrors `app.extraction.service.ExtractionService`'s shape, sharing the
same lazily-configured global DSPy/MLflow runtime (see
`app.extraction.dspy_runtime`) so both signatures run against one
consistent LM/adapter configuration per process.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

import dspy
import mlflow

from app.core.config import Settings, get_settings
from app.extraction.brief import IntelligenceBrief
from app.extraction.brief_signature import GenerateIntelligenceBrief
from app.extraction.dspy_runtime import DspyConfigurationError, ensure_dspy_configured


class BriefGenerationError(Exception):
    """Raised when DSPy configuration or a brief generation call fails."""


class BriefGenerationService:
    """Configures and runs the DSPy intelligence-brief generation pipeline."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        """Initializes the service.

        Args:
            settings: Application settings to configure DSPy/MLflow
                from. Defaults to the process-wide cached `Settings`
                instance.
        """
        self._settings = settings or get_settings()
        self._predictor: Optional[dspy.Predict] = None

    def _ensure_predictor(self) -> dspy.Predict:
        """Ensures DSPy is configured and this service's predictor exists.

        Returns:
            The `dspy.Predict(GenerateIntelligenceBrief)` instance.

        Raises:
            BriefGenerationError: If DSPy configuration fails.
        """
        if self._predictor is None:
            try:
                ensure_dspy_configured(self._settings)
            except DspyConfigurationError as exc:
                raise BriefGenerationError(str(exc)) from exc
            self._predictor = dspy.Predict(GenerateIntelligenceBrief)
        return self._predictor

    def generate(
        self,
        operation_type: str,
        vessel_type: str,
        incident_count: int,
        total_injuries: int,
        total_fatalities: int,
        year_range: str,
        top_causal_signature: str,
        most_representative_report_id: int,
        reports_context: str,
        mlflow_experiment_name: Optional[str] = None,
    ) -> IntelligenceBrief:
        """Runs one operation/vessel combination through brief generation.

        Args:
            operation_type: The operation type this brief covers.
            vessel_type: The vessel class this brief covers.
            incident_count: Total number of matching reports.
            total_injuries: Summed injuries across matching reports.
            total_fatalities: Summed fatalities across matching reports.
            year_range: Earliest-to-latest incident year span, as text.
            top_causal_signature: The most frequent causal signature label.
            most_representative_report_id: Highest-confidence report id
                within the top causal-signature group.
            reports_context: Formatted per-report context text (see
                `app.briefs.context_builder.build_reports_context`).
            mlflow_experiment_name: MLflow experiment to log this call
                under. Defaults to `Settings.MLFLOW_EXPERIMENT_NAME`.

        Returns:
            The validated `IntelligenceBrief` produced by the model.

        Raises:
            BriefGenerationError: If DSPy configuration or the
                generation call itself fails, or returns no usable
                prediction.
        """
        predictor = self._ensure_predictor()
        mlflow.set_experiment(
            mlflow_experiment_name or self._settings.MLFLOW_EXPERIMENT_NAME
        )

        try:
            prediction = predictor(
                operation_type=operation_type,
                vessel_type=vessel_type,
                incident_count=incident_count,
                total_injuries=total_injuries,
                total_fatalities=total_fatalities,
                year_range=year_range,
                top_causal_signature=top_causal_signature,
                most_representative_report_id=most_representative_report_id,
                reports_context=reports_context,
            )
        except Exception as exc:  # noqa: BLE001
            raise BriefGenerationError(
                f"DSPy brief generation call raised: {exc}"
            ) from exc

        if prediction is None or not hasattr(prediction, "brief"):
            raise BriefGenerationError(
                "DSPy brief generation returned no usable prediction -- check "
                "MLflow traces for the underlying LM error."
            )
        return prediction.brief


@lru_cache
def get_brief_generation_service() -> BriefGenerationService:
    """Returns the process-wide `BriefGenerationService` singleton.

    Returns:
        A lazily-configured `BriefGenerationService`, cached per process.
    """
    return BriefGenerationService()
