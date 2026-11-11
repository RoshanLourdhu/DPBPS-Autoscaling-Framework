"""
Baseline B: Conventional CPU-Threshold Reactive Scaling Policy.
Evaluates CPU utilization against static high (70%) and low (30%) watermarks.
"""

from typing import Dict, List
from .base_policy import BaseScalingPolicy
from ..models import NormalizedObservation, PolicyRecommendation, ScalingAction, PolicyType


class CPUThresholdPolicy(BaseScalingPolicy):
    """
    Baseline B: CPU-Threshold Reactive Scaling.
    
    Parameters:
    - Scale-Up Threshold: CPU utilization > 0.70 (70%)
    - Scale-Down Threshold: CPU utilization < 0.30 (30%)
    - Sustained Condition: 2 consecutive observations above/below threshold
    - Cooldown: 30 seconds between scaling actions
    - Max Replica Delta: 2 replicas per step
    - Min Replicas: 1, Max Replicas: 10
    """

    def __init__(
        self,
        scale_up_threshold: float = 0.70,
        scale_down_threshold: float = 0.30,
        cooldown_sec: float = 30.0,
        consecutive_required: int = 2,
        max_step_change: int = 2,
        min_replicas: int = 1,
        max_replicas: int = 10,
        initial_replicas: int = 1
    ):
        super().__init__(
            policy_type=PolicyType.CPU_THRESHOLD,
            min_replicas=min_replicas,
            max_replicas=max_replicas,
            initial_replicas=initial_replicas
        )
        self.scale_up_threshold = scale_up_threshold
        self.scale_down_threshold = scale_down_threshold
        self.cooldown_sec = cooldown_sec
        self.consecutive_required = consecutive_required
        self.max_step_change = max_step_change
        
        # Track consecutive violations
        self.high_cpu_consecutive: Dict[str, int] = {}
        self.low_cpu_consecutive: Dict[str, int] = {}

    def reset(self) -> None:
        super().reset()
        self.high_cpu_consecutive.clear()
        self.low_cpu_consecutive.clear()

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
                reason="Telemetry unpopulated: skipping CPU threshold check",
                trigger_metric="cpu_utilization_ratio",
                metric_value=None
            )
            self.record_recommendation(rec)
            return rec

        cpu_util = observation.cpu_utilization_ratio

        # Update consecutive counters
        if cpu_util > self.scale_up_threshold:
            self.high_cpu_consecutive[svc] = self.high_cpu_consecutive.get(svc, 0) + 1
            self.low_cpu_consecutive[svc] = 0
        elif cpu_util < self.scale_down_threshold:
            self.low_cpu_consecutive[svc] = self.low_cpu_consecutive.get(svc, 0) + 1
            self.high_cpu_consecutive[svc] = 0
        else:
            self.high_cpu_consecutive[svc] = 0
            self.low_cpu_consecutive[svc] = 0

        # Check cooldown
        last_scale = self.last_scale_time.get(svc, -999.0)
        in_cooldown = (t - last_scale) < self.cooldown_sec

        # Evaluate Scale-Up
        if self.high_cpu_consecutive.get(svc, 0) >= self.consecutive_required:
            if in_cooldown:
                reason = f"CPU utilization ({cpu_util*100:.1f}%) > {self.scale_up_threshold*100:.0f}%, but in cooldown ({t - last_scale:.1f}s < {self.cooldown_sec}s)"
                action = ScalingAction.HOLD
                target = curr
                delta = 0
            elif curr >= self.max_replicas:
                reason = f"CPU utilization ({cpu_util*100:.1f}%) > {self.scale_up_threshold*100:.0f}%, but already at max replicas ({self.max_replicas})"
                action = ScalingAction.HOLD
                target = curr
                delta = 0
            else:
                # Calculate scale-up delta (1 or 2 replicas based on severity)
                step = 2 if cpu_util > (self.scale_up_threshold + 0.30) else 1
                step = min(step, self.max_step_change)
                target = min(self.max_replicas, curr + step)
                delta = target - curr
                action = ScalingAction.SCALE_UP
                reason = f"High CPU utilization sustained ({cpu_util*100:.1f}% > {self.scale_up_threshold*100:.0f}% for {self.consecutive_required} cycles): scaling up by {delta}"
                self.high_cpu_consecutive[svc] = 0  # reset after action

        # Evaluate Scale-Down
        elif self.low_cpu_consecutive.get(svc, 0) >= self.consecutive_required:
            if in_cooldown:
                reason = f"CPU utilization ({cpu_util*100:.1f}%) < {self.scale_down_threshold*100:.0f}%, but in cooldown ({t - last_scale:.1f}s < {self.cooldown_sec}s)"
                action = ScalingAction.HOLD
                target = curr
                delta = 0
            elif curr <= self.min_replicas:
                reason = f"CPU utilization ({cpu_util*100:.1f}%) < {self.scale_down_threshold*100:.0f}%, but already at min replicas ({self.min_replicas})"
                action = ScalingAction.HOLD
                target = curr
                delta = 0
            else:
                step = 1
                target = max(self.min_replicas, curr - step)
                delta = target - curr
                action = ScalingAction.SCALE_DOWN
                reason = f"Low CPU utilization sustained ({cpu_util*100:.1f}% < {self.scale_down_threshold*100:.0f}% for {self.consecutive_required} cycles): scaling down by {abs(delta)}"
                self.low_cpu_consecutive[svc] = 0

        else:
            action = ScalingAction.HOLD
            target = curr
            delta = 0
            reason = f"CPU utilization ({cpu_util*100:.1f}%) within acceptable operational band [{self.scale_down_threshold*100:.0f}% - {self.scale_up_threshold*100:.0f}%]"

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
            is_bottleneck=False
        )
        self.record_recommendation(rec)
        return rec

