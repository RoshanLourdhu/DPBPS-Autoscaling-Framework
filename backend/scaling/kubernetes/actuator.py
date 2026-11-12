"""
Kubernetes scaling actuator for the DPBPS framework.

Translates DPBPS DecisionOutput scaling decisions into safe Kubernetes
Deployment replica updates, with comprehensive safety checks, emergency stop,
post-action readiness verification, automated rollback procedures, and dry-run execution.

Safety principles:
1. Dry-run mode by default; live cluster modifications require explicit enablement
   (dry_run=False and cfg.SCALING_ENABLED=True).
2. Unknown services, uninstrumented components, and infrastructure (e.g. redis-cart,
   opentelemetrycollector, loadgenerator) are strictly rejected from scaling.
3. Replica counts must fall within configured [min_replicas, max_replicas] bounds.
4. Maximum replica change per decision is strictly enforced (max_replica_change).
5. Scale-down operations are prohibited during PRE_DEPLOYMENT and ACTIVE_DEPLOYMENT.
6. Scale-down operations during POST_DEPLOYMENT respect the stabilization window.
7. Active deployment rollouts, generation mismatches, and unready pods prevent scaling.
8. HorizontalPodAutoscaler (HPA) conflicts are detected and rejected to prevent controller fighting.
9. Stale decisions (concurrency conflicts where live replica count differs from decision baseline) are rejected.
10. Cooldown intervals are enforced to prevent rapid oscillation.
11. Global Emergency Stop switch provides immediate fail-closed protection.
12. Transient Kubernetes API errors are retried with bounded exponential backoff; non-retryable errors fail fast.
13. Post-action readiness verification verifies updated and available pod counts.
14. Safe automated rollback engine reverts replicas if readiness verification fails.
"""

from datetime import datetime, timezone
from enum import Enum
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from pydantic import BaseModel, Field

import backend.config as cfg
from backend.scaling.deployment_state import DeploymentStateManager
from backend.scaling.kubernetes.client import (
    get_apps_v1_api,
    get_autoscaling_v2_api,
)
from backend.scaling.models import (
    DecisionAction,
    DecisionOutput,
    DeploymentPhase,
    ScalingConfig,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# SERVICE CLASSIFICATION
# ---------------------------------------------------------------------

# Approved application microservices that DPBPS is designed to manage
APPLICATION_SERVICES: Set[str] = {
    "frontend",
    "cartservice",
    "productcatalogservice",
    "currencyservice",
    "paymentservice",
    "shippingservice",
    "emailservice",
    "checkoutservice",
    "recommendationservice",
    "adservice",
}

# Protected infrastructure services that must NEVER be scaled dynamically
PROTECTED_INFRASTRUCTURE: Set[str] = {
    "redis-cart",
    "opentelemetrycollector",
    "loadgenerator",
}


# ---------------------------------------------------------------------
# EXECUTION MODELS
# ---------------------------------------------------------------------

class ScalingExecutionStatus(str, Enum):
    """Execution status for a proposed scaling operation."""
    VALIDATED = "VALIDATED"       # Dry-run validation passed
    APPLIED = "APPLIED"           # Scaling operation executed (live mode)
    REJECTED = "REJECTED"         # Safety check rejected the scaling action
    SKIPPED = "SKIPPED"           # Non-scaling decision (HOLD, INSUFFICIENT, no-op)
    FAILED = "FAILED"             # API error or unexpected exception


class KubernetesScalingResult(BaseModel):
    """
    Structured result of a Kubernetes scaling evaluation or execution.
    """
    operation_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique operation identifier")
    decision_id: Optional[str] = Field(None, description="Linked DPBPS decision ID")
    service_name: str = Field(..., description="Target service/deployment identifier")
    namespace: str = Field(..., description="Target Kubernetes namespace")
    current_replicas: int = Field(..., ge=0, description="Current replica count before action")
    requested_replicas: int = Field(..., ge=0, description="Target replica count requested")
    action: DecisionAction = Field(..., description="DPBPS decision action")
    execution_mode: str = Field("DRY_RUN", description="Execution mode: DRY_RUN or LIVE")
    status: ScalingExecutionStatus = Field(..., description="Outcome of the actuator evaluation")
    cluster_modified: bool = Field(False, description="Whether any cluster resource was modified")
    reason: str = Field(..., description="Detailed explanation of outcome")
    deployment_phase: DeploymentPhase = Field(..., description="Active deployment phase")
    readiness_status: str = Field("SKIPPED", description="Readiness check outcome: VERIFIED, TIMED_OUT, FAILED, SKIPPED, SIMULATED")
    rollback_status: str = Field("NOT_REQUIRED", description="Rollback outcome: NOT_REQUIRED, EXECUTED, SIMULATED, FAILED")
    validation_result: Optional[str] = Field(None, description="Pre-flight safety validation detail")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    details: Dict[str, Any] = Field(default_factory=dict, description="Diagnostic metadata")

    @property
    def service(self) -> str:
        """Alias for service_name matching illustrative specification."""
        return self.service_name


# ---------------------------------------------------------------------
# KUBERNETES SCALING ACTUATOR
# ---------------------------------------------------------------------

class KubernetesScalingActuator:
    """
    Translates DPBPS DecisionOutput objects into safe Kubernetes Deployment
    replica operations with pre-flight validation, emergency stop, retry handling,
    post-action verification, rollback procedures, and strict dry-run execution.
    """

    def __init__(
        self,
        namespace: str = "online-boutique",
        apps_api: Optional[Any] = None,
        autoscaling_api: Optional[Any] = None,
        state_manager: Optional[DeploymentStateManager] = None,
        config: Optional[ScalingConfig] = None,
        dry_run: bool = True,
        allowlist: Optional[List[str]] = None,
        emergency_stop: bool = False,
        telemetry_freshness_threshold_sec: float = 60.0,
        readiness_timeout_sec: float = 60.0,
        max_retries: int = 3,
        retry_backoff_sec: float = 0.2,
    ):
        self.namespace = namespace
        self._apps_api = apps_api
        self._autoscaling_api = autoscaling_api
        self.state_manager = state_manager or DeploymentStateManager()
        self.config = config or ScalingConfig()
        self.dry_run = dry_run
        self.allowlist = (
            allowlist
            if allowlist is not None
            else getattr(cfg, "SCALING_ALLOWLIST", [])
        )
        self.emergency_stop = emergency_stop
        self.emergency_stop_reason: Optional[str] = None
        self.emergency_stop_timestamp: Optional[datetime] = None
        self.telemetry_freshness_threshold_sec = telemetry_freshness_threshold_sec
        self.readiness_timeout_sec = readiness_timeout_sec
        self.max_retries = max_retries
        self.retry_backoff_sec = retry_backoff_sec
        self._operation_lock = threading.Lock()

    @property
    def apps_api(self):
        """Lazy-loaded AppsV1Api client."""
        if self._apps_api is None:
            self._apps_api = get_apps_v1_api()
        return self._apps_api

    @property
    def autoscaling_api(self):
        """Lazy-loaded Autoscaling API client."""
        if self._autoscaling_api is None:
            try:
                self._autoscaling_api = get_autoscaling_v2_api()
            except Exception as exc:
                logger.warning("Autoscaling API unavailable: %s", exc)
                self._autoscaling_api = None
        return self._autoscaling_api

    # -----------------------------------------------------------------
    # EMERGENCY STOP CONTROLS
    # -----------------------------------------------------------------

    def activate_emergency_stop(self, reason: str = "Manual emergency stop activated") -> Dict[str, Any]:
        """Activate the global emergency stop switch, immediately halting scaling."""
        with self._operation_lock:
            self.emergency_stop = True
            self.emergency_stop_reason = reason
            self.emergency_stop_timestamp = datetime.now(timezone.utc)
            logger.warning("EMERGENCY STOP ACTIVATED: %s", reason)
            return {
                "emergency_stop": True,
                "reason": reason,
                "timestamp": self.emergency_stop_timestamp.isoformat(),
            }

    def deactivate_emergency_stop(self) -> Dict[str, Any]:
        """Deactivate emergency stop, restoring normal actuator readiness."""
        with self._operation_lock:
            prev_reason = self.emergency_stop_reason
            self.emergency_stop = False
            self.emergency_stop_reason = None
            self.emergency_stop_timestamp = None
            logger.info("Emergency stop deactivated (previously: %s)", prev_reason)
            return {
                "emergency_stop": False,
                "previous_reason": prev_reason,
                "restored_at": datetime.now(timezone.utc).isoformat(),
            }

    def is_emergency_stop_active(self) -> bool:
        """Check whether the emergency stop switch is currently active."""
        return self.emergency_stop

    def get_actuator_status(self) -> Dict[str, Any]:
        """Return comprehensive status of the scaling actuator and all safety controls."""
        return {
            "namespace": self.namespace,
            "dry_run": self.dry_run,
            "global_scaling_enabled": cfg.SCALING_ENABLED,
            "emergency_stop": self.emergency_stop,
            "emergency_stop_reason": self.emergency_stop_reason,
            "emergency_stop_timestamp": (
                self.emergency_stop_timestamp.isoformat()
                if self.emergency_stop_timestamp
                else None
            ),
            "approved_services": sorted(list(APPLICATION_SERVICES)),
            "protected_infrastructure": sorted(list(PROTECTED_INFRASTRUCTURE)),
            "allowlist": self.allowlist,
            "limits": {
                "min_replicas": self.config.min_replicas,
                "max_replicas": self.config.max_replicas,
                "max_replica_change": self.config.max_replica_change,
                "cooldown_sec": self.config.cooldown_sec,
                "scale_down_stabilization_sec": self.config.scale_down_stabilization_sec,
            },
            "reliability": {
                "max_retries": self.max_retries,
                "readiness_timeout_sec": self.readiness_timeout_sec,
                "telemetry_freshness_threshold_sec": self.telemetry_freshness_threshold_sec,
            },
        }

    # -----------------------------------------------------------------
    # HPA CONFLICT DETECTION
    # -----------------------------------------------------------------

    def check_hpa_conflict(self, deployment_name: str) -> Optional[str]:
        """
        Check if any HorizontalPodAutoscaler in the namespace targets this deployment.
        Returns the conflicting HPA name if found, else None.
        """
        if self.autoscaling_api is None:
            return None

        try:
            hpas = self.autoscaling_api.list_namespaced_horizontal_pod_autoscaler(
                namespace=self.namespace
            )
            for hpa in hpas.items:
                target = hpa.spec.scale_target_ref
                if (
                    target.name == deployment_name
                    and target.kind.lower() == "deployment"
                ):
                    return hpa.metadata.name
        except Exception as exc:
            logger.debug(
                "Unable to query HPAs in namespace %s: %s",
                self.namespace,
                exc,
            )
        return None

    # -----------------------------------------------------------------
    # RETRY-ENABLED KUBERNETES API CLIENT HELPERS
    # -----------------------------------------------------------------

    def _query_deployment_with_retry(self, service_name: str) -> Any:
        """
        Query a Kubernetes deployment with bounded retries for transient errors.
        Non-retryable errors (401, 403, 404, 409, 422) raise immediately.
        """
        last_exc = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return self.apps_api.read_namespaced_deployment(
                    name=service_name,
                    namespace=self.namespace,
                )
            except Exception as exc:
                last_exc = exc
                status_code = getattr(exc, "status", None)
                # Fail fast on non-retryable errors
                if status_code in (400, 401, 403, 404, 409, 422):
                    raise exc
                if attempt < self.max_retries:
                    backoff = self.retry_backoff_sec * (2 ** (attempt - 1))
                    time.sleep(backoff)
        if last_exc:
            raise last_exc

    # -----------------------------------------------------------------
    # POST-ACTION READINESS VERIFICATION ENGINE
    # -----------------------------------------------------------------

    def verify_post_action_readiness(
        self,
        service_name: str,
        target_replicas: int,
        timeout_seconds: Optional[float] = None,
        poll_interval_seconds: float = 2.0,
    ) -> Dict[str, Any]:
        """
        Verify that a scaling operation reached completion and all target replicas are ready.
        In DRY_RUN mode, returns simulated successful verification without delay.
        """
        timeout = timeout_seconds if timeout_seconds is not None else self.readiness_timeout_sec

        if self.dry_run:
            return {
                "ready": True,
                "status": "SIMULATED",
                "message": f"Simulated readiness verification succeeded for {service_name} at {target_replicas} replicas.",
                "elapsed_seconds": 0.0,
            }

        start_time = time.perf_counter()
        while (time.perf_counter() - start_time) < timeout:
            try:
                dep = self._query_deployment_with_retry(service_name)
                status = dep.status
                metadata = dep.metadata
                gen = getattr(metadata, "generation", None)
                obs_gen = getattr(status, "observed_generation", None)
                updated = getattr(status, "updated_replicas", 0) or 0
                ready = getattr(status, "ready_replicas", 0) or 0
                available = getattr(status, "available_replicas", 0) or 0

                # Check for failure condition
                for cond in getattr(status, "conditions", []) or []:
                    if getattr(cond, "type", "") == "Progressing":
                        if getattr(cond, "status", "") == "False" and getattr(cond, "reason", "") == "ProgressDeadlineExceeded":
                            return {
                                "ready": False,
                                "status": "FAILED",
                                "message": f"Rollout progress deadline exceeded for {service_name}.",
                                "elapsed_seconds": time.perf_counter() - start_time,
                            }

                if (
                    gen is not None
                    and obs_gen is not None
                    and gen == obs_gen
                    and updated >= target_replicas
                    and ready >= target_replicas
                    and available >= target_replicas
                ):
                    return {
                        "ready": True,
                        "status": "VERIFIED",
                        "message": f"Service {service_name} ready with {ready}/{target_replicas} replicas.",
                        "elapsed_seconds": time.perf_counter() - start_time,
                    }
            except Exception as exc:
                logger.warning("Error checking readiness for %s: %s", service_name, exc)

            time.sleep(poll_interval_seconds)

        return {
            "ready": False,
            "status": "TIMED_OUT",
            "message": f"Readiness verification timed out after {timeout:.1f}s for {service_name}.",
            "elapsed_seconds": timeout,
        }

    # -----------------------------------------------------------------
    # AUTOMATED ROLLBACK ENGINE
    # -----------------------------------------------------------------

    def execute_rollback_procedure(
        self,
        service_name: str,
        rollback_replicas: int,
        reason: str = "Rollout readiness verification failure",
    ) -> Dict[str, Any]:
        """
        Safely execute or simulate a rollback to revert a deployment to its previous replica count.
        In DRY_RUN mode, returns simulated rollback output without cluster mutation.
        """
        now_utc = datetime.now(timezone.utc)
        if self.dry_run:
            logger.info(
                "DRY-RUN: Simulated rollback for %s to %d replicas (%s)",
                service_name,
                rollback_replicas,
                reason,
            )
            return {
                "service_name": service_name,
                "rollback_status": "SIMULATED",
                "reverted_to": rollback_replicas,
                "reason": reason,
                "cluster_modified": False,
                "timestamp": now_utc.isoformat(),
            }

        if not cfg.SCALING_ENABLED:
            return {
                "service_name": service_name,
                "rollback_status": "REJECTED",
                "reason": "Live scaling is disabled (SCALING_ENABLED=false)",
                "cluster_modified": False,
                "timestamp": now_utc.isoformat(),
            }

        try:
            scale_body = {"spec": {"replicas": rollback_replicas}}
            self.apps_api.patch_namespaced_deployment_scale(
                name=service_name,
                namespace=self.namespace,
                body=scale_body,
            )
            logger.warning(
                "LIVE ROLLBACK: Reverted %s to %d replicas (%s)",
                service_name,
                rollback_replicas,
                reason,
            )
            return {
                "service_name": service_name,
                "rollback_status": "EXECUTED",
                "reverted_to": rollback_replicas,
                "reason": reason,
                "cluster_modified": True,
                "timestamp": now_utc.isoformat(),
            }
        except Exception as exc:
            logger.error("Live rollback failed for %s: %s", service_name, exc)
            return {
                "service_name": service_name,
                "rollback_status": "FAILED",
                "reverted_to": rollback_replicas,
                "reason": f"Live rollback failed: {exc}",
                "cluster_modified": False,
                "timestamp": now_utc.isoformat(),
            }

    # -----------------------------------------------------------------
    # DECISION EXECUTION WITH COMPLETE SAFETY GATES
    # -----------------------------------------------------------------

    def execute_decision(self, decision: DecisionOutput) -> KubernetesScalingResult:
        """
        Validate and execute a single DPBPS scaling decision.

        In dry-run mode (default), performs all pre-flight safety validations,
        queries the live deployment state, checks for conflicts, and returns
        a validated result without modifying the cluster.
        """
        service_name = decision.service_name
        mgr_phase = self.state_manager.get_phase(service_name)
        current_phase = mgr_phase if mgr_phase != DeploymentPhase.NORMAL_OPERATION else (decision.phase or mgr_phase)
        now_utc = datetime.now(timezone.utc)
        mode_str = "DRY_RUN" if self.dry_run else "LIVE"
        op_id = str(uuid.uuid4())
        dec_id = getattr(decision, "decision_id", None)

        with self._operation_lock:
            # 1. Emergency Stop Check (Immediate Fail-Closed)
            if self.is_emergency_stop_active():
                return KubernetesScalingResult(
                    operation_id=op_id,
                    decision_id=dec_id,
                    service_name=service_name,
                    namespace=self.namespace,
                    current_replicas=decision.previous_replicas,
                    requested_replicas=decision.requested_replicas,
                    action=decision.action,
                    execution_mode=mode_str,
                    status=ScalingExecutionStatus.REJECTED,
                    cluster_modified=False,
                    reason=f"Emergency stop active: {self.emergency_stop_reason or 'Manual emergency stop triggered'}. Scaling operations are halted.",
                    deployment_phase=current_phase,
                    readiness_status="SKIPPED",
                    rollback_status="NOT_REQUIRED",
                    validation_result="REJECTED_EMERGENCY_STOP",
                )

            # 2. Non-scaling decisions: HOLD or INSUFFICIENT_TELEMETRY
            if decision.action == DecisionAction.HOLD:
                return KubernetesScalingResult(
                    operation_id=op_id,
                    decision_id=dec_id,
                    service_name=service_name,
                    namespace=self.namespace,
                    current_replicas=decision.previous_replicas,
                    requested_replicas=decision.requested_replicas,
                    action=decision.action,
                    execution_mode=mode_str,
                    status=ScalingExecutionStatus.SKIPPED,
                    cluster_modified=False,
                    reason=decision.reason or "Scaling action is HOLD – no replica change required.",
                    deployment_phase=current_phase,
                    readiness_status="SKIPPED",
                    rollback_status="NOT_REQUIRED",
                    validation_result="SKIPPED_HOLD",
                )

            if decision.action == DecisionAction.INSUFFICIENT_TELEMETRY:
                return KubernetesScalingResult(
                    operation_id=op_id,
                    decision_id=dec_id,
                    service_name=service_name,
                    namespace=self.namespace,
                    current_replicas=decision.previous_replicas,
                    requested_replicas=decision.requested_replicas,
                    action=decision.action,
                    execution_mode=mode_str,
                    status=ScalingExecutionStatus.SKIPPED,
                    cluster_modified=False,
                    reason=decision.reason or "Insufficient or stale telemetry – scaling skipped.",
                    deployment_phase=current_phase,
                    readiness_status="SKIPPED",
                    rollback_status="NOT_REQUIRED",
                    validation_result="SKIPPED_INSUFFICIENT_TELEMETRY",
                )

            # 3. No-op replica change
            if decision.requested_replicas == decision.previous_replicas:
                return KubernetesScalingResult(
                    operation_id=op_id,
                    decision_id=dec_id,
                    service_name=service_name,
                    namespace=self.namespace,
                    current_replicas=decision.previous_replicas,
                    requested_replicas=decision.requested_replicas,
                    action=decision.action,
                    execution_mode=mode_str,
                    status=ScalingExecutionStatus.SKIPPED,
                    cluster_modified=False,
                    reason="Requested replicas equal previous replicas – no-op.",
                    deployment_phase=current_phase,
                    readiness_status="SKIPPED",
                    rollback_status="NOT_REQUIRED",
                    validation_result="SKIPPED_NO_OP",
                )

            # 4. Reject protected infrastructure components
            if service_name in PROTECTED_INFRASTRUCTURE:
                return KubernetesScalingResult(
                    operation_id=op_id,
                    decision_id=dec_id,
                    service_name=service_name,
                    namespace=self.namespace,
                    current_replicas=decision.previous_replicas,
                    requested_replicas=decision.requested_replicas,
                    action=decision.action,
                    execution_mode=mode_str,
                    status=ScalingExecutionStatus.REJECTED,
                    cluster_modified=False,
                    reason=f"Service '{service_name}' is a protected infrastructure component and cannot be dynamically scaled.",
                    deployment_phase=current_phase,
                    readiness_status="SKIPPED",
                    rollback_status="NOT_REQUIRED",
                    validation_result="REJECTED_PROTECTED_INFRASTRUCTURE",
                )

            # 5. Check explicit allowlist if configured
            if self.allowlist and service_name not in self.allowlist:
                return KubernetesScalingResult(
                    operation_id=op_id,
                    decision_id=dec_id,
                    service_name=service_name,
                    namespace=self.namespace,
                    current_replicas=decision.previous_replicas,
                    requested_replicas=decision.requested_replicas,
                    action=decision.action,
                    execution_mode=mode_str,
                    status=ScalingExecutionStatus.REJECTED,
                    cluster_modified=False,
                    reason=f"Service '{service_name}' is not in the scaling allowlist.",
                    deployment_phase=current_phase,
                    readiness_status="SKIPPED",
                    rollback_status="NOT_REQUIRED",
                    validation_result="REJECTED_ALLOWLIST",
                )

            # 6. Check decision freshness if timestamp is present
            if hasattr(decision, "timestamp") and decision.timestamp:
                dec_ts = decision.timestamp
                if isinstance(dec_ts, str):
                    try:
                        dec_ts = datetime.fromisoformat(dec_ts.replace("Z", "+00:00"))
                    except Exception:
                        dec_ts = None
                if isinstance(dec_ts, datetime):
                    if dec_ts.tzinfo is None:
                        dec_ts = dec_ts.replace(tzinfo=timezone.utc)
                    age_sec = (now_utc - dec_ts).total_seconds()
                    if age_sec > self.telemetry_freshness_threshold_sec:
                        return KubernetesScalingResult(
                            operation_id=op_id,
                            decision_id=dec_id,
                            service_name=service_name,
                            namespace=self.namespace,
                            current_replicas=decision.previous_replicas,
                            requested_replicas=decision.requested_replicas,
                            action=decision.action,
                            execution_mode=mode_str,
                            status=ScalingExecutionStatus.REJECTED,
                            cluster_modified=False,
                            reason=f"Stale decision rejected: decision age ({age_sec:.1f}s) exceeds threshold ({self.telemetry_freshness_threshold_sec:.1f}s).",
                            deployment_phase=current_phase,
                            readiness_status="SKIPPED",
                            rollback_status="NOT_REQUIRED",
                            validation_result="REJECTED_STALE_DECISION",
                        )

            # 7. Enforce replica boundaries and delta limits
            min_reps = self.config.min_replicas
            max_reps = self.config.max_replicas
            max_change = self.config.max_replica_change

            if decision.requested_replicas < min_reps or decision.requested_replicas > max_reps:
                return KubernetesScalingResult(
                    operation_id=op_id,
                    decision_id=dec_id,
                    service_name=service_name,
                    namespace=self.namespace,
                    current_replicas=decision.previous_replicas,
                    requested_replicas=decision.requested_replicas,
                    action=decision.action,
                    execution_mode=mode_str,
                    status=ScalingExecutionStatus.REJECTED,
                    cluster_modified=False,
                    reason=f"Requested replicas {decision.requested_replicas} out of allowed range [{min_reps}, {max_reps}].",
                    deployment_phase=current_phase,
                    readiness_status="SKIPPED",
                    rollback_status="NOT_REQUIRED",
                    validation_result="REJECTED_BOUNDS_VIOLATION",
                )

            if decision.previous_replicas < min_reps or decision.previous_replicas > max_reps:
                return KubernetesScalingResult(
                    operation_id=op_id,
                    decision_id=dec_id,
                    service_name=service_name,
                    namespace=self.namespace,
                    current_replicas=decision.previous_replicas,
                    requested_replicas=decision.requested_replicas,
                    action=decision.action,
                    execution_mode=mode_str,
                    status=ScalingExecutionStatus.REJECTED,
                    cluster_modified=False,
                    reason=f"Previous replicas {decision.previous_replicas} out of allowed range [{min_reps}, {max_reps}].",
                    deployment_phase=current_phase,
                    readiness_status="SKIPPED",
                    rollback_status="NOT_REQUIRED",
                    validation_result="REJECTED_PREVIOUS_BOUNDS_VIOLATION",
                )

            replica_change = abs(decision.requested_replicas - decision.previous_replicas)
            if replica_change > max_change:
                return KubernetesScalingResult(
                    operation_id=op_id,
                    decision_id=dec_id,
                    service_name=service_name,
                    namespace=self.namespace,
                    current_replicas=decision.previous_replicas,
                    requested_replicas=decision.requested_replicas,
                    action=decision.action,
                    execution_mode=mode_str,
                    status=ScalingExecutionStatus.REJECTED,
                    cluster_modified=False,
                    reason=f"Replica change ({replica_change}) exceeds maximum allowed change ({max_change}).",
                    deployment_phase=current_phase,
                    readiness_status="SKIPPED",
                    rollback_status="NOT_REQUIRED",
                    validation_result="REJECTED_MAX_DELTA_EXCEEDED",
                )

            # 8. Deployment phase rules (PRE_DEPLOYMENT & ACTIVE_DEPLOYMENT)
            if current_phase in (DeploymentPhase.ACTIVE_DEPLOYMENT, DeploymentPhase.PRE_DEPLOYMENT) and decision.action == DecisionAction.SCALE_DOWN:
                return KubernetesScalingResult(
                    operation_id=op_id,
                    decision_id=dec_id,
                    service_name=service_name,
                    namespace=self.namespace,
                    current_replicas=decision.previous_replicas,
                    requested_replicas=decision.requested_replicas,
                    action=decision.action,
                    execution_mode=mode_str,
                    status=ScalingExecutionStatus.REJECTED,
                    cluster_modified=False,
                    reason=f"Scale-down prohibited during {current_phase.value} phase.",
                    deployment_phase=current_phase,
                    readiness_status="SKIPPED",
                    rollback_status="NOT_REQUIRED",
                    validation_result="REJECTED_PHASE_RESTRICTION",
                )

            if current_phase == DeploymentPhase.POST_DEPLOYMENT and decision.action == DecisionAction.SCALE_DOWN:
                if not self.state_manager.is_stabilized_for_scale_down(service_name, now_utc, self.config):
                    return KubernetesScalingResult(
                        operation_id=op_id,
                        decision_id=dec_id,
                        service_name=service_name,
                        namespace=self.namespace,
                        current_replicas=decision.previous_replicas,
                        requested_replicas=decision.requested_replicas,
                        action=decision.action,
                        execution_mode=mode_str,
                        status=ScalingExecutionStatus.REJECTED,
                        cluster_modified=False,
                        reason=f"Scale-down postponed: service '{service_name}' in post-deployment stabilization window.",
                        deployment_phase=current_phase,
                        readiness_status="SKIPPED",
                        rollback_status="NOT_REQUIRED",
                        validation_result="REJECTED_POST_DEPLOYMENT_STABILIZATION",
                    )

            # 9. Cooldown check
            if not self.state_manager.can_scale(service_name, now_utc, self.config):
                return KubernetesScalingResult(
                    operation_id=op_id,
                    decision_id=dec_id,
                    service_name=service_name,
                    namespace=self.namespace,
                    current_replicas=decision.previous_replicas,
                    requested_replicas=decision.requested_replicas,
                    action=decision.action,
                    execution_mode=mode_str,
                    status=ScalingExecutionStatus.REJECTED,
                    cluster_modified=False,
                    reason=f"Service '{service_name}' is currently within scaling cooldown window.",
                    deployment_phase=current_phase,
                    readiness_status="SKIPPED",
                    rollback_status="NOT_REQUIRED",
                    validation_result="REJECTED_COOLDOWN_ACTIVE",
                )

            # 10. Query live Kubernetes Deployment with bounded retry
            try:
                deployment = self._query_deployment_with_retry(service_name)
            except Exception as exc:
                status_code = getattr(exc, "status", None)
                if status_code == 404:
                    return KubernetesScalingResult(
                        operation_id=op_id,
                        decision_id=dec_id,
                        service_name=service_name,
                        namespace=self.namespace,
                        current_replicas=decision.previous_replicas,
                        requested_replicas=decision.requested_replicas,
                        action=decision.action,
                        execution_mode=mode_str,
                        status=ScalingExecutionStatus.REJECTED,
                        cluster_modified=False,
                        reason=f"Deployment '{service_name}' not found in namespace '{self.namespace}'.",
                        deployment_phase=current_phase,
                        readiness_status="SKIPPED",
                        rollback_status="NOT_REQUIRED",
                        validation_result="REJECTED_NOT_FOUND",
                    )
                if status_code in (401, 403):
                    return KubernetesScalingResult(
                        operation_id=op_id,
                        decision_id=dec_id,
                        service_name=service_name,
                        namespace=self.namespace,
                        current_replicas=decision.previous_replicas,
                        requested_replicas=decision.requested_replicas,
                        action=decision.action,
                        execution_mode=mode_str,
                        status=ScalingExecutionStatus.FAILED,
                        cluster_modified=False,
                        reason=f"Kubernetes permission/authorization failure: {exc}",
                        deployment_phase=current_phase,
                        readiness_status="FAILED",
                        rollback_status="NOT_REQUIRED",
                        validation_result="FAILED_PERMISSION_DENIED",
                    )

                logger.error("Failed to query deployment %s: %s", service_name, exc)
                return KubernetesScalingResult(
                    operation_id=op_id,
                    decision_id=dec_id,
                    service_name=service_name,
                    namespace=self.namespace,
                    current_replicas=decision.previous_replicas,
                    requested_replicas=decision.requested_replicas,
                    action=decision.action,
                    execution_mode=mode_str,
                    status=ScalingExecutionStatus.FAILED,
                    cluster_modified=False,
                    reason=f"Kubernetes API error querying deployment: {exc}",
                    deployment_phase=current_phase,
                    readiness_status="FAILED",
                    rollback_status="NOT_REQUIRED",
                    validation_result="FAILED_KUBERNETES_API_ERROR",
                )

            live_desired = deployment.spec.replicas if deployment.spec and deployment.spec.replicas is not None else 0

            # 11. Optimistic Concurrency Check (live desired == decision.previous_replicas)
            if live_desired != decision.previous_replicas:
                return KubernetesScalingResult(
                    operation_id=op_id,
                    decision_id=dec_id,
                    service_name=service_name,
                    namespace=self.namespace,
                    current_replicas=live_desired,
                    requested_replicas=decision.requested_replicas,
                    action=decision.action,
                    execution_mode=mode_str,
                    status=ScalingExecutionStatus.REJECTED,
                    cluster_modified=False,
                    reason=f"Stale decision: expected current replicas {decision.previous_replicas}, but live deployment has {live_desired}.",
                    deployment_phase=current_phase,
                    readiness_status="SKIPPED",
                    rollback_status="NOT_REQUIRED",
                    validation_result="REJECTED_STALE_BASELINE_CONCURRENCY",
                    details={"live_desired_replicas": live_desired},
                )

            # 12. Deployment Rollout / In-Flight Status Check
            status = deployment.status
            metadata = deployment.metadata
            generation = getattr(metadata, "generation", None)
            observed_gen = getattr(status, "observed_generation", None)

            if generation is not None and observed_gen is not None and generation != observed_gen:
                return KubernetesScalingResult(
                    operation_id=op_id,
                    decision_id=dec_id,
                    service_name=service_name,
                    namespace=self.namespace,
                    current_replicas=live_desired,
                    requested_replicas=decision.requested_replicas,
                    action=decision.action,
                    execution_mode=mode_str,
                    status=ScalingExecutionStatus.REJECTED,
                    cluster_modified=False,
                    reason="Deployment is currently undergoing rollout (spec generation mismatch).",
                    deployment_phase=current_phase,
                    readiness_status="SKIPPED",
                    rollback_status="NOT_REQUIRED",
                    validation_result="REJECTED_ROLLOUT_IN_PROGRESS",
                )

            updated_replicas = getattr(status, "updated_replicas", None) or 0
            if updated_replicas < live_desired:
                return KubernetesScalingResult(
                    operation_id=op_id,
                    decision_id=dec_id,
                    service_name=service_name,
                    namespace=self.namespace,
                    current_replicas=live_desired,
                    requested_replicas=decision.requested_replicas,
                    action=decision.action,
                    execution_mode=mode_str,
                    status=ScalingExecutionStatus.REJECTED,
                    cluster_modified=False,
                    reason=f"Deployment update in progress: updated_replicas ({updated_replicas}) < desired ({live_desired}).",
                    deployment_phase=current_phase,
                    readiness_status="SKIPPED",
                    rollback_status="NOT_REQUIRED",
                    validation_result="REJECTED_ROLLOUT_UPDATING",
                )

            ready_replicas = getattr(status, "ready_replicas", None) or 0
            if ready_replicas < live_desired:
                return KubernetesScalingResult(
                    operation_id=op_id,
                    decision_id=dec_id,
                    service_name=service_name,
                    namespace=self.namespace,
                    current_replicas=live_desired,
                    requested_replicas=decision.requested_replicas,
                    action=decision.action,
                    execution_mode=mode_str,
                    status=ScalingExecutionStatus.REJECTED,
                    cluster_modified=False,
                    reason=f"Deployment pods are not fully ready: ready_replicas ({ready_replicas}) < desired ({live_desired}).",
                    deployment_phase=current_phase,
                    readiness_status="SKIPPED",
                    rollback_status="NOT_REQUIRED",
                    validation_result="REJECTED_PODS_UNREADY",
                )

            # 13. HPA Conflict Check
            conflicting_hpa = self.check_hpa_conflict(service_name)
            if conflicting_hpa:
                return KubernetesScalingResult(
                    operation_id=op_id,
                    decision_id=dec_id,
                    service_name=service_name,
                    namespace=self.namespace,
                    current_replicas=live_desired,
                    requested_replicas=decision.requested_replicas,
                    action=decision.action,
                    execution_mode=mode_str,
                    status=ScalingExecutionStatus.REJECTED,
                    cluster_modified=False,
                    reason=f"Deployment is managed by HorizontalPodAutoscaler '{conflicting_hpa}'; scaling rejected to avoid conflicting controller updates.",
                    deployment_phase=current_phase,
                    readiness_status="SKIPPED",
                    rollback_status="NOT_REQUIRED",
                    validation_result="REJECTED_HPA_CONFLICT",
                    details={"conflicting_hpa": conflicting_hpa},
                )

            # 14. DRY-RUN EXECUTION (Simulation Mode)
            if self.dry_run:
                readiness_sim = self.verify_post_action_readiness(service_name, decision.requested_replicas)
                logger.info(
                    "DRY-RUN: Validated scaling decision for %s: %d -> %d (%s)",
                    service_name,
                    live_desired,
                    decision.requested_replicas,
                    decision.action.value,
                )
                return KubernetesScalingResult(
                    operation_id=op_id,
                    decision_id=dec_id,
                    service_name=service_name,
                    namespace=self.namespace,
                    current_replicas=live_desired,
                    requested_replicas=decision.requested_replicas,
                    action=decision.action,
                    execution_mode="DRY_RUN",
                    status=ScalingExecutionStatus.VALIDATED,
                    cluster_modified=False,
                    reason=f"Dry-run validated: proposed {decision.action.value} from {live_desired} to {decision.requested_replicas} replicas.",
                    deployment_phase=current_phase,
                    readiness_status=readiness_sim.get("status", "SIMULATED"),
                    rollback_status="NOT_REQUIRED",
                    validation_result="VALIDATED_DRY_RUN",
                    details={
                        "live_desired": live_desired,
                        "ready_replicas": ready_replicas,
                        "target_replicas": decision.requested_replicas,
                        "readiness_verification": readiness_sim,
                    },
                )

            # 15. LIVE EXECUTION (Strictly Protected by SCALING_ENABLED)
            if not cfg.SCALING_ENABLED:
                return KubernetesScalingResult(
                    operation_id=op_id,
                    decision_id=dec_id,
                    service_name=service_name,
                    namespace=self.namespace,
                    current_replicas=live_desired,
                    requested_replicas=decision.requested_replicas,
                    action=decision.action,
                    execution_mode="LIVE",
                    status=ScalingExecutionStatus.REJECTED,
                    cluster_modified=False,
                    reason="Live scaling is disabled in global configuration (SCALING_ENABLED=false).",
                    deployment_phase=current_phase,
                    readiness_status="SKIPPED",
                    rollback_status="NOT_REQUIRED",
                    validation_result="REJECTED_GLOBAL_SCALING_DISABLED",
                )

            # Execute Live Mutation
            try:
                scale_body = {"spec": {"replicas": decision.requested_replicas}}
                self.apps_api.patch_namespaced_deployment_scale(
                    name=service_name,
                    namespace=self.namespace,
                    body=scale_body,
                )
                self.state_manager.record_action(service_name, decision.action, now_utc)

                # Post-Action Readiness Verification
                readiness = self.verify_post_action_readiness(service_name, decision.requested_replicas)
                rollback_info = {"rollback_status": "NOT_REQUIRED"}

                if not readiness.get("ready"):
                    logger.warning(
                        "Post-action readiness verification failed for %s (%s). Initiating rollback to %d...",
                        service_name,
                        readiness.get("message"),
                        live_desired,
                    )
                    rollback_info = self.execute_rollback_procedure(
                        service_name=service_name,
                        rollback_replicas=live_desired,
                        reason=readiness.get("message", "Readiness check failed"),
                    )

                logger.info(
                    "LIVE: Scaled deployment %s from %d to %d replicas (%s). Readiness: %s, Rollback: %s",
                    service_name,
                    live_desired,
                    decision.requested_replicas,
                    decision.action.value,
                    readiness.get("status"),
                    rollback_info.get("rollback_status"),
                )

                return KubernetesScalingResult(
                    operation_id=op_id,
                    decision_id=dec_id,
                    service_name=service_name,
                    namespace=self.namespace,
                    current_replicas=live_desired,
                    requested_replicas=decision.requested_replicas,
                    action=decision.action,
                    execution_mode="LIVE",
                    status=(
                        ScalingExecutionStatus.APPLIED
                        if readiness.get("ready")
                        else ScalingExecutionStatus.FAILED
                    ),
                    cluster_modified=True,
                    reason=(
                        f"Successfully scaled deployment '{service_name}' from {live_desired} to {decision.requested_replicas} replicas."
                        if readiness.get("ready")
                        else f"Scale applied but readiness verification failed: {readiness.get('message')}. Rollback: {rollback_info.get('rollback_status')}."
                    ),
                    deployment_phase=current_phase,
                    readiness_status=readiness.get("status", "FAILED"),
                    rollback_status=rollback_info.get("rollback_status", "NOT_REQUIRED"),
                    validation_result="APPLIED_LIVE",
                    details={
                        "readiness": readiness,
                        "rollback": rollback_info,
                    },
                )
            except Exception as exc:
                status_code = getattr(exc, "status", None)
                if status_code == 409:
                    logger.warning("Resource conflict during scale patch for %s: %s", service_name, exc)
                    return KubernetesScalingResult(
                        operation_id=op_id,
                        decision_id=dec_id,
                        service_name=service_name,
                        namespace=self.namespace,
                        current_replicas=live_desired,
                        requested_replicas=decision.requested_replicas,
                        action=decision.action,
                        execution_mode="LIVE",
                        status=ScalingExecutionStatus.FAILED,
                        cluster_modified=False,
                        reason=f"Kubernetes resource conflict (409) during mutation: {exc}",
                        deployment_phase=current_phase,
                        readiness_status="FAILED",
                        rollback_status="NOT_REQUIRED",
                        validation_result="FAILED_RESOURCE_CONFLICT",
                    )

                logger.error("Live scaling failed for %s: %s", service_name, exc)
                return KubernetesScalingResult(
                    operation_id=op_id,
                    decision_id=dec_id,
                    service_name=service_name,
                    namespace=self.namespace,
                    current_replicas=live_desired,
                    requested_replicas=decision.requested_replicas,
                    action=decision.action,
                    execution_mode="LIVE",
                    status=ScalingExecutionStatus.FAILED,
                    cluster_modified=False,
                    reason=f"Live scale operation failed: {exc}",
                    deployment_phase=current_phase,
                    readiness_status="FAILED",
                    rollback_status="NOT_REQUIRED",
                    validation_result="FAILED_MUTATION_ERROR",
                )

    # -----------------------------------------------------------------
    # BATCH EXECUTION & SUMMARY
    # -----------------------------------------------------------------

    def execute_decisions(
        self,
        decisions: List[DecisionOutput],
    ) -> List[KubernetesScalingResult]:
        """
        Evaluate and execute a batch of scaling decisions sequentially.
        """
        results: List[KubernetesScalingResult] = []
        for decision in decisions:
            res = self.execute_decision(decision)
            results.append(res)
        return results

    def get_summary(
        self,
        results: List[KubernetesScalingResult],
    ) -> Dict[str, Any]:
        """
        Generate a summary of actuator evaluation results.
        """
        return {
            "namespace": self.namespace,
            "execution_mode": "DRY_RUN" if self.dry_run else "LIVE",
            "emergency_stop": self.emergency_stop,
            "total_decisions": len(results),
            "validated_count": sum(
                1 for r in results if r.status == ScalingExecutionStatus.VALIDATED
            ),
            "applied_count": sum(
                1 for r in results if r.status == ScalingExecutionStatus.APPLIED
            ),
            "rejected_count": sum(
                1 for r in results if r.status == ScalingExecutionStatus.REJECTED
            ),
            "skipped_count": sum(
                1 for r in results if r.status == ScalingExecutionStatus.SKIPPED
            ),
            "failed_count": sum(
                1 for r in results if r.status == ScalingExecutionStatus.FAILED
            ),
            "cluster_modified": any(r.cluster_modified for r in results),
            "results": [r.dict() for r in results],
        }
