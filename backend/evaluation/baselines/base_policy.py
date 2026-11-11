"""
Abstract Base Class for offline scaling evaluation policies.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from ..models import NormalizedObservation, PolicyRecommendation, ScalingAction, PolicyType


class BaseScalingPolicy(ABC):
    """
    Abstract interface for scaling policies in the trace-replay evaluator.
    Maintains simulated replica state per service during offline evaluation.
    """

    def __init__(
        self,
        policy_type: PolicyType,
        min_replicas: int = 1,
        max_replicas: int = 10,
        initial_replicas: int = 1
    ):
        self.policy_type = policy_type
        self.min_replicas = min_replicas
        self.max_replicas = max_replicas
        self.initial_replicas = initial_replicas
        
        # State tracking per service
        self.service_replicas: Dict[str, int] = {}
        self.last_scale_time: Dict[str, float] = {}
        self.recommendation_history: Dict[str, List[PolicyRecommendation]] = {}

    def reset(self) -> None:
        """Reset internal state between experiments."""
        self.service_replicas.clear()
        self.last_scale_time.clear()
        self.recommendation_history.clear()

    def get_current_replicas(self, service_name: str) -> int:
        """Retrieve current simulated replica count for a service."""
        return self.service_replicas.get(service_name, self.initial_replicas)

    def set_current_replicas(self, service_name: str, count: int) -> None:
        """Update simulated replica count within bounds."""
        bounded = max(self.min_replicas, min(self.max_replicas, count))
        self.service_replicas[service_name] = bounded

    def record_recommendation(self, rec: PolicyRecommendation) -> None:
        """Record recommendation and update replica state."""
        svc = rec.service_name
        if svc not in self.recommendation_history:
            self.recommendation_history[svc] = []
        self.recommendation_history[svc].append(rec)
        
        # In offline trace-replay simulation, we update the policy's view of current replicas
        if rec.action in (ScalingAction.SCALE_UP, ScalingAction.SCALE_DOWN):
            self.set_current_replicas(svc, rec.target_replicas)
            self.last_scale_time[svc] = rec.elapsed_seconds

    @abstractmethod
    def evaluate(self, observation: NormalizedObservation) -> PolicyRecommendation:
        """
        Evaluate a single service telemetry observation and return a scaling recommendation.
        """
        pass

