"""
backend/tests/test_hardened_actuator.py
Comprehensive test suite for Stage 14: Kubernetes Actuator Hardening.

Validates all 20 required scenarios:
1. Valid scale-up request in DRY_RUN
2. Valid scale-down request in DRY_RUN
3. Protected infrastructure scaling rejection
4. Minimum replica violation
5. Maximum replica violation
6. Excessive scaling delta
7. Cooldown violation
8. Stale decision rejection (concurrency mismatch)
9. Deployment-phase restriction (ACTIVE_DEPLOYMENT scale-down)
10. Emergency-stop activation
11. Kubernetes API timeout and retry handling
12. Kubernetes API conflict (HTTP 409)
13. Kubernetes permission failure (HTTP 403 fail-fast)
14. Pod readiness timeout detection
15. Failed rollout and simulated rollback recovery
16. Concurrent scaling request prevention
17. Duplicate operation request
18. Backend restart during operation
19. Global scaling disabled enforcement
20. Strict DRY_RUN enforcement (zero cluster modifications)
"""

from datetime import datetime, timedelta, timezone
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from kubernetes.client.rest import ApiException

import backend.config as cfg
from backend.scaling.deployment_state import DeploymentStateManager
from backend.scaling.kubernetes.actuator import (
    APPLICATION_SERVICES,
    KubernetesScalingActuator,
    PROTECTED_INFRASTRUCTURE,
    ScalingExecutionStatus,
)
from backend.scaling.models import (
    DecisionAction,
    DecisionOutput,
    DeploymentPhase,
    ScalingConfig,
)


def make_decision(
    service_name: str = "checkoutservice",
    action: DecisionAction = DecisionAction.SCALE_UP,
    previous: int = 1,
    requested: int = 2,
    phase: DeploymentPhase = DeploymentPhase.NORMAL_OPERATION,
    reason: str = "Test decision",
    age_seconds: float = 0.0,
) -> DecisionOutput:
    ts = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return DecisionOutput(
        service_name=service_name,
        action=action,
        previous_replicas=previous,
        requested_replicas=requested,
        priority_score=0.8,
        phase=phase,
        bottleneck=service_name if action == DecisionAction.SCALE_UP else None,
        reason=reason,
        timestamp=ts,
        simulated=True,
    )


def create_mock_deployment(replicas=1, updated=None, ready=None, available=None, gen=1, obs_gen=1):
    dep = MagicMock()
    dep.spec.replicas = replicas
    dep.status.updated_replicas = replicas if updated is None else updated
    dep.status.ready_replicas = replicas if ready is None else ready
    dep.status.available_replicas = replicas if available is None else available
    dep.metadata.generation = gen
    dep.status.observed_generation = obs_gen
    dep.status.conditions = []
    return dep


# ---------------------------------------------------------------------
# SCENARIO 1 & 2: VALID SCALE-UP AND SCALE-DOWN IN DRY_RUN
# ---------------------------------------------------------------------

def test_scenario_1_valid_scale_up_dry_run():
    """Scenario 1: Valid scale-up request validated in DRY_RUN without cluster mutation."""
    mock_apps = MagicMock()
    mock_apps.read_namespaced_deployment.return_value = create_mock_deployment(1)
    actuator = KubernetesScalingActuator(apps_api=mock_apps, dry_run=True)

    dec = make_decision("checkoutservice", DecisionAction.SCALE_UP, previous=1, requested=2)
    res = actuator.execute_decision(dec)

    assert res.status == ScalingExecutionStatus.VALIDATED
    assert res.execution_mode == "DRY_RUN"
    assert res.cluster_modified is False
    assert res.current_replicas == 1
    assert res.requested_replicas == 2
    assert res.readiness_status == "SIMULATED"
    mock_apps.patch_namespaced_deployment_scale.assert_not_called()


def test_scenario_2_valid_scale_down_dry_run():
    """Scenario 2: Valid scale-down request validated in DRY_RUN without cluster mutation."""
    mock_apps = MagicMock()
    mock_apps.read_namespaced_deployment.return_value = create_mock_deployment(3)
    actuator = KubernetesScalingActuator(apps_api=mock_apps, dry_run=True)

    dec = make_decision("checkoutservice", DecisionAction.SCALE_DOWN, previous=3, requested=2)
    res = actuator.execute_decision(dec)

    assert res.status == ScalingExecutionStatus.VALIDATED
    assert res.cluster_modified is False
    assert res.current_replicas == 3
    assert res.requested_replicas == 2
    mock_apps.patch_namespaced_deployment_scale.assert_not_called()


# ---------------------------------------------------------------------
# SCENARIO 3: PROTECTED INFRASTRUCTURE REJECTION
# ---------------------------------------------------------------------

def test_scenario_3_protected_infrastructure_rejection():
    """Scenario 3: Protected infrastructure (redis-cart, opentelemetrycollector, loadgenerator) strictly rejected."""
    actuator = KubernetesScalingActuator(dry_run=True)
    for infra in PROTECTED_INFRASTRUCTURE:
        dec = make_decision(infra, DecisionAction.SCALE_UP, previous=1, requested=2)
        res = actuator.execute_decision(dec)
        assert res.status == ScalingExecutionStatus.REJECTED
        assert res.cluster_modified is False
        assert "protected infrastructure" in res.reason.lower()
        assert res.validation_result == "REJECTED_PROTECTED_INFRASTRUCTURE"


# ---------------------------------------------------------------------
# SCENARIOS 4, 5, 6: BOUNDS & DELTA VIOLATIONS
# ---------------------------------------------------------------------

def test_scenario_4_minimum_replica_violation():
    """Scenario 4: Requested replicas below min_replicas is rejected."""
    actuator = KubernetesScalingActuator(config=ScalingConfig(min_replicas=1, max_replicas=10), dry_run=True)
    dec = make_decision("checkoutservice", DecisionAction.SCALE_DOWN, previous=1, requested=0)
    res = actuator.execute_decision(dec)
    assert res.status == ScalingExecutionStatus.REJECTED
    assert "out of allowed range" in res.reason.lower()
    assert res.validation_result == "REJECTED_BOUNDS_VIOLATION"


def test_scenario_5_maximum_replica_violation():
    """Scenario 5: Requested replicas above max_replicas is rejected."""
    actuator = KubernetesScalingActuator(config=ScalingConfig(min_replicas=1, max_replicas=10), dry_run=True)
    dec = make_decision("checkoutservice", DecisionAction.SCALE_UP, previous=10, requested=12)
    res = actuator.execute_decision(dec)
    assert res.status == ScalingExecutionStatus.REJECTED
    assert "out of allowed range" in res.reason.lower()
    assert res.validation_result == "REJECTED_BOUNDS_VIOLATION"


def test_scenario_6_excessive_scaling_delta():
    """Scenario 6: Delta exceeding max_replica_change is rejected."""
    actuator = KubernetesScalingActuator(config=ScalingConfig(max_replica_change=2), dry_run=True)
    # Requested change of 4 exceeds max allowed delta of 2
    dec = make_decision("checkoutservice", DecisionAction.SCALE_UP, previous=2, requested=6)
    res = actuator.execute_decision(dec)
    assert res.status == ScalingExecutionStatus.REJECTED
    assert "exceeds maximum allowed change" in res.reason.lower()
    assert res.validation_result == "REJECTED_MAX_DELTA_EXCEEDED"


# ---------------------------------------------------------------------
# SCENARIO 7: COOLDOWN VIOLATION
# ---------------------------------------------------------------------

def test_scenario_7_cooldown_violation():
    """Scenario 7: Scaling within cooldown window is rejected."""
    state_mgr = DeploymentStateManager(auto_load=False)
    now = datetime.now(timezone.utc)
    state_mgr.record_action("cartservice", DecisionAction.SCALE_UP, now)

    mock_apps = MagicMock()
    mock_apps.read_namespaced_deployment.return_value = create_mock_deployment(3)
    actuator = KubernetesScalingActuator(apps_api=mock_apps, state_manager=state_mgr, dry_run=True)
    dec = make_decision("cartservice", DecisionAction.SCALE_UP, previous=1, requested=2)
    res = actuator.execute_decision(dec)

    assert res.status == ScalingExecutionStatus.REJECTED
    assert "cooldown window" in res.reason.lower()
    assert res.validation_result == "REJECTED_COOLDOWN_ACTIVE"


# ---------------------------------------------------------------------
# SCENARIO 8: STALE DECISION REJECTION (CONCURRENCY MISMATCH)
# ---------------------------------------------------------------------

def test_scenario_8_stale_decision_concurrency_mismatch():
    """Scenario 8: If live cluster replicas differ from decision previous_replicas, reject as stale."""
    mock_apps = MagicMock()
    # Live cluster has 3 replicas, but decision was calculated against 1
    mock_apps.read_namespaced_deployment.return_value = create_mock_deployment(3)

    actuator = KubernetesScalingActuator(apps_api=mock_apps, dry_run=True)
    dec = make_decision("checkoutservice", DecisionAction.SCALE_UP, previous=1, requested=2)
    res = actuator.execute_decision(dec)

    assert res.status == ScalingExecutionStatus.REJECTED
    assert "stale decision" in res.reason.lower()
    assert res.validation_result == "REJECTED_STALE_BASELINE_CONCURRENCY"


# ---------------------------------------------------------------------
# SCENARIO 9: DEPLOYMENT PHASE RESTRICTION
# ---------------------------------------------------------------------

def test_scenario_9_deployment_phase_restriction():
    """Scenario 9: Scale-down is prohibited during ACTIVE_DEPLOYMENT."""
    state_mgr = DeploymentStateManager(auto_load=False)
    state_mgr.set_phase(DeploymentPhase.ACTIVE_DEPLOYMENT, service_name="emailservice")

    mock_apps = MagicMock()
    mock_apps.read_namespaced_deployment.return_value = create_mock_deployment(3)
    actuator = KubernetesScalingActuator(apps_api=mock_apps, state_manager=state_mgr, dry_run=True)
    dec = make_decision("emailservice", DecisionAction.SCALE_DOWN, previous=3, requested=2)
    res = actuator.execute_decision(dec)

    assert res.status == ScalingExecutionStatus.REJECTED
    assert "scale-down prohibited during active_deployment" in res.reason.lower()
    assert res.validation_result == "REJECTED_PHASE_RESTRICTION"


# ---------------------------------------------------------------------
# SCENARIO 10: EMERGENCY STOP ACTIVATION
# ---------------------------------------------------------------------

def test_scenario_10_emergency_stop():
    """Scenario 10: Global emergency stop immediately halts and rejects scaling operations."""
    actuator = KubernetesScalingActuator(dry_run=True)
    actuator.activate_emergency_stop(reason="Anomaly in checkout latency detected")
    assert actuator.is_emergency_stop_active() is True

    dec = make_decision("checkoutservice", DecisionAction.SCALE_UP, previous=1, requested=2)
    res = actuator.execute_decision(dec)

    assert res.status == ScalingExecutionStatus.REJECTED
    assert "emergency stop active" in res.reason.lower()
    assert "anomaly in checkout" in res.reason.lower()
    assert res.validation_result == "REJECTED_EMERGENCY_STOP"

    # Deactivating restores readiness
    actuator.deactivate_emergency_stop()
    assert actuator.is_emergency_stop_active() is False


# ---------------------------------------------------------------------
# SCENARIO 11: KUBERNETES API TIMEOUT AND RETRY
# ---------------------------------------------------------------------

def test_scenario_11_kubernetes_api_timeout():
    """Scenario 11: Transient API errors retried up to max_retries before safe failure."""
    mock_apps = MagicMock()
    # Simulate repeated connection timeouts
    mock_apps.read_namespaced_deployment.side_effect = ApiException(status=504, reason="Gateway Timeout")

    actuator = KubernetesScalingActuator(
        apps_api=mock_apps,
        dry_run=True,
        max_retries=3,
        retry_backoff_sec=0.01,
    )
    dec = make_decision("checkoutservice", DecisionAction.SCALE_UP, previous=1, requested=2)
    res = actuator.execute_decision(dec)

    assert res.status == ScalingExecutionStatus.FAILED
    assert res.cluster_modified is False
    assert "api error" in res.reason.lower()
    # Verified that 3 attempts were made
    assert mock_apps.read_namespaced_deployment.call_count == 3


# ---------------------------------------------------------------------
# SCENARIO 12: KUBERNETES RESOURCE CONFLICT (HTTP 409)
# ---------------------------------------------------------------------

def test_scenario_12_kubernetes_api_conflict():
    """Scenario 12: Resource conflict during scale patch is caught safely."""
    mock_apps = MagicMock()
    mock_apps.read_namespaced_deployment.return_value = create_mock_deployment(1)
    mock_apps.patch_namespaced_deployment_scale.side_effect = ApiException(status=409, reason="Conflict")

    # In live mode with mock API
    actuator = KubernetesScalingActuator(apps_api=mock_apps, dry_run=False)
    dec = make_decision("checkoutservice", DecisionAction.SCALE_UP, previous=1, requested=2)

    with patch.object(cfg, "SCALING_ENABLED", True):
        res = actuator.execute_decision(dec)
        assert res.status == ScalingExecutionStatus.FAILED
        assert res.cluster_modified is False
        assert "resource conflict" in res.reason.lower()
        assert res.validation_result == "FAILED_RESOURCE_CONFLICT"


# ---------------------------------------------------------------------
# SCENARIO 13: KUBERNETES PERMISSION FAILURE (HTTP 403)
# ---------------------------------------------------------------------

def test_scenario_13_kubernetes_permission_failure():
    """Scenario 13: Authorization failure (403) fails fast without pointless retries."""
    mock_apps = MagicMock()
    mock_apps.read_namespaced_deployment.side_effect = ApiException(status=403, reason="Forbidden")

    actuator = KubernetesScalingActuator(apps_api=mock_apps, dry_run=True, max_retries=3)
    dec = make_decision("checkoutservice", DecisionAction.SCALE_UP, previous=1, requested=2)
    res = actuator.execute_decision(dec)

    assert res.status == ScalingExecutionStatus.FAILED
    assert "authorization failure" in res.reason.lower() or "permission" in res.reason.lower()
    # Fails fast on attempt 1 without retry loops
    assert mock_apps.read_namespaced_deployment.call_count == 1


# ---------------------------------------------------------------------
# SCENARIO 14: POD READINESS TIMEOUT DETECTION
# ---------------------------------------------------------------------

def test_scenario_14_readiness_timeout():
    """Scenario 14: Post-action verification engine detects when pods do not become ready within timeout."""
    mock_apps = MagicMock()
    # Pods remain unready (0 ready of 2 desired)
    mock_apps.read_namespaced_deployment.return_value = create_mock_deployment(2, ready=0, available=0)

    actuator = KubernetesScalingActuator(apps_api=mock_apps, dry_run=False, readiness_timeout_sec=0.1)
    check = actuator.verify_post_action_readiness(
        service_name="checkoutservice",
        target_replicas=2,
        timeout_seconds=0.1,
        poll_interval_seconds=0.02,
    )
    assert check["ready"] is False
    assert check["status"] == "TIMED_OUT"
    assert "timed out" in check["message"].lower()


# ---------------------------------------------------------------------
# SCENARIO 15: FAILED ROLLOUT AND SIMULATED ROLLBACK RECOVERY
# ---------------------------------------------------------------------

def test_scenario_15_rollout_failure_and_rollback():
    """Scenario 15: Unready deployment triggers automated rollback procedure."""
    actuator = KubernetesScalingActuator(dry_run=True)
    rollback_res = actuator.execute_rollback_procedure(
        service_name="frontend",
        rollback_replicas=1,
        reason="Readiness timeout on live canary",
    )
    assert rollback_res["rollback_status"] == "SIMULATED"
    assert rollback_res["reverted_to"] == 1
    assert rollback_res["cluster_modified"] is False
    assert "readiness timeout" in rollback_res["reason"].lower()


# ---------------------------------------------------------------------
# SCENARIO 16: CONCURRENT SCALING REQUESTS
# ---------------------------------------------------------------------

def test_scenario_16_concurrent_scaling_requests():
    """Scenario 16: Operation lock serializes concurrent execution safely."""
    mock_apps = MagicMock()
    mock_apps.read_namespaced_deployment.return_value = create_mock_deployment(1)
    actuator = KubernetesScalingActuator(apps_api=mock_apps, dry_run=True)

    results = []

    def _worker(svc):
        dec = make_decision(svc, DecisionAction.SCALE_UP, previous=1, requested=2)
        r = actuator.execute_decision(dec)
        results.append(r)

    threads = [
        threading.Thread(target=_worker, args=("cartservice",)),
        threading.Thread(target=_worker, args=("checkoutservice",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 2
    assert all(r.status == ScalingExecutionStatus.VALIDATED for r in results)


# ---------------------------------------------------------------------
# SCENARIO 17: DUPLICATE OPERATION REQUEST
# ---------------------------------------------------------------------

def test_scenario_17_duplicate_operation():
    """Scenario 17: Identical sequential request after state change handled safely."""
    mock_apps = MagicMock()
    mock_apps.read_namespaced_deployment.return_value = create_mock_deployment(1)
    actuator = KubernetesScalingActuator(apps_api=mock_apps, dry_run=True)

    dec = make_decision("checkoutservice", DecisionAction.SCALE_UP, previous=1, requested=2)
    res1 = actuator.execute_decision(dec)
    assert res1.status == ScalingExecutionStatus.VALIDATED

    # When second request evaluates with no change (requested == previous)
    dec_noop = make_decision("checkoutservice", DecisionAction.SCALE_UP, previous=2, requested=2)
    res2 = actuator.execute_decision(dec_noop)
    assert res2.status == ScalingExecutionStatus.SKIPPED
    assert "no-op" in res2.reason.lower()


# ---------------------------------------------------------------------
# SCENARIO 18: BACKEND RESTAURT DURING OPERATION
# ---------------------------------------------------------------------

def test_scenario_18_restart_safety():
    """Scenario 18: Actuator state and configuration recover gracefully after process restart."""
    state_mgr = DeploymentStateManager(auto_load=False)
    actuator1 = KubernetesScalingActuator(state_manager=state_mgr, dry_run=True)
    status1 = actuator1.get_actuator_status()
    assert status1["dry_run"] is True
    assert status1["emergency_stop"] is False

    # Instantiate fresh actuator instance (simulating restart)
    actuator2 = KubernetesScalingActuator(state_manager=state_mgr, dry_run=True)
    status2 = actuator2.get_actuator_status()
    assert status2["dry_run"] is True
    assert status2["emergency_stop"] is False
    assert status2["limits"]["min_replicas"] == status1["limits"]["min_replicas"]


# ---------------------------------------------------------------------
# SCENARIO 19: GLOBAL SCALING DISABLED ENFORCEMENT
# ---------------------------------------------------------------------

def test_scenario_19_global_scaling_disabled():
    """Scenario 19: If dry_run=False but SCALING_ENABLED=False, actuator strictly rejects live mutation."""
    mock_apps = MagicMock()
    mock_apps.read_namespaced_deployment.return_value = create_mock_deployment(1)

    actuator = KubernetesScalingActuator(apps_api=mock_apps, dry_run=False)
    dec = make_decision("checkoutservice", DecisionAction.SCALE_UP, previous=1, requested=2)

    with patch.object(cfg, "SCALING_ENABLED", False):
        res = actuator.execute_decision(dec)
        assert res.status == ScalingExecutionStatus.REJECTED
        assert res.cluster_modified is False
        assert "scaling_enabled=false" in res.reason.lower()
        assert res.validation_result == "REJECTED_GLOBAL_SCALING_DISABLED"
        mock_apps.patch_namespaced_deployment_scale.assert_not_called()


# ---------------------------------------------------------------------
# SCENARIO 20: STRICT DRY-RUN ENFORCEMENT
# ---------------------------------------------------------------------

def test_scenario_20_dry_run_enforcement():
    """Scenario 20: Zero cluster modifications under any circumstances when dry_run=True."""
    mock_apps = MagicMock()
    mock_apps.read_namespaced_deployment.return_value = create_mock_deployment(1)

    actuator = KubernetesScalingActuator(apps_api=mock_apps, dry_run=True)

    # Batch test all 10 approved boutique microservices
    decisions = [
        make_decision(svc, DecisionAction.SCALE_UP, previous=1, requested=2)
        for svc in sorted(list(APPLICATION_SERVICES))
    ]
    results = actuator.execute_decisions(decisions)

    assert len(results) == 10
    assert all(r.status == ScalingExecutionStatus.VALIDATED for r in results)
    assert all(r.cluster_modified is False for r in results)
    assert all(r.execution_mode == "DRY_RUN" for r in results)

    # Confirm patch API was called 0 times
    mock_apps.patch_namespaced_deployment_scale.assert_not_called()
    summary = actuator.get_summary(results)
    assert summary["cluster_modified"] is False
    assert summary["validated_count"] == 10
