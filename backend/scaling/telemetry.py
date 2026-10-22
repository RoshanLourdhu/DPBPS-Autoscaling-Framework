# backend/scaling/telemetry.py
"""Utility functions for telemetry validation and freshness checking."""

from datetime import datetime, timezone
from .models import TelemetryInput, ScalingConfig


def is_fresh(telemetry: TelemetryInput, config: ScalingConfig) -> bool:
    """Return True if the telemetry timestamp is within the configured freshness window.

    The timestamp is assumed to be UTC. ``config.telemetry_freshness_sec`` defines the
    maximum age in seconds a sample may have before it is considered stale.
    """
    now = datetime.now(timezone.utc)
    age = (now - telemetry.timestamp).total_seconds()
    return age <= config.telemetry_freshness_sec
