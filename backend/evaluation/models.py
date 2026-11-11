"""
Data models and evaluation structures for Stage 9 Comparative Evaluation.
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime


class PolicyType(str, Enum):
    STATIC = "STATIC"
    CPU_THRESHOLD = "CPU_THRESHOLD"
    HPA_STYLE = "HPA_STYLE"
    DPBPS = "DPBPS"


class ScalingAction(str, Enum):
    HOLD = "HOLD"
    SCALE_UP = "SCALE_UP"
    SCALE_DOWN = "SCALE_DOWN"
    NO_ACTION = "NO_ACTION"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class NormalizedObservation(BaseModel):
    """Normalized snapshot telemetry for a single microservice."""
    experiment_id: str
    service_name: str
    timestamp: str
    elapsed_seconds: float
    stage: Optional[str] = None
    
    # Workload & performance metrics
    request_rate: float = 0.0
    p50_latency_ms: Optional[float] = None
    p95_latency_ms: Optional[float] = None
    p99_latency_ms: Optional[float] = None
    error_rate: float = 0.0
    
    # Resource metrics
    cpu_usage_millicores: float = 0.0
    memory_usage_mib: float = 0.0
    cpu_utilization_ratio: float = 0.0  # 0.0 - 1.0+ (can exceed 1.0 if over request)
    memory_utilization_ratio: float = 0.0
    
    # Replicas
    current_replicas: int = 1
    ready_replicas: Optional[int] = 1
    
    # Health & metadata
    telemetry_available: bool = True
    dependencies: List[str] = Field(default_factory=list)
    deployment_phase: str = "NORMAL_OPERATION"


class PolicyRecommendation(BaseModel):
    """Standardized scaling recommendation issued by any policy."""
    policy_type: PolicyType
    service_name: str
    timestamp: str
    elapsed_seconds: float
    action: ScalingAction
    current_replicas: int
    target_replicas: int
    replica_delta: int = 0
    reason: str
    trigger_metric: Optional[str] = None
    metric_value: Optional[float] = None
    is_bottleneck: bool = False
    priority_score: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExperimentEvaluationSummary(BaseModel):
    """Summary of policy performance on a specific experiment."""
    experiment_id: str
    profile_name: str
    policy_type: PolicyType
    total_evaluations: int
    hold_count: int
    scale_up_count: int
    scale_down_count: int
    no_action_count: int
    
    # Latency to scale
    time_to_first_scale_up_sec: Optional[float] = None
    time_to_return_to_hold_sec: Optional[float] = None
    
    # Replica stats
    max_recommended_replicas: int
    min_recommended_replicas: int
    total_replica_increase: int
    total_replica_decrease: int
    recommendation_reversals: int
    repeated_service_recommendations: int
    
    # Service specific
    recommendations_by_service: Dict[str, Dict[str, int]] = Field(default_factory=dict)

