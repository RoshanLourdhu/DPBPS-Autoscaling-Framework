"""
DPBPS Policy Adapter for Comparative Evaluation.
Provides faithful evaluation using DPBPS controller logic and empirical decision traces.
"""

from typing import Dict, List, Optional
from datetime import datetime
from .baselines.base_policy import BaseScalingPolicy
from .models import NormalizedObservation, PolicyRecommendation, ScalingAction, PolicyType
from ..scaling.models import (
    TelemetryInput,
    DecisionOutput,
    DecisionAction,
    DeploymentPhase,
    ScalingConfig
)
from ..scaling.dpbps_controller import DPBPSController


class DPBPSAdapter(BaseScalingPolicy):
    """
    DPBPS Policy Adapter.
    Evaluates multi-dimensional telemetry (latency, CPU, memory, errors, dependencies, deployment phase)
    using the canonical DPBPS algorithm.
    """

    def __init__(
        self,
        config: Optional[ScalingConfig] = None,
        initial_replicas: int = 1,
        recorded_decisions: Optional[Dict[str, Dict[str, List[dict]]]] = None
    ):
        super().__init__(
            policy_type=PolicyType.DPBPS,
            min_replicas=config.min_replicas if config else 1,
            max_replicas=config.max_replicas if config else 10,
            initial_replicas=initial_replicas
        )
        self.config = config or ScalingConfig()
        self.controller = DPBPSController(self.config)
        self.recorded_decisions = recorded_decisions or {}
        self.active_experiment_id: Optional[str] = None

    def set_experiment(self, experiment_id: str) -> None:
        """Set current experiment context for empirical decision indexing."""
        self.active_experiment_id = experiment_id
        self.reset()
        self.controller = DPBPSController(self.config)

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
                reason="Insufficient or unpopulated telemetry: HOLD",
                trigger_metric="telemetry_available",
                metric_value=0.0,
                is_bottleneck=False
            )
            self.record_recommendation(rec)
            return rec

        # Check if empirical recorded decision exists for this experiment and cycle
        if self.active_experiment_id and self.active_experiment_id in self.recorded_decisions:
            exp_decs = self.recorded_decisions[self.active_experiment_id]
            # Match by approximate elapsed time or step
            svc_decs = exp_decs.get(svc, [])
            matched = None
            for d in svc_decs:
                if abs(d.get("elapsed_seconds", -999.0) - t) < 5.0:
                    matched = d
                    break
            
            if matched:
                act_str = matched.get("action", "HOLD")
                action = ScalingAction(act_str) if act_str in ScalingAction._value2member_map_ else ScalingAction.HOLD
                
                # In DPBPS controller, target is computed from recommendation
                if action == ScalingAction.SCALE_UP:
                    target = min(self.max_replicas, curr + 1)
                    delta = target - curr
                elif action == ScalingAction.SCALE_DOWN:
                    target = max(self.min_replicas, curr - 1)
                    delta = target - curr
                else:
                    target = curr
                    delta = 0

                rec = PolicyRecommendation(
                    policy_type=self.policy_type,
                    service_name=svc,
                    timestamp=observation.timestamp,
                    elapsed_seconds=t,
                    action=action,
                    current_replicas=curr,
                    target_replicas=target,
                    replica_delta=delta,
                    reason=matched.get("reason", "DPBPS evaluated empirical state"),
                    trigger_metric=matched.get("trigger_metric"),
                    metric_value=matched.get("metric_value"),
                    is_bottleneck=matched.get("is_bottleneck", False),
                    priority_score=matched.get("priority_score"),
                    metadata=matched.get("metadata", {})
                )
                self.record_recommendation(rec)
                return rec

        # Live DPBPS Controller fallback evaluation
        # Map NormalizedObservation to TelemetryInput
        try:
            ts_dt = datetime.fromisoformat(observation.timestamp.replace("Z", "+00:00"))
        except Exception:
            ts_dt = datetime.now()

        # Bounded utilization inputs [0, 1]
        cpu_u = min(1.0, max(0.0, observation.cpu_utilization_ratio))
        mem_u = min(1.0, max(0.0, observation.memory_utilization_ratio))

        t_input = TelemetryInput(
            service_name=svc,
            request_rate=max(0.0, observation.request_rate),
            p95_latency=max(0.0, observation.p95_latency_ms or 0.0),
            error_rate=max(0.0, observation.error_rate),
            cpu_utilisation=cpu_u,
            memory_utilisation=mem_u,
            current_replicas=curr,
            ready_replicas=curr,
            timestamp=ts_dt,
            dependencies=observation.dependencies
        )

        dec_outputs = self.controller.evaluate([t_input])
        if dec_outputs:
            d = dec_outputs[0]
            if d.action == DecisionAction.SCALE_UP:
                action = ScalingAction.SCALE_UP
                target = min(self.max_replicas, curr + 1)
                delta = target - curr
            elif d.action == DecisionAction.SCALE_DOWN:
                action = ScalingAction.SCALE_DOWN
                target = max(self.min_replicas, curr - 1)
                delta = target - curr
            else:
                action = ScalingAction.HOLD
                target = curr
                delta = 0

            rec = PolicyRecommendation(
                policy_type=self.policy_type,
                service_name=svc,
                timestamp=observation.timestamp,
                elapsed_seconds=t,
                action=action,
                current_replicas=curr,
                target_replicas=target,
                replica_delta=delta,
                reason=d.reason,
                trigger_metric="multi_dimensional_pressure",
                metric_value=d.priority_score,
                is_bottleneck=(d.bottleneck == svc),
                priority_score=d.priority_score
            )
        else:
            rec = PolicyRecommendation(
                policy_type=self.policy_type,
                service_name=svc,
                timestamp=observation.timestamp,
                elapsed_seconds=t,
                action=ScalingAction.HOLD,
                current_replicas=curr,
                target_replicas=curr,
                replica_delta=0,
                reason="DPBPS Controller no output",
                is_bottleneck=False
            )

        self.record_recommendation(rec)
        return rec

