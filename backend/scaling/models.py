# backend/scaling/models.py
"""Pydantic models and enums for DPBPS scaling controller."""

from enum import Enum
from typing import List, Optional, Dict
from pydantic import BaseModel, Field, validator
from datetime import datetime, timezone


class DeploymentPhase(str, Enum):
    NORMAL_OPERATION = "NORMAL_OPERATION"
    PRE_DEPLOYMENT = "PRE_DEPLOYMENT"
    ACTIVE_DEPLOYMENT = "ACTIVE_DEPLOYMENT"
    POST_DEPLOYMENT = "POST_DEPLOYMENT"


class DecisionAction(str, Enum):
    SCALE_UP = "SCALE_UP"
    SCALE_DOWN = "SCALE_DOWN"
    HOLD = "HOLD"
    INSUFFICIENT_TELEMETRY = "INSUFFICIENT_TELEMETRY"


class TelemetryInput(BaseModel):
    service_name: str = Field(..., description="Unique service identifier")
    request_rate: float = Field(..., ge=0)
    p95_latency: float = Field(..., ge=0)
    error_rate: float = Field(..., ge=0)
    cpu_utilisation: float = Field(..., ge=0, le=1)
    memory_utilisation: float = Field(..., ge=0, le=1)
    current_replicas: int = Field(..., ge=0)
    ready_replicas: Optional[int] = Field(None, ge=0)
    timestamp: datetime = Field(..., description="ISO‑8601 timestamp of the metric sample")
    dependencies: List[str] = Field(default_factory=list, description="Names of services this service depends on")

    @validator("timestamp")
    def ensure_timestamp_not_future(cls, v: datetime) -> datetime:
        # Compare using timezone-aware UTC timestamps
        now = datetime.now(timezone.utc)
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        if v > now:
            raise ValueError("timestamp cannot be in the future")
        return v


class DecisionOutput(BaseModel):
    service_name: str
    action: DecisionAction
    previous_replicas: int
    requested_replicas: int
    priority_score: Optional[float] = None
    phase: DeploymentPhase
    bottleneck: Optional[str] = None
    reason: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    simulated: bool = True


class ScalingConfig(BaseModel):
    strategy: str = "simulation"
    min_replicas: int = 1
    max_replicas: int = 10
    cpu_threshold: float = 0.8
    memory_threshold: float = 0.8
    latency_target_ms: float = 200.0
    scale_up_window_sec: int = 30
    scale_down_window_sec: int = 120
    cooldown_sec: int = 15
    telemetry_freshness_sec: int = 30
    max_replica_change: int = 2
    scale_down_stabilization_sec: int = 60
    # Additional weights for scoring – these are provisional and may be tuned later.
    weight_cpu: float = 0.4
    weight_memory: float = 0.2
    weight_latency: float = 0.3
    weight_error: float = 0.1

