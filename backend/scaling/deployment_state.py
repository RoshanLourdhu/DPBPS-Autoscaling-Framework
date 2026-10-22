# backend/scaling/deployment_state.py
"""Manage deployment phase and cooldown timers for DPBPS simulation."""

from datetime import datetime, timezone, timedelta
from typing import Dict
from .models import DeploymentPhase, ScalingConfig, DecisionAction


class DeploymentStateManager:
    """Keeps track of the current deployment phase and per‑service cooldown timestamps.

    All timestamps are stored in UTC. The manager is deliberately lightweight and
    suitable for in‑memory simulation; it can be swapped for a persistent store
    later without changing the controller logic.
    """

    def __init__(self) -> None:
        self.phase: DeploymentPhase = DeploymentPhase.NORMAL_OPERATION
        # service_name -> last scaling action timestamp (UTC)
        self.last_action_time: Dict[str, datetime] = {}
        # service_name -> last action type (DecisionAction value string)
        self.last_action_type: Dict[str, str] = {}
        # service_name -> timestamp when a scale‑down stabilization period started
        self.scale_down_stabilization_start: Dict[str, datetime] = {}

    # ---------------------------------------------------------------------
    # Phase handling
    # ---------------------------------------------------------------------
    def set_phase(self, new_phase: DeploymentPhase) -> None:
        self.phase = new_phase

    def get_phase(self) -> DeploymentPhase:
        return self.phase

    # ---------------------------------------------------------------------
    # Cooldown handling
    # ---------------------------------------------------------------------
    def can_scale(self, service_name: str, now: datetime, config: ScalingConfig) -> bool:
        """Return ``True`` if the service is not within the global cooldown window.

        ``config.cooldown_sec`` defines the minimum interval between any two
        scaling actions for the same service.
        """
        last = self.last_action_time.get(service_name)
        if last is None:
            return True
        return (now - last).total_seconds() >= config.cooldown_sec

    def record_action(self, service_name: str, action: DecisionAction, now: datetime) -> None:
        self.last_action_time[service_name] = now
        self.last_action_type[service_name] = action.value
        # Reset stabilization when a scale‑up occurs or a scale‑down is performed
        if action == DecisionAction.SCALE_DOWN:
            self.scale_down_stabilization_start[service_name] = now
        else:
            self.scale_down_stabilization_start.pop(service_name, None)

    def is_stabilized_for_scale_down(self, service_name: str, now: datetime, config: ScalingConfig) -> bool:
        """During ``POST_DEPLOYMENT`` a service may only scale down after a
        stabilization period defined by ``config.scale_down_stabilization_sec``.
        """
        start = self.scale_down_stabilization_start.get(service_name)
        if start is None:
            return False
        return (now - start).total_seconds() >= config.scale_down_stabilization_sec
