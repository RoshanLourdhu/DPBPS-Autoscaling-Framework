"""
backend/tests/test_cicd_deployment_awareness.py
Comprehensive test suite for Stage 13: CI/CD Deployment Awareness.

Validates all 13 required scenarios:
1. Normal operation phase
2. Deployment started via CI/CD event
3. Deployment in progress (reconciliation)
4. Deployment successfully completed (transition to POST_DEPLOYMENT)
5. Deployment failed event
6. Deployment cancelled event
7. Duplicate webhook event deduplication
8. Invalid webhook HMAC SHA-256 signature rejection
9. Out-of-order / stale webhook event rejection
10. Kubernetes rollout failure (ProgressDeadlineExceeded)
11. Backend restart persistence recovery
12. Kubernetes API watch / query recovery
13. Deployment phase modulation of DPBPS scaling decisions
"""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.scaling.deployment_state import DeploymentStateManager
from backend.scaling.dpbps_controller import DPBPSController
from backend.scaling.models import (
    DecisionAction,
    DeploymentPhase,
    ScalingConfig,
    TelemetryInput,
)

SECRET = "dpbps-cicd-secret-token"


def make_signature(body: bytes, secret: str = SECRET) -> str:
    sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def make_telemetry(service_name="checkoutservice", cpu=0.01, memory=0.05, replicas=4):
    now = datetime.now(timezone.utc)
    return TelemetryInput(
        service_name=service_name,
        request_rate=10.0,
        p95_latency=30.0,
        error_rate=0.0,
        cpu_utilisation=cpu,
        memory_utilisation=memory,
        current_replicas=replicas,
        ready_replicas=replicas,
        timestamp=now,
        dependencies=[],
    )


# ---------------------------------------------------------------------
# SCENARIO 1: NORMAL OPERATION
# ---------------------------------------------------------------------

def test_scenario_1_normal_operation():
    """Scenario 1: Default service state is NORMAL_OPERATION."""
    mgr = DeploymentStateManager(auto_load=False)
    assert mgr.get_phase() == DeploymentPhase.NORMAL_OPERATION
    assert mgr.get_phase("checkoutservice") == DeploymentPhase.NORMAL_OPERATION
    assert mgr.get_all_service_phases() == {}


# ---------------------------------------------------------------------
# SCENARIO 2: DEPLOYMENT STARTED VIA CI/CD EVENT
# ---------------------------------------------------------------------

def test_scenario_2_deployment_started():
    """Scenario 2: CI/CD 'started' event transitions service to ACTIVE_DEPLOYMENT."""
    mgr = DeploymentStateManager(auto_load=False)
    now_iso = datetime.now(timezone.utc).isoformat()
    event = {
        "event_id": "evt-start-001",
        "service_name": "checkoutservice",
        "event_type": "started",
        "timestamp": now_iso,
        "commit_sha": "abc1234",
    }
    success, msg, rec = mgr.record_cicd_event(event)
    assert success is True
    assert mgr.get_phase("checkoutservice") == DeploymentPhase.ACTIVE_DEPLOYMENT
    # Global phase and other services remain NORMAL_OPERATION
    assert mgr.get_phase("frontend") == DeploymentPhase.NORMAL_OPERATION
    assert rec["new_phase"] == "ACTIVE_DEPLOYMENT"


# ---------------------------------------------------------------------
# SCENARIO 3: DEPLOYMENT IN PROGRESS
# ---------------------------------------------------------------------

def test_scenario_3_deployment_in_progress():
    """Scenario 3: Rollout progressing condition maintains ACTIVE_DEPLOYMENT."""
    mgr = DeploymentStateManager(auto_load=False)
    rollout_info = {
        "generation": 3,
        "observed_generation": 2,  # mismatch indicates rollout in progress
        "desired_replicas": 2,
        "updated_replicas": 1,
        "available_replicas": 1,
        "ready_replicas": 1,
        "conditions": [{"type": "Progressing", "status": "True", "reason": "ReplicaSetUpdated"}],
    }
    res = mgr.reconcile_kubernetes_rollout("cartservice", rollout_info)
    assert res["reconciled_phase"] == "ACTIVE_DEPLOYMENT"
    assert mgr.get_phase("cartservice") == DeploymentPhase.ACTIVE_DEPLOYMENT


# ---------------------------------------------------------------------
# SCENARIO 4: DEPLOYMENT SUCCESSFULLY COMPLETED
# ---------------------------------------------------------------------

def test_scenario_4_deployment_completed():
    """Scenario 4: Rollout completion transitions service to POST_DEPLOYMENT."""
    mgr = DeploymentStateManager(auto_load=False)
    mgr.set_phase(DeploymentPhase.ACTIVE_DEPLOYMENT, service_name="paymentservice")

    complete_rollout = {
        "generation": 2,
        "observed_generation": 2,
        "desired_replicas": 2,
        "updated_replicas": 2,
        "available_replicas": 2,
        "ready_replicas": 2,
        "conditions": [{"type": "Progressing", "status": "True", "reason": "NewReplicaSetAvailable"}],
    }
    res = mgr.reconcile_kubernetes_rollout("paymentservice", complete_rollout)
    assert res["reconciled_phase"] == "POST_DEPLOYMENT"
    assert mgr.get_phase("paymentservice") == DeploymentPhase.POST_DEPLOYMENT


# ---------------------------------------------------------------------
# SCENARIO 5: DEPLOYMENT FAILED
# ---------------------------------------------------------------------

def test_scenario_5_deployment_failed():
    """Scenario 5: CI/CD 'failed' event reverts phase to NORMAL_OPERATION."""
    mgr = DeploymentStateManager(auto_load=False)
    mgr.set_phase(DeploymentPhase.ACTIVE_DEPLOYMENT, service_name="shippingservice")

    event = {
        "event_id": "evt-fail-001",
        "service_name": "shippingservice",
        "event_type": "failed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    success, msg, rec = mgr.record_cicd_event(event)
    assert success is True
    assert mgr.get_phase("shippingservice") == DeploymentPhase.NORMAL_OPERATION
    assert rec["previous_phase"] == "ACTIVE_DEPLOYMENT"
    assert rec["new_phase"] == "NORMAL_OPERATION"


# ---------------------------------------------------------------------
# SCENARIO 6: DEPLOYMENT CANCELLED
# ---------------------------------------------------------------------

def test_scenario_6_deployment_cancelled():
    """Scenario 6: CI/CD 'cancelled' event safely resets phase to NORMAL_OPERATION."""
    mgr = DeploymentStateManager(auto_load=False)
    mgr.set_phase(DeploymentPhase.ACTIVE_DEPLOYMENT, service_name="currencyservice")

    event = {
        "event_id": "evt-cancel-001",
        "service_name": "currencyservice",
        "event_type": "cancelled",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    success, msg, rec = mgr.record_cicd_event(event)
    assert success is True
    assert mgr.get_phase("currencyservice") == DeploymentPhase.NORMAL_OPERATION


# ---------------------------------------------------------------------
# SCENARIO 7: DUPLICATE WEBHOOK EVENT DEDUPLICATION
# ---------------------------------------------------------------------

def test_scenario_7_duplicate_webhook_event():
    """Scenario 7: Duplicate event_id is safely ignored without repeating state changes."""
    mgr = DeploymentStateManager(auto_load=False)
    event = {
        "event_id": "evt-unique-dup",
        "service_name": "emailservice",
        "event_type": "started",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    # First ingestion succeeds
    ok1, msg1, _ = mgr.record_cicd_event(event)
    assert ok1 is True

    # Second ingestion with same event_id is rejected as duplicate
    ok2, msg2, details = mgr.record_cicd_event(event)
    assert ok2 is False
    assert "duplicate" in msg2.lower()
    assert details.get("event_id") == "evt-unique-dup"


# ---------------------------------------------------------------------
# SCENARIO 8: INVALID WEBHOOK SIGNATURE
# ---------------------------------------------------------------------

def test_scenario_8_invalid_webhook_signature():
    """Scenario 8: Invalid HMAC SHA-256 signature is rejected with HTTP 401."""
    client = TestClient(app)
    payload = {
        "event_id": "evt-sig-test",
        "service_name": "checkoutservice",
        "event_type": "started",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    body = json.dumps(payload).encode("utf-8")
    invalid_sig = "sha256=0000000000000000000000000000000000000000000000000000000000000000"

    resp = client.post(
        "/api/v1/cicd/events",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": invalid_sig},
    )
    assert resp.status_code == 401
    assert "signature" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------
# SCENARIO 9: OUT-OF-ORDER WEBHOOK EVENTS
# ---------------------------------------------------------------------

def test_scenario_9_out_of_order_events():
    """Scenario 9: Events arriving with older timestamps than latest processed are rejected."""
    mgr = DeploymentStateManager(auto_load=False)
    t_now = datetime.now(timezone.utc)
    t_old = t_now - timedelta(minutes=10)

    # Ingest newer event first
    mgr.record_cicd_event({
        "event_id": "evt-order-2",
        "service_name": "adservice",
        "event_type": "started",
        "timestamp": t_now.isoformat(),
    })

    # Attempt to ingest older event for same service
    ok, msg, _ = mgr.record_cicd_event({
        "event_id": "evt-order-1",
        "service_name": "adservice",
        "event_type": "started",
        "timestamp": t_old.isoformat(),
    })
    assert ok is False
    assert "out-of-order" in msg.lower()


# ---------------------------------------------------------------------
# SCENARIO 10: KUBERNETES ROLLOUT FAILURE
# ---------------------------------------------------------------------

def test_scenario_10_rollout_failure_reconciliation():
    """Scenario 10: Rollout deadline exceeded condition triggers failure recovery."""
    mgr = DeploymentStateManager(auto_load=False)
    mgr.set_phase(DeploymentPhase.ACTIVE_DEPLOYMENT, service_name="recommendationservice")

    failure_rollout = {
        "generation": 3,
        "observed_generation": 3,
        "desired_replicas": 2,
        "updated_replicas": 1,
        "available_replicas": 1,
        "ready_replicas": 1,
        "conditions": [
            {
                "type": "Progressing",
                "status": "False",
                "reason": "ProgressDeadlineExceeded",
                "message": "ReplicaSet did not finish progress in 600s",
            }
        ],
    }
    res = mgr.reconcile_kubernetes_rollout("recommendationservice", failure_rollout)
    assert res["rollout_failed"] is True
    assert res["action"] == "FAILED_ROLLOUT_RESET"
    assert mgr.get_phase("recommendationservice") == DeploymentPhase.NORMAL_OPERATION


# ---------------------------------------------------------------------
# SCENARIO 11: BACKEND RESTAURT PERSISTENCE RECOVERY
# ---------------------------------------------------------------------

def test_scenario_11_persistence_across_restarts():
    """Scenario 11: Deployment state and events survive backend restart."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = os.path.join(tmpdir, "deployment_state.json")

        mgr1 = DeploymentStateManager(persistence_file=state_file, auto_load=False)
        mgr1.set_phase(DeploymentPhase.ACTIVE_DEPLOYMENT, service_name="checkoutservice")
        mgr1.set_phase(DeploymentPhase.POST_DEPLOYMENT, service_name="frontend")

        mgr1.record_cicd_event({
            "event_id": "evt-persist-1",
            "service_name": "checkoutservice",
            "event_type": "started",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        assert os.path.exists(state_file)

        # Simulate backend restart with a new DeploymentStateManager instance
        mgr2 = DeploymentStateManager(persistence_file=state_file, auto_load=True)
        assert mgr2.get_phase("checkoutservice") == DeploymentPhase.ACTIVE_DEPLOYMENT
        assert mgr2.get_phase("frontend") == DeploymentPhase.POST_DEPLOYMENT
        assert mgr2.get_phase("cartservice") == DeploymentPhase.NORMAL_OPERATION
        assert "evt-persist-1" in mgr2.processed_event_ids
        assert len(mgr2.cicd_events) == 1


# ---------------------------------------------------------------------
# SCENARIO 12: KUBERNETES WATCH / QUERY RECOVERY
# ---------------------------------------------------------------------

def test_scenario_12_kubernetes_query_recovery():
    """Scenario 12: Transient query error in rollout reconciliation handled safely without crash."""
    client = TestClient(app)
    with patch("backend.app.api.v1_router.get_apps_v1_api") as mock_get_api:
        mock_api = MagicMock()
        mock_api.read_namespaced_deployment.side_effect = Exception("Connection reset by peer")
        mock_get_api.return_value = mock_api

        resp = client.post("/api/v1/deployments/reconcile", json={"service_name": "checkoutservice"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["action"] == "ERROR"
        assert "Connection reset" in data[0]["error"]


# ---------------------------------------------------------------------
# SCENARIO 13: DEPLOYMENT PHASE INFLUENCING DPBPS SCALING
# ---------------------------------------------------------------------

def test_scenario_13_dpbps_phase_influence():
    """Scenario 13: Scale-down is suppressed under ACTIVE_DEPLOYMENT and postponed in POST_DEPLOYMENT."""
    state_mgr = DeploymentStateManager(auto_load=False)
    ctrl = DPBPSController()
    ctrl.state_manager = state_mgr

    # Under-utilized service (cpu 0.01, mem 0.05, 4 replicas)
    t = make_telemetry("checkoutservice", replicas=4)

    # 1. NORMAL_OPERATION: allowed to scale down
    state_mgr.set_phase(DeploymentPhase.NORMAL_OPERATION, service_name="checkoutservice")
    dec_normal = ctrl.evaluate([t])[0]
    assert dec_normal.action == DecisionAction.SCALE_DOWN
    assert dec_normal.requested_replicas == 3

    # Reset cooldown so phase restriction is tested in isolation
    state_mgr.last_action_time.clear()

    # 2. ACTIVE_DEPLOYMENT: scale-down is strictly suppressed to HOLD
    state_mgr.set_phase(DeploymentPhase.ACTIVE_DEPLOYMENT, service_name="checkoutservice")
    dec_active = ctrl.evaluate([t])[0]
    assert dec_active.action == DecisionAction.HOLD
    assert dec_active.requested_replicas == 4
    assert "active deployment" in dec_active.reason.lower()

    # Reset cooldown
    state_mgr.last_action_time.clear()

    # 3. PRE_DEPLOYMENT: scale-down is also suppressed
    state_mgr.set_phase(DeploymentPhase.PRE_DEPLOYMENT, service_name="checkoutservice")
    dec_pre = ctrl.evaluate([t])[0]
    assert dec_pre.action == DecisionAction.HOLD
    assert dec_pre.requested_replicas == 4
    assert "pre-deployment" in dec_pre.reason.lower()

    # Reset cooldown
    state_mgr.last_action_time.clear()

    # 4. POST_DEPLOYMENT: scale-down postponed during stabilization window
    state_mgr.set_phase(DeploymentPhase.POST_DEPLOYMENT, service_name="checkoutservice")
    dec_post = ctrl.evaluate([t])[0]
    assert dec_post.action == DecisionAction.HOLD
    assert dec_post.requested_replicas == 4
    assert "stabilization period not elapsed" in dec_post.reason.lower()
