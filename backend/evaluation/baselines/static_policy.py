"""
Baseline A: Static Resource Allocation Policy.
Fixed replica count; zero dynamic reactions to workload changes.
"""

from .base_policy import BaseScalingPolicy
from ..models import NormalizedObservation, PolicyRecommendation, ScalingAction, PolicyType


class StaticPolicy(BaseScalingPolicy):
    """
    Baseline A: Static Resource Allocation.
    Maintains fixed initial replica count across all conditions.
    """

    def __init__(self, initial_replicas: int = 1):
        super().__init__(
            policy_type=PolicyType.STATIC,
            min_replicas=initial_replicas,
            max_replicas=initial_replicas,
            initial_replicas=initial_replicas
        )

    def evaluate(self, observation: NormalizedObservation) -> PolicyRecommendation:
        curr = self.get_current_replicas(observation.service_name)
        rec = PolicyRecommendation(
            policy_type=self.policy_type,
            service_name=observation.service_name,
            timestamp=observation.timestamp,
            elapsed_seconds=observation.elapsed_seconds,
            action=ScalingAction.HOLD,
            current_replicas=curr,
            target_replicas=curr,
            replica_delta=0,
            reason="Static allocation: replicas fixed at baseline",
            trigger_metric=None,
            metric_value=None,
            is_bottleneck=False
        )
        self.record_recommendation(rec)
        return rec

