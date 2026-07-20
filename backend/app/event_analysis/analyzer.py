"""Orchestrates the full event-trajectory analysis pipeline.

Three steps, each independently callable (and independently tested):
classify the free-text description (Step A), query and bucket matching
reports by severity (Step B), then compare the fatal and near-miss
groups to find the barrier condition and recommend one action (Steps
D+E). Step C (the sequence display) is pure frontend rendering of
`TrajectoryBuckets`' counts -- nothing to orchestrate here.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import vocab_crud
from app.event_analysis.context_builder import build_group_context
from app.event_analysis.trajectory import TrajectoryBuckets, get_trajectory_buckets
from app.extraction.event_analysis import EventAnalysisFindings, EventClassification
from app.extraction.event_analysis_service import (
    get_barrier_finding_service,
    get_event_classification_service,
)


async def classify_event(
    session: AsyncSession, description: str, mlflow_experiment_name: Optional[str] = None
) -> EventClassification:
    """Step A: classifies a free-text event description.

    Args:
        session: Active async DB session (used only to fetch the
            current open-vocabulary lists to match against).
        description: The user's free-text event description.
        mlflow_experiment_name: Optional MLflow experiment name override.

    Returns:
        The classified operation type, vessel type, summary, and severity stage.

    Raises:
        app.extraction.event_analysis_service.EventAnalysisError: If the
            underlying DSPy call fails.
    """
    vocab = await vocab_crud.get_vocabulary_for_signature(session)
    service = get_event_classification_service()
    return service.classify(
        description,
        operation_types=vocab.get("operation_types", []),
        vessel_types=vocab.get("vessel_types", []),
        mlflow_experiment_name=mlflow_experiment_name,
    )


async def map_trajectory(
    session: AsyncSession, operation_type: str, vessel_type: str, description: str
) -> TrajectoryBuckets:
    """Step B: finds every matching report, bucketed by severity outcome.

    Matches on two sources: an exact operation_type/vessel_type match,
    and a semantic similarity match against the raw description -- see
    `app.event_analysis.trajectory.get_trajectory_buckets`.

    Args:
        session: Active async DB session.
        operation_type: The classified operation type to match exactly.
        vessel_type: The classified vessel type to match exactly.
        description: The user's raw event description, used for the
            semantic match (not Step A's cleaned-up summary -- the
            rawest, most direct signal of intent).

    Returns:
        The matching reports, sorted into near_miss/serious/fatal
        buckets, each tagged with how it matched.
    """
    return await get_trajectory_buckets(session, operation_type, vessel_type, description)


def find_barrier(
    description: str,
    classification: EventClassification,
    buckets: TrajectoryBuckets,
    mlflow_experiment_name: Optional[str] = None,
) -> EventAnalysisFindings:
    """Steps D+E: finds the barrier condition and recommends one action.

    Args:
        description: The user's original free-text event description.
        classification: The Step A classification result.
        buckets: The Step B trajectory buckets.
        mlflow_experiment_name: Optional MLflow experiment name override.

    Returns:
        The barrier finding and recommended action, each with citations.

    Raises:
        app.extraction.event_analysis_service.EventAnalysisError: If the
            underlying DSPy call fails.
    """
    described_event = (
        f"Original description: {description}\n"
        f"Classified summary: {classification.event_summary}\n"
        f"Operation type: {classification.operation_type}\n"
        f"Vessel type: {classification.vessel_type}\n"
        f"This event's own severity stage: {classification.severity_stage}"
    )
    near_miss_context = build_group_context(buckets.near_miss)
    fatal_context = build_group_context(buckets.fatal)

    service = get_barrier_finding_service()
    return service.find_barrier(
        described_event=described_event,
        near_miss_context=near_miss_context,
        fatal_context=fatal_context,
        near_miss_count=buckets.near_miss_count,
        serious_count=buckets.serious_count,
        fatal_count=buckets.fatal_count,
        mlflow_experiment_name=mlflow_experiment_name,
    )
