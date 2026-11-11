"""
Data models for experiment management and execution lifecycle.

Tracks experiment status, metadata, configurations, and safety constraints.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.workload.models import WorkloadProfileConfig, WorkloadProfileName


class ExperimentStatus(str, Enum):
    """
    Standard experiment lifecycle states.
    
    In Stage 7, experiments can only reach CREATED or READY.
    Transitions to RUNNING are strictly disabled.
    """
    CREATED = "CREATED"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


# Allowed state transitions
VALID_STATE_TRANSITIONS = {
    ExperimentStatus.CREATED: {ExperimentStatus.READY, ExperimentStatus.STOPPED, ExperimentStatus.FAILED},
    ExperimentStatus.READY: {ExperimentStatus.CREATED, ExperimentStatus.RUNNING, ExperimentStatus.STOPPED, ExperimentStatus.FAILED},
    ExperimentStatus.RUNNING: {ExperimentStatus.COMPLETED, ExperimentStatus.STOPPED, ExperimentStatus.FAILED},
    ExperimentStatus.COMPLETED: set(),  # Terminal
    ExperimentStatus.STOPPED: set(),    # Terminal
    ExperimentStatus.FAILED: set(),     # Terminal
}


class ExperimentMetadata(BaseModel):
    """Full metadata record for a prepared or historical experiment."""
    experiment_id: str = Field(..., description="Unique experiment identifier")
    profile_name: WorkloadProfileName = Field(..., description="Selected workload profile")
    configuration: WorkloadProfileConfig = Field(..., description="Validated workload configuration")
    application_entry_point: str = Field(default="http://frontend.online-boutique.svc.cluster.local:80")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC timestamp of experiment creation",
    )
    start_timestamp: Optional[str] = Field(default=None, description="UTC start time if executed")
    end_timestamp: Optional[str] = Field(default=None, description="UTC end time if completed/stopped")
    status: ExperimentStatus = Field(default=ExperimentStatus.CREATED, description="Lifecycle status")
    selected_concurrency: int = Field(default=10, description="Configured peak concurrent users")
    target_request_rate: Optional[float] = Field(default=None, description="Expected target RPS")
    actual_observed_request_rate: Optional[float] = Field(default=None, description="Observed RPS from telemetry")
    failure_information: Optional[str] = Field(default=None, description="Error or rejection reason if failed")
    execution_disabled: bool = Field(default=True, description="Safety guard: True when execution is forbidden")
    tags: List[str] = Field(default_factory=list, description="Categorization tags")
    notes: Optional[str] = Field(default=None, description="Operator notes or test hypothesis")


class ExperimentCreateRequest(BaseModel):
    """Request payload for creating a new experiment record."""
    profile_name: WorkloadProfileName
    custom_configuration: Optional[WorkloadProfileConfig] = None
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class ExperimentValidationResponse(BaseModel):
    """Response returned when validating an experiment configuration."""
    valid: bool
    errors: List[str] = Field(default_factory=list)
    profile_name: WorkloadProfileName
    safety_checks_passed: bool
    configuration: Optional[WorkloadProfileConfig] = None

