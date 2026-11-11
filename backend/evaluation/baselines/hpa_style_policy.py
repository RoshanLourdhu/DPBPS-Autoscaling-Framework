"""
Baseline C: Conventional Kubernetes HPA-Style Reactive Policy.
Mathematical approximation of Kubernetes Horizontal Pod Autoscaler algorithm.
"""

import math
from typing import Dict, List, Tuple
from .base_policy import BaseScalingPolicy
from ..models import NormalizedObservation, PolicyRecommendation, ScalingAction, PolicyType


class HPAStylePolicy(BaseScalingPolicy):
    """
    Baseline C: Conventional Kubernetes HPA-Style Policy.
    
    Mathematical Formulation:
      desiredReplicas = ceil[ currentReplicas * ( currentMetricValue / desiredMetricValue ) ]
      
    Parameters:
    - Target CPU Utilization: 0.70 (70%)
    - Tolerance Band: 0.10 (+/- 10% around target -> [63%, 77%])
    - Scale-Down Stabilization Window: 60 seconds (proposals held until window expires)
    - Scale-Up Stabilization Window: 0 seconds (scale-up takes precedence immediately)
    - Max Scale-Up Rate: 2x current replicas or +4 (whichever is smaller)
    - Min Replicas: 1, Max Replicas: 10
    """

    def __init__(
        self,
        target_cpu_utilization: float = 0.70,
        tolerance: float = 0.10,
        scale_down_stabilization_sec: float = 60.0,
        min_replicas: int = 1,
        max_replicas: int = 10,
        initial_replicas: int = 1
    ):
        super().__init__(
            policy_type=PolicyType.HPA_STYLE,
            min_replicas=min_replicas,
            max_replicas=max_replicas,
            initial_replicas=initial_replicas
        )
        self.target_cpu_utilization = target_cpu_utilization
        self.tolerance = tolerance
        self.scale_down_stabilization_sec = scale_down_stabilization_sec
        
        # Track scale-down proposals with timestamps for stabilization: Dict[svc, List[(time, proposed_replicas)]]
        self.scale_down_proposals: Dict[str, List[Tuple[float, int]]] = {}

    def reset(self) -> None:
        super().reset()
        self.scale_down_proposals.clear()

    def evaluate(self, observation: NormalizedObservation) -> PolicyRecommendation:
        svc = observation.service_name
        curr = self.get_current_replicas(svc)
        t = observation.elapsed_seconds
        
        # Guard against unpopulated telemetry
        if not observation.telemetry_available:
            rec = PolicyRecommendation(
                policy_type=self.policy_type,
                service_name=svc,
                timestamp=observation.timestamp,
                elapsed_seconds=t,
                action=ScalingAction.INSUFFICIENT_DATA,
                current_replicas=curr,
                target_replicas=curr,
                replica_delta=0,
                reason="Telemetry unpopulated: HPA formula evaluation skipped",
                trigger_metric="cpu_utilization_ratio",
                metric_value=None
            )
            self.record_recommendation(rec)
            return rec

        cpu_util = observation.cpu_utilization_ratio
        
        # Tolerance check
        ratio = cpu_util / self.target_cpu_utilization
        if abs(1.0 - ratio) <= self.tolerance:
            action = ScalingAction.HOLD
            target = curr
            delta = 0
            reason = f"CPU utilization ({cpu_util*100:.1f}%) within +/-{self.tolerance*100:.0f}% tolerance band of target {self.target_cpu_utilization*100:.0f}%"
            # Clear scale-down proposals
            self.scale_down_proposals[svc] = []
        else:
            # HPA Core Formula: desired = ceil[ current * (current_util / target_util) ]
            raw_desired = math.ceil(curr * ratio)
            bounded_desired = max(self.min_replicas, min(self.max_replicas, raw_desired))

            if bounded_desired > curr:
                # Scale-Up: Takes effect immediately (clear scale-down stabilization)
                self.scale_down_proposals[svc] = []
                # Max scale-up rate constraint
                max_allowed = min(self.max_replicas, max(curr * 2, curr + 4))
                target = min(bounded_desired, max_allowed)
                delta = target - curr
                action = ScalingAction.SCALE_UP
                reason = f"HPA ratio={ratio:.2f} (CPU {cpu_util*100:.1f}% vs target {self.target_cpu_utilization*100:.0f}%): scaling up from {curr} to {target}"
            
            elif bounded_desired < curr:
                # Scale-Down: Enforce stabilization window
                if svc not in self.scale_down_proposals:
                    self.scale_down_proposals[svc] = []
                self.scale_down_proposals[svc].append((t, bounded_desired))
                
                # Prune proposals older than stabilization window
                cutoff = t - self.scale_down_stabilization_sec
                self.scale_down_proposals[svc] = [p for p in self.scale_down_proposals[svc] if p[0] >= cutoff]
                
                # Check if stabilization window has elapsed since first proposal
                first_time = self.scale_down_proposals[svc][0][0]
                window_elapsed = (t - first_time) >= self.scale_down_stabilization_sec

                if window_elapsed:
                    # Select max of desired replicas in window (standard HPA stabilization algorithm)
                    stabilized_target = max(p[1] for p in self.scale_down_proposals[svc])
                    if stabilized_target < curr:
                        target = stabilized_target
                        delta = target - curr
                        action = ScalingAction.SCALE_DOWN
                        reason = f"HPA scale-down stabilized over {self.scale_down_stabilization_sec:.0f}s: reducing from {curr} to {target}"
                        self.scale_down_proposals[svc] = []
                    else:
                        action = ScalingAction.HOLD
                        target = curr
                        delta = 0
                        reason = f"HPA scale-down stabilization selected {stabilized_target} >= current {curr}: HOLD"
                else:
                    action = ScalingAction.HOLD
                    target = curr
                    delta = 0
                    elapsed_win = t - first_time
                    reason = f"HPA scale-down proposed ({bounded_desired} < {curr}), but stabilizing ({elapsed_win:.1f}s / {self.scale_down_stabilization_sec:.0f}s)"
            else:
                action = ScalingAction.HOLD
                target = curr
                delta = 0
                reason = f"HPA desired replicas ({bounded_desired}) equals current replicas ({curr})"

        rec = PolicyRecommendation(
            policy_type=self.policy_type,
            service_name=svc,
            timestamp=observation.timestamp,
            elapsed_seconds=t,
            action=action,
            current_replicas=curr,
            target_replicas=target,
            replica_delta=delta,
            reason=reason,
            trigger_metric="cpu_utilization_ratio",
            metric_value=cpu_util,
            is_bottleneck=False,
            metadata={"hpa_ratio": ratio, "raw_desired": raw_desired if 'raw_desired' in locals() else curr}
        )
        self.record_recommendation(rec)
        return rec

