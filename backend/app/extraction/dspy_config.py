"""Shared DSPy/MLflow configuration.

Both `app.extraction.service.ExtractionService` and
`app.extraction.brief_service.BriefGenerationService` run `dspy.Predict`
calls against the same global DSPy LM configuration -- this module holds
that configuration logic in one place so it happens exactly once per
process, however many DSPy-backed services end up using it.
"""

from __future__ import annotations

import threading

import dspy
import mlflow

from app.core.config import Settings

_lock = threading.Lock()
_configured = False


class DspyConfigurationError(Exception):
    """Raised when configuring DSPy's global LM/adapter or MLflow fails."""


def ensure_dspy_configured(settings: Settings) -> None:
    """Configures DSPy's global LM/adapter and MLflow autologging, once per process.

    Thread-safe and idempotent: only the first call (across all threads)
    actually configures anything.

    Args:
        settings: Application settings to configure DSPy/MLflow from.

    Raises:
        DspyConfigurationError: If configuration fails (e.g. an invalid
            model string).
    """
    global _configured
    if _configured:
        return

    with _lock:
        if _configured:
            return
        try:
            mlflow.dspy.autolog(
                log_traces=settings.MLFLOW_LOG_TRACES,
                log_traces_from_compile=settings.MLFLOW_LOG_TRACES_FROM_COMPILE,
                log_traces_from_eval=settings.MLFLOW_LOG_TRACES_FROM_EVAL,
                log_compiles=settings.MLFLOW_LOG_COMPILES,
                log_evals=settings.MLFLOW_LOG_EVALS,
            )
            if settings.MLFLOW_TRACKING_URI:
                mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)

            dspy.settings.configure(
                lm=dspy.LM(
                    model=settings.MODEL,
                    api_base=settings.API_BASE or None,
                    api_key=settings.API_KEY or None,
                    max_retries=settings.DSPY_LM_MAX_RETRIES,
                ),
                adapter=dspy.JSONAdapter() if settings.DSPY_ADAPTER == "json" else None,
            )
            _configured = True
        except Exception as exc:  # noqa: BLE001 - surface any config error uniformly
            raise DspyConfigurationError(f"Failed to configure DSPy: {exc}") from exc
