"""
Metric recording architecture for DPBPS experiment evaluation.

Defines schemas for capturing application, infrastructure, and DPBPS decision
telemetry snapshots during load-testing experiments.

Core invariants:
1. Missing telemetry remains None; never fabricate zero.
2. Timestamps are explicitly recorded in ISO-8601 UTC.
3. Telemetry preserves raw metrics and normalized units.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ApplicationServiceMetrics(BaseModel):
    """Application-level RPC metrics collected via Prometheus."""
    service_name: str
    request_rate: Optional[float] = Field(default=None, description="Requests per second (RPS)")
    p50_latency_ms: Optional[float] = Field(default=None, description="P50 latency in milliseconds")
    p95_latency_ms: Optional[float] = Field(default=None, description="P95 latency in milliseconds")
    p99_latency_ms: Optional[float] = Field(default=None, description="P99 latency in milliseconds")
    error_rate: Optional[float] = Field(default=None, description="Error fraction [0.0, 1.0]")
    telemetry_present: bool = Field(default=False, description="True if Prometheus metrics were returned")


class InfrastructureServiceMetrics(BaseModel):
    """Kubernetes pod and resource metrics collected via Metrics Server and K8s API."""
    service_name: str
    namespace: str = "online-boutique"
    current_replicas: int = Field(default=1, description="Desired/configured replica count")
    ready_replicas: int = Field(default=1, description="Ready and healthy replica count")
    observed_pods: int = Field(default=1, description="Pods observed by controller")
    cpu_usage_millicores: Optional[float] = None
    memory_usage_mib: Optional[float] = None
    cpu_utilization_fraction: Optional[float] = Field(default=None, description="Normalized [0.0, 1.0]")
    memory_utilization_fraction: Optional[float] = Field(default=None, description="Normalized [0.0, 1.0]")
    deployment_status: str = "HEALTHY"


class DPBPSDecisionMetrics(BaseModel):
    """DPBPS controller decision and actuation records."""
    service_name: str
    action: str = Field(..., description="SCALE_UP, SCALE_DOWN, HOLD, INSUFFICIENT_TELEMETRY")
    previous_replicas: int
    proposed_replicas: int
    detected_bottleneck: Optional[str] = None
    bottleneck_rank: int = 0
    downstream_impact: float = 0.0
    deployment_phase: str = "NORMAL_OPERATION"
    actuator_status: str = Field(default="SKIPPED", description="VALIDATED, SKIPPED, REJECTED")
    decision_reason: str = ""
    cluster_modified: bool = False


class ExperimentMetricSnapshot(BaseModel):
    """Consolidated metric sample taken at a specific point in time during an experiment."""
    experiment_id: str
    snapshot_index: int
    timestamp_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    elapsed_seconds: float = 0.0
    application_metrics: Dict[str, ApplicationServiceMetrics] = Field(default_factory=dict)
    infrastructure_metrics: Dict[str, InfrastructureServiceMetrics] = Field(default_factory=dict)
    dpbps_metrics: Dict[str, DPBPSDecisionMetrics] = Field(default_factory=dict)


class ExperimentMetricsCollection(BaseModel):
    """Collection of metric snapshots for a specific experiment run."""
    experiment_id: str
    profile_name: str
    start_timestamp: Optional[str] = None
    end_timestamp: Optional[str] = None
    total_snapshots: int = 0
    snapshots: List[ExperimentMetricSnapshot] = Field(default_factory=list)

