"""
Kubernetes scaling actuator for the DPBPS framework.

Translates DPBPS DecisionOutput scaling decisions into safe Kubernetes
Deployment replica updates, with comprehensive safety checks and dry-run execution.

Safety principles:
1. Dry-run mode by default; live cluster modifications require explicit enablement
   (dry_run=False and cfg.SCALING_ENABLED=True).
2. Unknown services, uninstrumented components, and infrastructure (e.g. redis-cart,
   opentelemetrycollector) are strictly rejected from scaling.
3. Replica counts must fall within configured [min_replicas, max_replicas] bounds.
4. Maximum replica change per decision is strictly enforced (max_replica_change).
5. Scale-down operations are prohibited during ACTIVE_DEPLOYMENT.
6. Scale-down operations during POST_DEPLOYMENT respect the stabilization window.
7. Active deployment rollouts, generation mismatches, and unready pods prevent scaling.
8. HorizontalPodAutoscaler (HPA) conflicts are detected and rejected to prevent controller fighting.
9. Stale decisions (concurrency conflicts where live replica count differs from decision baseline) are rejected.
10. Cooldown intervals are enforced to prevent rapid oscillation.
11. Kubernetes API errors are caught and surfaced safely without disrupting other evaluations.
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

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
# PROTECTED INFRASTRUCTURE COMPONENTS
# ---------------------------------------------------------------------
# These services must never be scaled dynamically by the DPBPS actuator.
# Redis is stateful; OpenTelemetry Collector is an infra agent; loadgenerator
# is controlled by benchmark harnesses.

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
    replica operations with full pre-flight validation and dry-run execution.
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
    ):
        """
        Initialize the Kubernetes scaling actuator.

        Args:
            namespace: Target Kubernetes namespace (default: "online-boutique").
            apps_api: Optional Kubernetes AppsV1Api instance (for mocking/DI).
            autoscaling_api: Optional Kubernetes Autoscaling API instance (for mocking/DI).
            state_manager: Optional DeploymentStateManager instance (for mocking/DI).
            config: Optional ScalingConfig defining replica limits and cooldowns.
            dry_run: If True, validate and simulate without modifying the cluster.
            allowlist: Optional list of service names authorized for scaling.
        """
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
    # HPA CONFLICT DETECTION
    # -----------------------------------------------------------------

    def check_hpa_conflict(self, deployment_name: str) -> Optional[str]:
        """
        Check if any HorizontalPodAutoscaler in the namespace targets this deployment.

        Returns:
            The name of the conflicting HPA if found, else None.
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
    # DECISION EXECUTION
    # -----------------------------------------------------------------

    def execute_decision(self, decision: DecisionOutput) -> KubernetesScalingResult:
        """
        Validate and execute a single DPBPS scaling decision.

        In dry-run mode (default), performs all pre-flight safety validations,
        queries the live deployment state, checks for conflicts, and returns
        a validated result without modifying the cluster.
        """
        service_name = decision.service_name
        current_phase = decision.phase or self.state_manager.get_phase()
        now_utc = datetime.now(timezone.utc)
        mode_str = "DRY_RUN" if self.dry_run else "LIVE"

        # 1. Non-scaling decisions: HOLD or INSUFFICIENT_TELEMETRY
        if decision.action == DecisionAction.HOLD:
            return KubernetesScalingResult(
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
            )

        if decision.action == DecisionAction.INSUFFICIENT_TELEMETRY:
            return KubernetesScalingResult(
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
            )

        # 2. No-op replica change
        if decision.requested_replicas == decision.previous_replicas:
            return KubernetesScalingResult(
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
            )

        # 3. Reject protected infrastructure components
        if service_name in PROTECTED_INFRASTRUCTURE:
            return KubernetesScalingResult(
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
            )

        # 4. Check explicit allowlist if configured
        if self.allowlist and service_name not in self.allowlist:
            return KubernetesScalingResult(
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
            )

        # 5. Enforce replica boundaries
        min_reps = self.config.min_replicas
        max_reps = self.config.max_replicas
        max_change = self.config.max_replica_change

        if decision.requested_replicas < min_reps or decision.requested_replicas > max_reps:
            return KubernetesScalingResult(
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
            )

        if decision.previous_replicas < min_reps or decision.previous_replicas > max_reps:
            return KubernetesScalingResult(
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
            )

        replica_change = abs(decision.requested_replicas - decision.previous_replicas)
        if replica_change > max_change:
            return KubernetesScalingResult(
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
            )

        # 6. Deployment phase rules
        if current_phase == DeploymentPhase.ACTIVE_DEPLOYMENT and decision.action == DecisionAction.SCALE_DOWN:
            return KubernetesScalingResult(
                service_name=service_name,
                namespace=self.namespace,
                current_replicas=decision.previous_replicas,
                requested_replicas=decision.requested_replicas,
                action=decision.action,
                execution_mode=mode_str,
                status=ScalingExecutionStatus.REJECTED,
                cluster_modified=False,
                reason="Scale-down prohibited during ACTIVE_DEPLOYMENT phase.",
                deployment_phase=current_phase,
            )

        if current_phase == DeploymentPhase.POST_DEPLOYMENT and decision.action == DecisionAction.SCALE_DOWN:
            if not self.state_manager.is_stabilized_for_scale_down(service_name, now_utc, self.config):
                return KubernetesScalingResult(
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
                )

        # 7. Cooldown check
        if not self.state_manager.can_scale(service_name, now_utc, self.config):
            return KubernetesScalingResult(
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
            )

        # 8. Query live Kubernetes Deployment
        try:
            deployment = self.apps_api.read_namespaced_deployment(
                name=service_name,
                namespace=self.namespace,
            )
        except Exception as exc:
            # Handle ApiException or 404
            status_code = getattr(exc, "status", None)
            if status_code == 404:
                return KubernetesScalingResult(
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
                )

            logger.error("Failed to query deployment %s: %s", service_name, exc)
            return KubernetesScalingResult(
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
            )

        live_desired = deployment.spec.replicas if deployment.spec and deployment.spec.replicas is not None else 0

        # 9. Verify Optimistic Concurrency / State Freshness
        if live_desired != decision.previous_replicas:
            return KubernetesScalingResult(
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
                details={"live_desired_replicas": live_desired},
            )

        # 10. Check deployment rollout / in-flight status
        status = deployment.status
        metadata = deployment.metadata
        generation = getattr(metadata, "generation", None)
        observed_gen = getattr(status, "observed_generation", None)

        if generation is not None and observed_gen is not None and generation != observed_gen:
            return KubernetesScalingResult(
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
            )

        updated_replicas = getattr(status, "updated_replicas", None) or 0
        if updated_replicas < live_desired:
            return KubernetesScalingResult(
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
            )

        ready_replicas = getattr(status, "ready_replicas", None) or 0
        if ready_replicas < live_desired:
            return KubernetesScalingResult(
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
            )

        # 11. Check HPA conflict
        conflicting_hpa = self.check_hpa_conflict(service_name)
        if conflicting_hpa:
            return KubernetesScalingResult(
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
                details={"conflicting_hpa": conflicting_hpa},
            )

        # 12. Dry-Run Execution
        if self.dry_run:
            logger.info(
                "DRY-RUN: Validated scaling decision for %s: %d -> %d (%s)",
                service_name,
                live_desired,
                decision.requested_replicas,
                decision.action.value,
            )
            return KubernetesScalingResult(
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
                details={
                    "live_desired": live_desired,
                    "ready_replicas": ready_replicas,
                    "target_replicas": decision.requested_replicas,
                },
            )

        # 13. Live Mode (Safety Guarded)
        if not cfg.SCALING_ENABLED:
            return KubernetesScalingResult(
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
            )

        # Execute live scale patch
        try:
            scale_body = {"spec": {"replicas": decision.requested_replicas}}
            self.apps_api.patch_namespaced_deployment_scale(
                name=service_name,
                namespace=self.namespace,
                body=scale_body,
            )
            self.state_manager.record_action(service_name, decision.action, now_utc)

            logger.info(
                "LIVE: Scaled deployment %s from %d to %d replicas (%s)",
                service_name,
                live_desired,
                decision.requested_replicas,
                decision.action.value,
            )
            return KubernetesScalingResult(
                service_name=service_name,
                namespace=self.namespace,
                current_replicas=live_desired,
                requested_replicas=decision.requested_replicas,
                action=decision.action,
                execution_mode="LIVE",
                status=ScalingExecutionStatus.APPLIED,
                cluster_modified=True,
                reason=f"Successfully scaled deployment '{service_name}' from {live_desired} to {decision.requested_replicas} replicas.",
                deployment_phase=current_phase,
            )
        except Exception as exc:
            logger.error("Live scaling failed for %s: %s", service_name, exc)
            return KubernetesScalingResult(
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
            )

    # -----------------------------------------------------------------
    # BATCH EXECUTION
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

