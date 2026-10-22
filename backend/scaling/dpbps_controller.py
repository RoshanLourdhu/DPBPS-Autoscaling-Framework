# backend/scaling/dpbps_controller.py
"""DPBPS simulation controller.

The controller evaluates a list of ``TelemetryInput`` objects (one per service)
and returns a list of ``DecisionOutput`` objects. It respects deployment phase,
cooldowns, scaling limits, and bottleneck detection.
"""

from datetime import datetime, timezone
from typing import List, Dict, Optional

from .models import (
    TelemetryInput,
    DecisionOutput,
    DecisionAction,
    DeploymentPhase,
    ScalingConfig,
)
from .telemetry import is_fresh
from .deployment_state import DeploymentStateManager
from .bottleneck_detector import detect_bottleneck


class DPBPSController:
    """Core DPBPS simulation engine.

    The controller holds a ``ScalingConfig`` and a ``DeploymentStateManager``.
    ``evaluate`` is deterministic: given identical telemetry and internal state it
    always returns the same decisions.
    """

    def __init__(self, config: Optional[ScalingConfig] = None) -> None:
        self.config = config or ScalingConfig()
        self.state_manager = DeploymentStateManager()
        # In‑memory decision history – a simple list ordered by timestamp.
        self.decision_history: List[DecisionOutput] = []

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def set_phase(self, phase: DeploymentPhase) -> None:
        self.state_manager.set_phase(phase)

    def get_phase(self) -> DeploymentPhase:
        return self.state_manager.get_phase()

    def get_history(self, limit: int = 20) -> List[DecisionOutput]:
        return self.decision_history[-limit:]

    def evaluate(self, telemetry: List[TelemetryInput]) -> List[DecisionOutput]:
        """Evaluate telemetry and produce scaling decisions.

        The algorithm follows the requirements from the user request. It
        operates purely on the supplied telemetry – no external side‑effects are
        performed (simulation mode).
        """
        now = datetime.now(timezone.utc)
        # Detect bottleneck once per evaluation (could be None).
        bottleneck_service = detect_bottleneck(telemetry)
        # Index telemetry for quick lookup.
        telemetry_by_name: Dict[str, TelemetryInput] = {t.service_name: t for t in telemetry}
        decisions: List[DecisionOutput] = []

        for t in telemetry:
            # Basic validation – missing or stale telemetry leads to HOLD/INSUFFICIENT.
            if not is_fresh(t, self.config):
                decision = DecisionOutput(
                    service_name=t.service_name,
                    action=DecisionAction.INSUFFICIENT_TELEMETRY,
                    previous_replicas=t.current_replicas,
                    requested_replicas=t.current_replicas,
                    phase=self.state_manager.get_phase(),
                    bottleneck=bottleneck_service,
                    reason="Telemetry sample is stale or missing",
                )
                decisions.append(decision)
                continue

            # Enforce cooldown.
            if not self.state_manager.can_scale(t.service_name, now, self.config):
                decision = DecisionOutput(
                    service_name=t.service_name,
                    action=DecisionAction.HOLD,
                    previous_replicas=t.current_replicas,
                    requested_replicas=t.current_replicas,
                    phase=self.state_manager.get_phase(),
                    bottleneck=bottleneck_service,
                    reason="Cooldown period active",
                )
                decisions.append(decision)
                continue

            # Compute pressure scores.
            cpu_pressure = max(0.0, (t.cpu_utilisation - self.config.cpu_threshold) / (1 - self.config.cpu_threshold))
            mem_pressure = max(0.0, (t.memory_utilisation - self.config.memory_threshold) / (1 - self.config.memory_threshold))
            latency_pressure = max(0.0, (t.p95_latency - self.config.latency_target_ms) / self.config.latency_target_ms)
            error_pressure = t.error_rate  # already a fraction
            # Weighted aggregate (0..1 range approx)
            aggregate = (
                self.config.weight_cpu * cpu_pressure
                + self.config.weight_memory * mem_pressure
                + self.config.weight_latency * latency_pressure
                + self.config.weight_error * error_pressure
            )

            # Determine desired replica change.
            desired_change = 0
            if aggregate > 0.2:  # heuristic threshold for scaling up
                desired_change = 1
            elif aggregate < 0.05:
                desired_change = -1

            # Respect deployment phase constraints.
            phase = self.state_manager.get_phase()
            reason = ""
            if phase == DeploymentPhase.ACTIVE_DEPLOYMENT and desired_change < 0:
                # No scale‑down during active deployment.
                desired_change = 0
                reason = "Active deployment – scale‑down suppressed"
            elif phase == DeploymentPhase.POST_DEPLOYMENT and desired_change < 0:
                # Require stabilization.
                if self.state_manager.is_stabilized_for_scale_down(t.service_name, now, self.config):
                    reason = "Post‑deployment stabilization satisfied – scaling down"
                else:
                    desired_change = 0
                    reason = "Post‑deployment stabilization period not elapsed"

            # Apply safety bounds.
            target = t.current_replicas + desired_change
            target = max(self.config.min_replicas, min(self.config.max_replicas, target))
            # Enforce max replica change per decision.
            if abs(target - t.current_replicas) > self.config.max_replica_change:
                target = t.current_replicas + (self.config.max_replica_change if desired_change > 0 else -self.config.max_replica_change)

            # Determine final action.
            if target > t.current_replicas:
                action = DecisionAction.SCALE_UP
                if not reason:
                    reason = f"High pressure (aggregate={aggregate:.2f}) – scaling up"
            elif target < t.current_replicas:
                action = DecisionAction.SCALE_DOWN
                if not reason:
                    reason = f"Low pressure (aggregate={aggregate:.2f}) – scaling down"
            else:
                action = DecisionAction.HOLD
                if not reason:
                    reason = f"Pressure within bounds (aggregate={aggregate:.2f}) – hold"

            # Bottleneck influence – if this service is downstream of a detected bottleneck
            # we ensure the decision is HOLD and the reason mentions the bottleneck.
            if bottleneck_service and t.service_name != bottleneck_service:
                action = DecisionAction.HOLD
                target = t.current_replicas
                reason = f"Downstream bottleneck detected on '{bottleneck_service}' – holding"

            decision = DecisionOutput(
                service_name=t.service_name,
                action=action,
                previous_replicas=t.current_replicas,
                requested_replicas=target,
                priority_score=aggregate,
                phase=phase,
                bottleneck=bottleneck_service,
                reason=reason,
                simulated=True,
            )
            decisions.append(decision)
            # Record action for cooldown / stabilization tracking.
            if action != DecisionAction.HOLD:
                self.state_manager.record_action(t.service_name, action, now)

        # Store history.
        self.decision_history.extend(decisions)
        return decisions

    # ---------------------------------------------------------------------
    # Helper used by API for dry‑run (no state mutation).
    # ---------------------------------------------------------------------
    def dry_run(self, telemetry: List[TelemetryInput]) -> List[DecisionOutput]:
        """Evaluate telemetry without mutating cooldown or history.

        Internally we clone the current state manager to avoid side‑effects.
        """
        # Clone simple mutable structures.
        original_last = self.state_manager.last_action_time.copy()
        original_last_type = self.state_manager.last_action_type.copy()
        original_stab = self.state_manager.scale_down_stabilization_start.copy()
        result = self.evaluate(telemetry)
        # Restore state.
        self.state_manager.last_action_time = original_last
        self.state_manager.last_action_type = original_last_type
        self.state_manager.scale_down_stabilization_start = original_stab
        # Remove recorded history for dry‑run.
        self.decision_history = self.decision_history[:-len(result)]
        return result
