"""DSPy extraction service.

Configures the DSPy LM, structured-output adapter, and MLflow
autologging from `Settings` (rather than reading `os.environ` directly
and configuring `dspy.settings` as an import-time side effect), and runs
`report_text` + the current open-vocabulary lists through
`ExtractMaritimeReport`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

import dspy
import mlflow

from app.core.config import Settings, get_settings
from app.extraction.dspy_runtime import DspyConfigurationError, ensure_dspy_configured
from app.extraction.incident import MaritimeIncident
from app.extraction.signature import ExtractMaritimeReport


class ExtractionError(Exception):
    """Raised when DSPy configuration or an extraction call fails."""


class ExtractionService:
    """Configures and runs the DSPy maritime-incident extraction pipeline.

    DSPy/MLflow global configuration happens lazily, on first use, via
    `app.extraction.dspy_runtime.ensure_dspy_configured` -- shared with
    every other DSPy-based service in this app (e.g. brief generation)
    so there is exactly one LM/adapter configuration for the whole
    process, not one per service.
    """

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
            The `dspy.Predict(ExtractMaritimeReport)` instance.

        Raises:
            ExtractionError: If DSPy configuration fails.
        """
        if self._predictor is None:
            try:
                ensure_dspy_configured(self._settings)
            except DspyConfigurationError as exc:
                raise ExtractionError(str(exc)) from exc
            self._predictor = dspy.Predict(ExtractMaritimeReport)
        return self._predictor

    def extract(
        self,
        report_text: str,
        vocabulary: dict[str, list[str]],
        mlflow_experiment_name: Optional[str] = None,
    ) -> MaritimeIncident:
        """Runs one document through the extraction pipeline.

        Args:
            report_text: The parsed source document text (with page
                markers where available -- see
                `app.ingestion.parsing.parse_document_to_text`).
            vocabulary: Current open-vocabulary lists, keyed exactly as
                `ExtractMaritimeReport` expects: "operation_types",
                "vessel_types", "root_cause_signatures" (see
                `app.db.crud.vocab.get_vocabulary_for_signature`).
            mlflow_experiment_name: MLflow experiment to log this call
                under. Defaults to `Settings.MLFLOW_EXPERIMENT_NAME`.

        Returns:
            The validated `MaritimeIncident` produced by the model.

        Raises:
            ExtractionError: If DSPy configuration or the extraction
                call itself fails, or returns no usable prediction.
        """
        predictor = self._ensure_predictor()

        mlflow.set_experiment(
            mlflow_experiment_name or self._settings.MLFLOW_EXPERIMENT_NAME
        )

        example = dspy.Example(
            report_text=report_text,
            operation_types=vocabulary.get("operation_types", []),
            vessel_types=vocabulary.get("vessel_types", []),
            root_cause_signatures=vocabulary.get("root_cause_signatures", []),
        ).with_inputs(
            "report_text", "operation_types", "vessel_types", "root_cause_signatures"
        )

        try:
            predictions = predictor.batch(
                [example],
                num_threads=self._settings.DSPY_NUM_THREADS,
                provide_traceback=True,
                timeout=self._settings.DSPY_BATCH_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001
            raise ExtractionError(f"DSPy extraction call raised: {exc}") from exc

        if (
            not predictions
            or predictions[0] is None
            or not hasattr(predictions[0], "extracted_data")
        ):
            raise ExtractionError(
                "DSPy extraction returned no usable prediction -- check worker "
                "logs / MLflow traces for the underlying LM error."
            )

        return predictions[0].extracted_data


@lru_cache
def get_extraction_service() -> ExtractionService:
    """Returns the process-wide `ExtractionService` singleton.

    Returns:
        A lazily-configured `ExtractionService`, cached per process so
        DSPy/MLflow are only configured once.
    """
    return ExtractionService()


def extract_report(
    report_text: str,
    vocabulary: dict[str, list[str]],
    mlflow_experiment_name: Optional[str] = None,
) -> MaritimeIncident:
    """Runs one document through the process-wide extraction service.

    Args:
        report_text: The parsed source document text.
        vocabulary: Current open-vocabulary lists for the signature's
            list-valued input fields.
        mlflow_experiment_name: Optional MLflow experiment name override.

    Returns:
        The validated `MaritimeIncident` produced by the model.

    Raises:
        ExtractionError: See `ExtractionService.extract`.
    """
    return get_extraction_service().extract(
        report_text, vocabulary, mlflow_experiment_name
    )
