"""Shared DSPy/MLflow runtime configuration.

Every DSPy signature in this app (incident extraction, intelligence
brief generation) runs against the same global `dspy.settings` LM/
adapter configuration -- there is only one model/API key/adapter choice
for the whole app. This module configures that global state exactly
once per process, lazily, on first use by whichever service asks first.
"""

from __future__ import annotations

import dspy
import mlflow

from app.core.config import Settings

_configured = False


class DspyConfigurationError(Exception):
    """Raised when DSPy/MLflow global configuration fails."""


def ensure_dspy_configured(settings: Settings) -> None:
    """Configures DSPy's global LM/adapter and MLflow autologging, once.

    Idempotent at the process level: only the first call (across every
    caller) actually configures anything.

    Args:
        settings: Application settings to configure DSPy/MLflow from.

    Raises:
        DspyConfigurationError: If configuration fails (e.g. an invalid
            model string).
    """
    global _configured
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
