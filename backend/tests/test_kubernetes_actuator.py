"""
Automated unit tests for DPBPS KubernetesScalingActuator.

Verifies:
1. Valid scale-up in dry-run mode (status=VALIDATED, cluster_modified=False).
2. Valid scale-down in dry-run mode (status=VALIDATED, cluster_modified=False).
3. HOLD decision handling (status=SKIPPED).
4. INSUFFICIENT_TELEMETRY decision handling (status=SKIPPED).
5. No-op replica change handling (status=SKIPPED).
6. Invalid deployment (404 Not Found -> status=REJECTED).
7. Invalid replica count boundaries (min/max limits -> status=REJECTED).
8. Maximum replica change exceeded (status=REJECTED).
9. Deployment not ready (unready pods, rollout in progress -> status=REJECTED).
10. ACTIVE_DEPLOYMENT scale-down rejection (scale-down blocked, scale-up permitted).
11. POST_DEPLOYMENT stabilization window enforcement.
12. Cooldown period enforcement.
13. Concurrent or stale deployment state detection (optimistic concurrency -> status=REJECTED).
14. Kubernetes API failure handling (status=FAILED, cluster_modified=False).
15. Dry-run safety: write operations (patch_namespaced_deployment_scale) are never called.
16. Infrastructure components exclusion (redis-cart, opentelemetrycollector, loadgenerator).
17. HPA conflict detection and rejection.
18. Scaling allowlist enforcement.
19. Batch decision execution and summary generation.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional
from unittest.mock import MagicMock
import pytest

from kubernetes.client.rest import ApiException

from backend.scaling.models import (
    DecisionAction,
    DecisionOutput,
    DeploymentPhase,
    ScalingConfig,
)
from backend.scaling.deployment_state import DeploymentStateManager
from backend.scaling.kubernetes.actuator import (
    KubernetesScalingActuator,
    KubernetesScalingResult,
    ScalingExecutionStatus,
    PROTECTED_INFRASTRUCTURE,
)


# ---------------------------------------------------------------------
# FIXTURES AND HELPERS
# ---------------------------------------------------------------------

def make_decision(
    service_name: str = "frontend",
    action: DecisionAction = DecisionAction.SCALE_UP,
    previous: int = 1,
    requested: int = 2,
    phase: DeploymentPhase = DeploymentPhase.NORMAL_OPERATION,
    reason: str = "High CPU load",
) -> DecisionOutput:
    """Create a test DecisionOutput object."""
    return DecisionOutput(
        service_name=service_name,
        action=action,
        previous_replicas=previous,
        requested_replicas=requested,
        phase=phase,
        reason=reason,
        timestamp=datetime.now(timezone.utc),
        simulated=False,
    )


def make_mock_k8s_deployment(
    name: str = "frontend",
    desired_replicas: int = 1,
    ready_replicas: int = 1,
    updated_replicas: int = 1,
    generation: int = 1,
    observed_generation: int = 1,
) -> MagicMock:
    """Create a mock Kubernetes Deployment API object with status and metadata."""
    dep = MagicMock()
    dep.metadata.name = name
    dep.metadata.generation = generation

    dep.spec = MagicMock()
    dep.spec.replicas = desired_replicas

    dep.status = MagicMock()
    dep.status.replicas = desired_replicas
    dep.status.ready_replicas = ready_replicas
    dep.status.updated_replicas = updated_replicas
    dep.status.observed_generation = observed_generation

    return dep


def make_mock_hpa_list(target_deployment_name: Optional[str] = None, hpa_name: str = "frontend-hpa") -> MagicMock:
    """Create a mock HPA list."""
    hpa_list = MagicMock()
    if target_deployment_name:
        hpa = MagicMock()
        hpa.metadata.name = hpa_name
        hpa.spec.scale_target_ref.name = target_deployment_name
        hpa.spec.scale_target_ref.kind = "Deployment"
        hpa_list.items = [hpa]
    else:
        hpa_list.items = []
    return hpa_list


# ---------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------

def test_1_valid_scale_up_dry_run():
    """Verify that a valid scale-up decision in dry-run mode returns VALIDATED without modifying cluster."""
    mock_apps = MagicMock()
    mock_apps.read_namespaced_deployment.return_value = make_mock_k8s_deployment(
        name="frontend", desired_replicas=1, ready_replicas=1, updated_replicas=1
    )

    actuator = KubernetesScalingActuator(
        namespace="online-boutique",
        apps_api=mock_apps,
        dry_run=True,
    )

    decision = make_decision(service_name="frontend", action=DecisionAction.SCALE_UP, previous=1, requested=2)
    result = actuator.execute_decision(decision)

    assert result.status == ScalingExecutionStatus.VALIDATED
    assert result.execution_mode == "DRY_RUN"
    assert result.cluster_modified is False
    assert result.service_name == "frontend"
    assert result.current_replicas == 1
    assert result.requested_replicas == 2
    assert "Dry-run validated" in result.reason
    mock_apps.patch_namespaced_deployment_scale.assert_not_called()


def test_2_valid_scale_down_dry_run():
    """Verify that a valid scale-down decision in dry-run mode returns VALIDATED without modifying cluster."""
    mock_apps = MagicMock()
    mock_apps.read_namespaced_deployment.return_value = make_mock_k8s_deployment(
        name="checkoutservice", desired_replicas=3, ready_replicas=3, updated_replicas=3
    )

    actuator = KubernetesScalingActuator(
        namespace="online-boutique",
        apps_api=mock_apps,
        dry_run=True,
    )

    decision = make_decision(service_name="checkoutservice", action=DecisionAction.SCALE_DOWN, previous=3, requested=2)
    result = actuator.execute_decision(decision)

    assert result.status == ScalingExecutionStatus.VALIDATED
    assert result.execution_mode == "DRY_RUN"
    assert result.cluster_modified is False
    assert result.current_replicas == 3
    assert result.requested_replicas == 2
    mock_apps.patch_namespaced_deployment_scale.assert_not_called()


def test_3_hold_decision():
    """Verify that HOLD decision is marked as SKIPPED and makes no Kubernetes read or write calls."""
    mock_apps = MagicMock()
    actuator = KubernetesScalingActuator(apps_api=mock_apps, dry_run=True)

    decision = make_decision(action=DecisionAction.HOLD, previous=2, requested=2, reason="Load within limits")
    result = actuator.execute_decision(decision)

    assert result.status == ScalingExecutionStatus.SKIPPED
    assert result.cluster_modified is False
    mock_apps.read_namespaced_deployment.assert_not_called()
    mock_apps.patch_namespaced_deployment_scale.assert_not_called()


def test_4_insufficient_telemetry_decision():
    """Verify that INSUFFICIENT_TELEMETRY decision is marked as SKIPPED and does not scale."""
    mock_apps = MagicMock()
    actuator = KubernetesScalingActuator(apps_api=mock_apps, dry_run=True)

    decision = make_decision(action=DecisionAction.INSUFFICIENT_TELEMETRY, previous=1, requested=1, reason="Metrics stale")
    result = actuator.execute_decision(decision)

    assert result.status == ScalingExecutionStatus.SKIPPED
    assert result.cluster_modified is False
    mock_apps.read_namespaced_deployment.assert_not_called()


def test_5_noop_replica_decision():
    """Verify that decision with requested == previous replicas is SKIPPED as no-op."""
    mock_apps = MagicMock()
    actuator = KubernetesScalingActuator(apps_api=mock_apps, dry_run=True)

    decision = make_decision(action=DecisionAction.SCALE_UP, previous=2, requested=2)
    result = actuator.execute_decision(decision)

    assert result.status == ScalingExecutionStatus.SKIPPED
    assert "no-op" in result.reason
    mock_apps.read_namespaced_deployment.assert_not_called()


def test_6_invalid_deployment_not_found():
    """Verify that targeting a non-existent deployment returns REJECTED."""
    mock_apps = MagicMock()
    mock_apps.read_namespaced_deployment.side_effect = ApiException(status=404, reason="Not Found")

    actuator = KubernetesScalingActuator(apps_api=mock_apps, dry_run=True)
    decision = make_decision(service_name="non-existent-service", action=DecisionAction.SCALE_UP, previous=1, requested=2)

    result = actuator.execute_decision(decision)
    assert result.status == ScalingExecutionStatus.REJECTED
    assert "not found" in result.reason.lower()
    assert result.cluster_modified is False


def test_7_invalid_replica_count_boundaries():
    """Verify that requested replicas outside configured [min, max] limits are REJECTED."""
    mock_apps = MagicMock()
    config = ScalingConfig(min_replicas=1, max_replicas=5, max_replica_change=2)
    actuator = KubernetesScalingActuator(apps_api=mock_apps, config=config, dry_run=True)

    # Requested < min
    dec_below = make_decision(previous=1, requested=0)
    res_below = actuator.execute_decision(dec_below)
    assert res_below.status == ScalingExecutionStatus.REJECTED
    assert "out of allowed range" in res_below.reason

    # Requested > max
    dec_above = make_decision(previous=5, requested=6)
    res_above = actuator.execute_decision(dec_above)
    assert res_above.status == ScalingExecutionStatus.REJECTED
    assert "out of allowed range" in res_above.reason

    # Previous out of range
    dec_prev_invalid = make_decision(previous=0, requested=1)
    res_prev = actuator.execute_decision(dec_prev_invalid)
    assert res_prev.status == ScalingExecutionStatus.REJECTED


def test_8_max_replica_change_exceeded():
    """Verify that replica changes greater than max_replica_change are REJECTED."""
    mock_apps = MagicMock()
    config = ScalingConfig(min_replicas=1, max_replicas=10, max_replica_change=2)
    actuator = KubernetesScalingActuator(apps_api=mock_apps, config=config, dry_run=True)

    # Change is 3 (1 -> 4), max allowed is 2
    decision = make_decision(previous=1, requested=4)
    result = actuator.execute_decision(decision)

    assert result.status == ScalingExecutionStatus.REJECTED
    assert "exceeds maximum allowed change" in result.reason


def test_9_deployment_not_ready():
    """Verify that unready pods or in-progress rollouts reject scaling."""
    mock_apps = MagicMock()

    # Case A: ready_replicas < desired_replicas
    mock_apps.read_namespaced_deployment.return_value = make_mock_k8s_deployment(
        desired_replicas=2, ready_replicas=1, updated_replicas=2
    )
    actuator = KubernetesScalingActuator(apps_api=mock_apps, dry_run=True)
    decision = make_decision(previous=2, requested=3)
    res_a = actuator.execute_decision(decision)
    assert res_a.status == ScalingExecutionStatus.REJECTED
    assert "not fully ready" in res_a.reason

    # Case B: updated_replicas < desired_replicas
    mock_apps.read_namespaced_deployment.return_value = make_mock_k8s_deployment(
        desired_replicas=2, ready_replicas=2, updated_replicas=1
    )
    res_b = actuator.execute_decision(decision)
    assert res_b.status == ScalingExecutionStatus.REJECTED
    assert "update in progress" in res_b.reason

    # Case C: generation != observed_generation
    mock_apps.read_namespaced_deployment.return_value = make_mock_k8s_deployment(
        desired_replicas=2, ready_replicas=2, updated_replicas=2, generation=3, observed_generation=2
    )
    res_c = actuator.execute_decision(decision)
    assert res_c.status == ScalingExecutionStatus.REJECTED
    assert "rollout" in res_c.reason


def test_10_active_deployment_scale_down_rejection():
    """Verify that scale-down is rejected during ACTIVE_DEPLOYMENT, but scale-up is allowed."""
    mock_apps = MagicMock()
    mock_apps.read_namespaced_deployment.return_value = make_mock_k8s_deployment(
        desired_replicas=2, ready_replicas=2, updated_replicas=2
    )
    state_mgr = DeploymentStateManager()
    state_mgr.set_phase(DeploymentPhase.ACTIVE_DEPLOYMENT)

    actuator = KubernetesScalingActuator(apps_api=mock_apps, state_manager=state_mgr, dry_run=True)

    # Scale-down rejected
    dec_down = make_decision(
        action=DecisionAction.SCALE_DOWN, previous=2, requested=1, phase=DeploymentPhase.ACTIVE_DEPLOYMENT
    )
    res_down = actuator.execute_decision(dec_down)
    assert res_down.status == ScalingExecutionStatus.REJECTED
    assert "prohibited during ACTIVE_DEPLOYMENT" in res_down.reason

    # Scale-up accepted
    dec_up = make_decision(
        action=DecisionAction.SCALE_UP, previous=2, requested=3, phase=DeploymentPhase.ACTIVE_DEPLOYMENT
    )
    res_up = actuator.execute_decision(dec_up)
    assert res_up.status == ScalingExecutionStatus.VALIDATED


def test_11_post_deployment_stabilization():
    """Verify that scale-down during POST_DEPLOYMENT respects stabilization window."""
    mock_apps = MagicMock()
    mock_apps.read_namespaced_deployment.return_value = make_mock_k8s_deployment(
        desired_replicas=2, ready_replicas=2, updated_replicas=2
    )
    state_mgr = DeploymentStateManager()
    state_mgr.set_phase(DeploymentPhase.POST_DEPLOYMENT)
    config = ScalingConfig(scale_down_stabilization_sec=60)

    actuator = KubernetesScalingActuator(
        apps_api=mock_apps, state_manager=state_mgr, config=config, dry_run=True
    )

    now = datetime.now(timezone.utc)
    # Simulate scale-down stabilization started 10s ago (< 60s)
    state_mgr.scale_down_stabilization_start["frontend"] = now - timedelta(seconds=10)

    dec_down = make_decision(
        service_name="frontend", action=DecisionAction.SCALE_DOWN, previous=2, requested=1, phase=DeploymentPhase.POST_DEPLOYMENT
    )
    res = actuator.execute_decision(dec_down)
    assert res.status == ScalingExecutionStatus.REJECTED
    assert "post-deployment stabilization window" in res.reason

    # Advance time past 60s
    state_mgr.scale_down_stabilization_start["frontend"] = now - timedelta(seconds=70)
    res_stabilized = actuator.execute_decision(dec_down)
    assert res_stabilized.status == ScalingExecutionStatus.VALIDATED


def test_12_cooldown_enforcement():
    """Verify that scaling actions during the cooldown period are REJECTED."""
    mock_apps = MagicMock()
    state_mgr = DeploymentStateManager()
    config = ScalingConfig(cooldown_sec=30)
    now = datetime.now(timezone.utc)

    # Record action 5 seconds ago
    state_mgr.record_action("cartservice", DecisionAction.SCALE_UP, now - timedelta(seconds=5))

    actuator = KubernetesScalingActuator(
        apps_api=mock_apps, state_manager=state_mgr, config=config, dry_run=True
    )

    decision = make_decision(service_name="cartservice", action=DecisionAction.SCALE_UP, previous=1, requested=2)
    res = actuator.execute_decision(decision)

    assert res.status == ScalingExecutionStatus.REJECTED
    assert "cooldown window" in res.reason


def test_13_concurrent_or_stale_deployment_state():
    """Verify that a decision evaluated against an outdated replica count is REJECTED."""
    mock_apps = MagicMock()
    # Live deployment is at 2 replicas
    mock_apps.read_namespaced_deployment.return_value = make_mock_k8s_deployment(
        desired_replicas=2, ready_replicas=2, updated_replicas=2
    )

    actuator = KubernetesScalingActuator(apps_api=mock_apps, dry_run=True)

    # Decision assumed previous_replicas was 1
    decision = make_decision(previous=1, requested=2)
    result = actuator.execute_decision(decision)

    assert result.status == ScalingExecutionStatus.REJECTED
    assert "Stale decision" in result.reason
    assert "expected current replicas 1, but live deployment has 2" in result.reason


def test_14_kubernetes_api_failure():
    """Verify that Kubernetes API connection/server errors result in FAILED status."""
    mock_apps = MagicMock()
    mock_apps.read_namespaced_deployment.side_effect = RuntimeError("Connection timeout to API server")

    actuator = KubernetesScalingActuator(apps_api=mock_apps, dry_run=True)
    decision = make_decision(previous=1, requested=2)

    result = actuator.execute_decision(decision)
    assert result.status == ScalingExecutionStatus.FAILED
    assert result.cluster_modified is False
    assert "Connection timeout" in result.reason


def test_15_dry_run_does_not_invoke_write():
    """Explicitly verify that dry-run mode never calls write operations even on valid decisions."""
    mock_apps = MagicMock()
    mock_apps.read_namespaced_deployment.return_value = make_mock_k8s_deployment(
        desired_replicas=1, ready_replicas=1, updated_replicas=1
    )

    actuator = KubernetesScalingActuator(apps_api=mock_apps, dry_run=True)
    decision = make_decision(previous=1, requested=2)

    result = actuator.execute_decision(decision)
    assert result.status == ScalingExecutionStatus.VALIDATED

    # Verify no mutation methods were called
    mock_apps.patch_namespaced_deployment_scale.assert_not_called()
    mock_apps.patch_namespaced_deployment.assert_not_called()
    mock_apps.replace_namespaced_deployment.assert_not_called()
    mock_apps.replace_namespaced_deployment_scale.assert_not_called()


def test_16_infrastructure_services_excluded():
    """Verify that infrastructure components are strictly rejected from scaling."""
    mock_apps = MagicMock()
    actuator = KubernetesScalingActuator(apps_api=mock_apps, dry_run=True)

    for infra_svc in ["redis-cart", "opentelemetrycollector", "loadgenerator"]:
        decision = make_decision(service_name=infra_svc, action=DecisionAction.SCALE_UP, previous=1, requested=2)
        result = actuator.execute_decision(decision)

        assert result.status == ScalingExecutionStatus.REJECTED
        assert "protected infrastructure component" in result.reason
        mock_apps.read_namespaced_deployment.assert_not_called()


def test_17_hpa_conflict_rejection():
    """Verify that a deployment managed by an HPA is rejected from manual scaling."""
    mock_apps = MagicMock()
    mock_apps.read_namespaced_deployment.return_value = make_mock_k8s_deployment(
        name="frontend", desired_replicas=1, ready_replicas=1, updated_replicas=1
    )

    mock_autoscaling = MagicMock()
    mock_autoscaling.list_namespaced_horizontal_pod_autoscaler.return_value = make_mock_hpa_list(
        target_deployment_name="frontend", hpa_name="frontend-hpa"
    )

    actuator = KubernetesScalingActuator(
        apps_api=mock_apps,
        autoscaling_api=mock_autoscaling,
        dry_run=True,
    )

    decision = make_decision(service_name="frontend", action=DecisionAction.SCALE_UP, previous=1, requested=2)
    result = actuator.execute_decision(decision)

    assert result.status == ScalingExecutionStatus.REJECTED
    assert "HorizontalPodAutoscaler" in result.reason
    assert "frontend-hpa" in result.reason


def test_18_allowlist_enforcement():
    """Verify that when an allowlist is provided, unlisted services are rejected."""
    mock_apps = MagicMock()
    mock_apps.read_namespaced_deployment.return_value = make_mock_k8s_deployment(
        name="frontend", desired_replicas=1, ready_replicas=1, updated_replicas=1
    )

    actuator = KubernetesScalingActuator(
        apps_api=mock_apps,
        dry_run=True,
        allowlist=["checkoutservice", "cartservice"],  # frontend is NOT in allowlist
    )

    decision = make_decision(service_name="frontend", action=DecisionAction.SCALE_UP, previous=1, requested=2)
    result = actuator.execute_decision(decision)

    assert result.status == ScalingExecutionStatus.REJECTED
    assert "not in the scaling allowlist" in result.reason


def test_19_batch_execution_and_summary():
    """Verify execute_decisions and get_summary aggregate batch results correctly."""
    mock_apps = MagicMock()
    mock_apps.read_namespaced_deployment.side_effect = lambda name, namespace: make_mock_k8s_deployment(
        name=name, desired_replicas=1, ready_replicas=1, updated_replicas=1
    )

    actuator = KubernetesScalingActuator(apps_api=mock_apps, dry_run=True)

    decisions = [
        make_decision(service_name="frontend", action=DecisionAction.SCALE_UP, previous=1, requested=2),
        make_decision(service_name="cartservice", action=DecisionAction.HOLD, previous=1, requested=1),
        make_decision(service_name="redis-cart", action=DecisionAction.SCALE_UP, previous=1, requested=2),
    ]

    results = actuator.execute_decisions(decisions)
    assert len(results) == 3

    assert results[0].status == ScalingExecutionStatus.VALIDATED
    assert results[1].status == ScalingExecutionStatus.SKIPPED
    assert results[2].status == ScalingExecutionStatus.REJECTED

    summary = actuator.get_summary(results)
    assert summary["total_decisions"] == 3
    assert summary["validated_count"] == 1
    assert summary["skipped_count"] == 1
    assert summary["rejected_count"] == 1
    assert summary["cluster_modified"] is False
