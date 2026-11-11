"""
Workload profile data models for DPBPS load testing preparation.

Defines the six canonical workload profiles, stage configurations, and safety constraints.
All traffic configurations are validated against safe limits to prevent cluster instability.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class WorkloadProfileName(str, Enum):
    """The six canonical DPBPS evaluation workload profiles."""
    NORMAL_TRAFFIC = "NORMAL_TRAFFIC"
    GRADUAL_TRAFFIC_INCREASE = "GRADUAL_TRAFFIC_INCREASE"
    SUDDEN_TRAFFIC_SPIKE = "SUDDEN_TRAFFIC_SPIKE"
    SUSTAINED_HIGH_TRAFFIC = "SUSTAINED_HIGH_TRAFFIC"
    TRAFFIC_DECREASE = "TRAFFIC_DECREASE"
    BURSTY_TRAFFIC = "BURSTY_TRAFFIC"


class WorkloadStage(BaseModel):
    """A distinct time-bound stage within a stepped or multi-phase workload profile."""
    stage_index: int = Field(..., ge=0, description="Sequential stage index (0-based)")
    name: str = Field(..., description="Descriptive stage name (e.g. 'Warmup', 'Step 1', 'Peak')")
    target_users: int = Field(..., ge=0, le=200, description="Target concurrent user count")
    duration_seconds: int = Field(..., ge=1, le=600, description="Duration of this stage in seconds")
    spawn_rate: float = Field(default=2.0, gt=0.0, le=50.0, description="Users spawned per second")
    description: Optional[str] = Field(default=None, description="Stage rationale and expected behavior")


class WorkloadProfileConfig(BaseModel):
    """
    Configuration for an independently selectable workload profile.
    
    Safety guardrails:
    - users: capped at 200 concurrent users to protect Docker Desktop memory.
    - spawn_rate: capped at 50 users/sec.
    - total_duration_seconds: capped at 1200 seconds (20 minutes).
    """
    profile_name: WorkloadProfileName = Field(..., description="Canonical profile identifier")
    display_name: str = Field(..., description="Human-readable profile title")
    description: str = Field(..., description="Detailed profile purpose and characteristics")
    target_host: str = Field(default="frontend:80", description="Target application entry point")
    users: int = Field(default=10, ge=1, le=200, description="Peak or steady-state concurrent users")
    spawn_rate: float = Field(default=2.0, gt=0.0, le=50.0, description="Rate of user arrival per second")
    ramp_up_seconds: int = Field(default=10, ge=0, le=300, description="Ramp-up duration in seconds")
    steady_state_seconds: int = Field(default=120, ge=1, le=600, description="Steady-state duration in seconds")
    ramp_down_seconds: int = Field(default=10, ge=0, le=300, description="Ramp-down duration in seconds")
    total_duration_seconds: int = Field(default=140, ge=10, le=1200, description="Total profile execution duration")
    stages: List[WorkloadStage] = Field(default_factory=list, description="Ordered stages for stepped/bursty profiles")
    expected_observations: List[str] = Field(default_factory=list, description="Expected metric patterns and DPBPS responses")
    custom_parameters: Dict[str, Any] = Field(default_factory=dict, description="Profile-specific tuning parameters")

    @field_validator("total_duration_seconds")
    @classmethod
    def validate_duration(cls, v: int, info) -> int:
        if v < 10:
            raise ValueError("Total duration must be at least 10 seconds")
        return v

