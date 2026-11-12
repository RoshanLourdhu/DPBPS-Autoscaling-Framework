"""
backend/scaling/continuous_controller.py
Continuous DPBPS Controller Execution Engine.

Provides an asynchronous, non-overlapping, closed-loop continuous evaluation
engine that periodically:
1. Ingests fresh telemetry via KubernetesTelemetryAdapter.
2. Validates metric availability, integrity, and freshness.
3. Excludes services with missing or stale telemetry without zero fabrication.
4. Identifies the primary bottleneck service across dependencies.
5. Ingests active deployment phase from DeploymentStateManager.
6. Evaluates decisions using the canonical DPBPS algorithm.
7. Processes scaling decisions through KubernetesScalingActuator in DRY_RUN mode.
8. Records full explainable decision history and per-cycle diagnostic summaries.
9. Persists evaluation history safely to disk.
10. Exposes status, control hooks (start, stop, pause, interval), and query APIs.

Safety Principles:
- Hardcoded DRY_RUN=True: Live cluster modifications are strictly prohibited.
- Overlapping Execution Prevention: Enforced via asyncio.Lock.
- Graceful Task Lifecycle: Safe start, pause, resume, and cancellation.
- Zero Missing Metric Fabrication: Missing metrics result in EXCLUDED or HOLD.
- Protected Infrastructure Guard: redis-cart, opentelemetrycollector, loadgenerator never scaled.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

import backend.config as cfg
from backend.scaling.bottleneck_detector import detect_bottleneck
from backend.scaling.deployment_state import DeploymentStateManager
from backend.scaling.dpbps_controller import DPBPSController
from backend.scaling.kubernetes.actuator import (
    KubernetesScalingActuator,
    KubernetesScalingResult,
    PROTECTED_INFRASTRUCTURE,
    ScalingExecutionStatus,
)
from backend.scaling.kubernetes.telemetry_adapter import (
    KubernetesTelemetryAdapter,
)
from backend.scaling.models import (
    DecisionAction,
    DecisionOutput,
    DeploymentPhase,
    ScalingConfig,
    TelemetryInput,
)

logger = logging.getLogger(__name__)

DEFAULT_HISTORY_FILE = Path(__file__).resolve().parents[1] / "data" / "continuous_controller_history.json"


# ---------------------------------------------------------------------
# DATA MODELS FOR CONTINUOUS EVALUATION
# ---------------------------------------------------------------------

class ContinuousDecisionRecord(BaseModel):
    """Detailed explainable record for a single microservice within an evaluation cycle."""
    service_name: str
    timestamp: str
    cycle_number: int
    deployment_phase: str
    is_bottleneck: bool = False
    bottleneck_service: Optional[str] = None
    action: str
    previous_replicas: int
    recommended_replicas: int
    reason: str
    execution_mode: str = "DRY_RUN"
    actuator_status: str
    cluster_modified: bool = False
    cpu_utilization: Optional[float] = None
    memory_utilization: Optional[float] = None
    cpu_usage_millicores: Optional[float] = None
    memory_usage_mib: Optional[float] = None
    request_rate: Optional[float] = None
    p95_latency: Optional[float] = None
    error_rate: Optional[float] = None
    telemetry_complete: bool = False
    telemetry_freshness_seconds: Optional[float] = None
    missing_metrics: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)


class ContinuousCycleSummary(BaseModel):
    """Consolidated summary for an entire continuous evaluation cycle."""
    cycle_number: int
    timestamp: str
    duration_ms: float
    deployment_phase: str
    total_services: int
    eligible_services: int
    excluded_services: int
    bottleneck_service: Optional[str] = None
    scale_up_count: int
    scale_down_count: int
    hold_count: int
    excluded_count: int
    execution_mode: str = "DRY_RUN"
    cluster_modified: bool = False
    decisions: List[ContinuousDecisionRecord] = Field(default_factory=list)


class ContinuousControllerStatus(BaseModel):
    """Runtime status of the continuous DPBPS controller."""
    is_running: bool
    is_paused: bool
    interval_seconds: float
    cycle_count: int
    last_evaluation_time: Optional[str] = None
    last_evaluation_duration_ms: Optional[float] = None
    next_evaluation_time: Optional[str] = None
    current_bottleneck: Optional[str] = None
    deployment_phase: str
    scaling_enabled: bool = False
    dry_run: bool = True
    total_decisions_recorded: int = 0
    latest_cycle_summary: Optional[ContinuousCycleSummary] = None


# ---------------------------------------------------------------------
# CONTINUOUS DPBPS CONTROLLER ENGINE
# ---------------------------------------------------------------------

class ContinuousDPBPSController:
    """
    Manages the continuous closed-loop evaluation lifecycle for DPBPS.

    Coordinates telemetry ingestion, algorithm evaluation, actuator dry-run
    validation, and historical persistence on a configurable cadence.
    """

    def __init__(
        self,
        dpbps_controller: Optional[DPBPSController] = None,
        telemetry_adapter: Optional[KubernetesTelemetryAdapter] = None,
        actuator: Optional[KubernetesScalingActuator] = None,
        state_manager: Optional[DeploymentStateManager] = None,
        interval_seconds: float = 15.0,
        history_file: Optional[Path] = None,
        max_history_cycles: int = 100,
    ):
        self.state_manager = state_manager or DeploymentStateManager()
        self.dpbps_controller = dpbps_controller or DPBPSController()
        self.dpbps_controller.state_manager = self.state_manager

        self.telemetry_adapter = telemetry_adapter or KubernetesTelemetryAdapter(
            state_manager=self.state_manager
        )

        # Enforce hard dry_run=True regardless of environment
        self.actuator = actuator or KubernetesScalingActuator(
            state_manager=self.state_manager,
            config=self.dpbps_controller.config,
            dry_run=True,
        )
        self.actuator.dry_run = True

        self.interval_seconds = max(5.0, min(300.0, float(interval_seconds)))
        self.max_history_cycles = max_history_cycles
        self.history_file = history_file or DEFAULT_HISTORY_FILE

        # Runtime loop state
        self._is_running: bool = False
        self._is_paused: bool = False
        self._cycle_count: int = 0
        self._last_evaluation_time: Optional[datetime] = None
        self._last_duration_ms: Optional[float] = None
        self._next_evaluation_time: Optional[datetime] = None
        self._last_cycle_summary: Optional[ContinuousCycleSummary] = None
        self.last_actuator_results: List[KubernetesScalingResult] = []

        # Thread & task safety primitives
        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None

        # In-memory history ring buffers
        self._cycle_history: List[ContinuousCycleSummary] = []
        self._decision_history: List[ContinuousDecisionRecord] = []

        # Attempt restoring previous history if file exists
        self._load_from_file()

    # -----------------------------------------------------------------
    # PROPERTIES
    # -----------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def is_paused(self) -> bool:
        return self._is_paused

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    @property
    def last_evaluation_time(self) -> Optional[datetime]:
        return self._last_evaluation_time

    @property
    def next_evaluation_time(self) -> Optional[datetime]:
        return self._next_evaluation_time

    # -----------------------------------------------------------------
    # CONTROL LIFECYCLE (START / STOP / PAUSE / RESUME)
    # -----------------------------------------------------------------

    async def start(self) -> bool:
        """
        Start the continuous evaluation loop in the background.

        Returns:
            True if started, False if already running.
        """
        if self._is_running:
            logger.warning("Continuous DPBPS controller is already running.")
            return False

        self._is_running = True
        self._is_paused = False
        self._stop_event.clear()
        self._task = asyncio.create_task(self._background_loop())
        logger.info(
            "Continuous DPBPS controller started with interval=%.1fs (DRY_RUN=True).",
            self.interval_seconds,
        )
        return True

    async def stop(self) -> bool:
        """
        Stop the continuous evaluation loop gracefully.

        Returns:
            True if stopped, False if was not running.
        """
        if not self._is_running:
            logger.info("Continuous DPBPS controller is not running.")
            return False

        logger.info("Stopping continuous DPBPS controller...")
        self._is_running = False
        self._is_paused = False
        self._stop_event.set()

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        self._task = None
        self._next_evaluation_time = None
        logger.info("Continuous DPBPS controller stopped successfully.")
        return True

    def pause(self) -> bool:
        """Pause evaluations without stopping the background task."""
        if not self._is_running or self._is_paused:
            return False
        self._is_paused = True
        logger.info("Continuous DPBPS controller paused.")
        return True

    def resume(self) -> bool:
        """Resume evaluations after being paused."""
        if not self._is_running or not self._is_paused:
            return False
        self._is_paused = False
        logger.info("Continuous DPBPS controller resumed.")
        return True

    def set_interval(self, seconds: float) -> float:
        """
        Update evaluation interval safely clamped between 5.0 and 300.0 seconds.
        """
        self.interval_seconds = max(5.0, min(300.0, float(seconds)))
        logger.info(
            "Continuous DPBPS controller interval set to %.1f seconds.",
            self.interval_seconds,
        )
        return self.interval_seconds

    # -----------------------------------------------------------------
    # BACKGROUND EVALUATION LOOP
    # -----------------------------------------------------------------

    async def _background_loop(self) -> None:
        """Background execution loop running until cancelled or stopped."""
        logger.info("Background loop initialized.")
        try:
            while not self._stop_event.is_set():
                if not self._is_paused:
                    try:
                        await self.run_single_cycle()
                    except asyncio.CancelledError:
                        break
                    except Exception as exc:
                        logger.error(
                            "Unexpected error during continuous DPBPS cycle #%d: %s",
                            self._cycle_count + 1,
                            exc,
                            exc_info=True,
                        )

                # Compute next evaluation timestamp
                now = datetime.now(timezone.utc)
                self._next_evaluation_time = datetime.fromtimestamp(
                    now.timestamp() + self.interval_seconds, tz=timezone.utc
                )

                # Wait for next interval or stop signal
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.interval_seconds,
                    )
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            logger.info("Continuous DPBPS background loop received cancellation.")
        finally:
            self._is_running = False
            self._next_evaluation_time = None

    # -----------------------------------------------------------------
    # CORE SINGLE EVALUATION CYCLE
    # -----------------------------------------------------------------

    async def run_single_cycle(self) -> ContinuousCycleSummary:
        """
        Execute one closed-loop DPBPS evaluation cycle.

        Enforces concurrency lock to avoid overlapping cycles.
        """
        if self._lock.locked():
            logger.warning("Previous evaluation cycle still in progress; skipping.")
            if self._last_cycle_summary:
                return self._last_cycle_summary
            # Create a placeholder summary if first cycle
            now_iso = datetime.now(timezone.utc).isoformat()
            return ContinuousCycleSummary(
                cycle_number=self._cycle_count,
                timestamp=now_iso,
                duration_ms=0.0,
                deployment_phase=self.state_manager.get_phase().value,
                total_services=0,
                eligible_services=0,
                excluded_services=0,
                scale_up_count=0,
                scale_down_count=0,
                hold_count=0,
                excluded_count=0,
            )

        async with self._lock:
            t_start = time.perf_counter()
            cycle_num = self._cycle_count + 1
            now_dt = datetime.now(timezone.utc)
            now_str = now_dt.isoformat()
            current_phase = self.state_manager.get_phase().value

            # 1. Ingest telemetry from KubernetesTelemetryAdapter
            valid_inputs, excluded = self.telemetry_adapter.get_telemetry_inputs()
            raw_telemetry = self.telemetry_adapter.collect_deployment_telemetry()

            # Filter raw telemetry to exclude loadgenerator
            app_raw = [item for item in raw_telemetry if item.get("service_name") != "loadgenerator"]
            raw_by_name = {item["service_name"]: item for item in app_raw}

            # 2. Detect bottleneck across valid microservices
            bottleneck_service = detect_bottleneck(valid_inputs) if valid_inputs else None

            # 3. Evaluate decisions using DPBPS Controller
            decisions: List[DecisionOutput] = []
            if valid_inputs:
                decisions = self.dpbps_controller.evaluate(valid_inputs)
            dec_by_name: Dict[str, DecisionOutput] = {d.service_name: d for d in decisions}

            # 4. Process scaling decisions through KubernetesScalingActuator in DRY_RUN mode
            actuator_results: List[KubernetesScalingResult] = []
            if decisions:
                actuator_results = self.actuator.execute_decisions(decisions)
            act_by_name: Dict[str, KubernetesScalingResult] = {r.service_name: r for r in actuator_results}
            self.last_actuator_results = list(actuator_results)

            # 5. Build structured per-service records
            cycle_decisions: List[ContinuousDecisionRecord] = []

            for svc_name, raw in raw_by_name.items():
                is_eligible = raw.get("telemetry_available", False) and svc_name in dec_by_name
                current_rep = int(raw.get("desired_replicas", 1))
                svc_phase = self.state_manager.get_phase(svc_name).value

                # Calculate metric age / freshness
                freshness_sec: Optional[float] = None
                raw_ts = raw.get("timestamp")
                if raw_ts:
                    try:
                        ts_dt = datetime.fromisoformat(raw_ts)
                        freshness_sec = max(0.0, (now_dt - ts_dt).total_seconds())
                    except Exception:
                        pass

                if is_eligible:
                    decision = dec_by_name[svc_name]
                    act_res = act_by_name.get(svc_name)
                    act_status = act_res.status.value if act_res else "VALIDATED"
                    act_reason = act_res.reason if act_res else decision.reason

                    cycle_decisions.append(
                        ContinuousDecisionRecord(
                            service_name=svc_name,
                            timestamp=now_str,
                            cycle_number=cycle_num,
                            deployment_phase=svc_phase,
                            is_bottleneck=(svc_name == bottleneck_service),
                            bottleneck_service=bottleneck_service,
                            action=decision.action.value,
                            previous_replicas=decision.previous_replicas,
                            recommended_replicas=decision.requested_replicas,
                            reason=act_reason,
                            execution_mode="DRY_RUN",
                            actuator_status=act_status,
                            cluster_modified=False,
                            cpu_utilization=raw.get("cpu_utilisation"),
                            memory_utilization=raw.get("memory_utilisation"),
                            cpu_usage_millicores=raw.get("cpu_usage_millicores"),
                            memory_usage_mib=raw.get("memory_usage_mib"),
                            request_rate=raw.get("request_rate"),
                            p95_latency=raw.get("p95_latency_ms"),
                            error_rate=raw.get("error_rate"),
                            telemetry_complete=True,
                            telemetry_freshness_seconds=freshness_sec,
                            missing_metrics=[],
                            dependencies=raw.get("dependencies", []),
                        )
                    )
                else:
                    # Incomplete, idle, or protected infrastructure service
                    missing = raw.get("missing_metrics", [])
                    if not raw.get("telemetry_available", False) or missing:
                        action_str = "EXCLUDED"
                        status_str = "SKIPPED"
                        missing_str = f"missing metrics {missing}" if missing else "incomplete telemetry"
                        excl_reason = f"Excluded: {missing_str}"
                    elif svc_name in PROTECTED_INFRASTRUCTURE:
                        action_str = "HOLD"
                        status_str = "SKIPPED"
                        excl_reason = f"Protected infrastructure service '{svc_name}' is exempt from scaling."
                    else:
                        action_str = "HOLD"
                        status_str = "SKIPPED"
                        excl_reason = "Service telemetry held at steady-state."

                    cycle_decisions.append(
                        ContinuousDecisionRecord(
                            service_name=svc_name,
                            timestamp=now_str,
                            cycle_number=cycle_num,
                            deployment_phase=svc_phase,
                            is_bottleneck=False,
                            bottleneck_service=bottleneck_service,
                            action=action_str,
                            previous_replicas=current_rep,
                            recommended_replicas=current_rep,
                            reason=excl_reason,
                            execution_mode="DRY_RUN",
                            actuator_status=status_str,
                            cluster_modified=False,
                            cpu_utilization=raw.get("cpu_utilisation"),
                            memory_utilization=raw.get("memory_utilisation"),
                            cpu_usage_millicores=raw.get("cpu_usage_millicores"),
                            memory_usage_mib=raw.get("memory_usage_mib"),
                            request_rate=raw.get("request_rate"),
                            p95_latency=raw.get("p95_latency_ms"),
                            error_rate=raw.get("error_rate"),
                            telemetry_complete=False,
                            telemetry_freshness_seconds=freshness_sec,
                            missing_metrics=missing,
                            dependencies=raw.get("dependencies", []),
                        )
                    )

            # 6. Aggregate cycle metrics
            scale_ups = sum(1 for d in cycle_decisions if d.action == "SCALE_UP")
            scale_downs = sum(1 for d in cycle_decisions if d.action == "SCALE_DOWN")
            holds = sum(1 for d in cycle_decisions if d.action == "HOLD")
            excluded_count = sum(1 for d in cycle_decisions if d.action == "EXCLUDED")

            duration_ms = (time.perf_counter() - t_start) * 1000.0

            summary = ContinuousCycleSummary(
                cycle_number=cycle_num,
                timestamp=now_str,
                duration_ms=round(duration_ms, 2),
                deployment_phase=current_phase,
                total_services=len(cycle_decisions),
                eligible_services=len(valid_inputs),
                excluded_services=len(cycle_decisions) - len(valid_inputs),
                bottleneck_service=bottleneck_service,
                scale_up_count=scale_ups,
                scale_down_count=scale_downs,
                hold_count=holds,
                excluded_count=excluded_count,
                execution_mode="DRY_RUN",
                cluster_modified=False,
                decisions=cycle_decisions,
            )

            # Update state
            self._cycle_count = cycle_num
            self._last_evaluation_time = now_dt
            self._last_duration_ms = duration_ms
            self._last_cycle_summary = summary

            # Append to ring buffers
            self._cycle_history.append(summary)
            if len(self._cycle_history) > self.max_history_cycles:
                self._cycle_history.pop(0)

            self._decision_history.extend(cycle_decisions)
            if len(self._decision_history) > (self.max_history_cycles * 15):
                self._decision_history = self._decision_history[-(self.max_history_cycles * 15):]

            # Persist evaluation history
            self._persist_to_file()

            logger.info(
                "Cycle #%d complete in %.1fms: %d eligible, %d excluded, bottleneck=%s, "
                "scale_up=%d, scale_down=%d, hold=%d (DRY_RUN=True)",
                cycle_num,
                duration_ms,
                len(valid_inputs),
                summary.excluded_services,
                bottleneck_service or "None",
                scale_ups,
                scale_downs,
                holds,
            )

            return summary

    # -----------------------------------------------------------------
    # QUERY & EXPORT METHODS
    # -----------------------------------------------------------------

    def get_status(self) -> ContinuousControllerStatus:
        """Return comprehensive live status of the continuous controller."""
        now_str = datetime.now(timezone.utc).isoformat()
        last_str = self._last_evaluation_time.isoformat() if self._last_evaluation_time else None
        next_str = self._next_evaluation_time.isoformat() if self._next_evaluation_time else None

        current_bn = None
        if self._last_cycle_summary:
            current_bn = self._last_cycle_summary.bottleneck_service

        return ContinuousControllerStatus(
            is_running=self._is_running,
            is_paused=self._is_paused,
            interval_seconds=self.interval_seconds,
            cycle_count=self._cycle_count,
            last_evaluation_time=last_str,
            last_evaluation_duration_ms=self._last_duration_ms,
            next_evaluation_time=next_str,
            current_bottleneck=current_bn,
            deployment_phase=self.state_manager.get_phase().value,
            scaling_enabled=cfg.SCALING_ENABLED,
            dry_run=True,
            total_decisions_recorded=len(self._decision_history),
            latest_cycle_summary=self._last_cycle_summary,
        )

    def get_history(self, limit: int = 20) -> List[ContinuousCycleSummary]:
        """Return the most recent cycle summaries up to limit."""
        return self._cycle_history[-limit:]

    def get_detailed_decisions(
        self,
        service_name: Optional[str] = None,
        limit: int = 50,
    ) -> List[ContinuousDecisionRecord]:
        """Return the most recent per-service decision records."""
        if service_name:
            filtered = [d for d in self._decision_history if d.service_name == service_name]
            return filtered[-limit:]
        return self._decision_history[-limit:]

    # -----------------------------------------------------------------
    # PERSISTENCE
    # -----------------------------------------------------------------

    def _persist_to_file(self) -> None:
        """Safely write recent cycle summaries to disk."""
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "cycle_count": self._cycle_count,
                "interval_seconds": self.interval_seconds,
                "cycles": [
                    {
                        "cycle_number": c.cycle_number,
                        "timestamp": c.timestamp,
                        "duration_ms": c.duration_ms,
                        "deployment_phase": c.deployment_phase,
                        "total_services": c.total_services,
                        "eligible_services": c.eligible_services,
                        "excluded_services": c.excluded_services,
                        "bottleneck_service": c.bottleneck_service,
                        "scale_up_count": c.scale_up_count,
                        "scale_down_count": c.scale_down_count,
                        "hold_count": c.hold_count,
                        "excluded_count": c.excluded_count,
                        "execution_mode": c.execution_mode,
                        "cluster_modified": c.cluster_modified,
                        "decisions_count": len(c.decisions),
                    }
                    for c in self._cycle_history[-50:]
                ],
            }
            temp_path = self.history_file.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            temp_path.replace(self.history_file)
        except Exception as exc:
            logger.warning("Failed to persist continuous controller history: %s", exc)

    def _load_from_file(self) -> None:
        """Load history metadata if previously written."""
        if not self.history_file.exists():
            return
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._cycle_count = int(data.get("cycle_count", 0))
            logger.info(
                "Restored previous continuous controller state: cycle_count=%d",
                self._cycle_count,
            )
        except Exception as exc:
            logger.warning("Failed to load continuous controller history: %s", exc)
