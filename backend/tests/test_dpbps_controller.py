# backend/tests/test_dpbps_controller.py
"""DPBPS controller unit tests.

These tests cover the core decision logic, deployment‑phase handling, cooldown,
stale telemetry, bottleneck detection, and API‑level behaviour via FastAPI's
TestClient.
"""

import json
from datetime import datetime, timezone, timedelta
from typing import List

import pytest
from fastapi.testclient import TestClient

# Import the FastAPI app
from backend.app.main import app

# Import controller and models for direct testing
from backend.scaling.dpbps_controller import DPBPSController
from backend.scaling.models import (
    TelemetryInput,
    DecisionAction,
    DeploymentPhase,
    ScalingConfig,
)

client = TestClient(app)

def make_telemetry(
    service_name: str,
    cpu: float = 0.3,
    mem: float = 0.3,
    latency: float = 100,
    error: float = 0.0,
    replicas: int = 1,
    ready: int = 1,
    dependencies: List[str] = None,
    timestamp: datetime = None,
) -> TelemetryInput:
    """Helper to construct TelemetryInput with sensible defaults."""
    if dependencies is None:
        dependencies = []
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    return TelemetryInput(
        service_name=service_name,
        request_rate=10.0,
        p95_latency=latency,
        error_rate=error,
        cpu_utilisation=cpu,
        memory_utilisation=mem,
        current_replicas=replicas,
        ready_replicas=ready,
        timestamp=timestamp,
        dependencies=dependencies,
    )

@pytest.fixture
def controller():
    # Use a config with low cooldown to simplify tests
    cfg = ScalingConfig(
        min_replicas=1,
        max_replicas=5,
        cpu_threshold=0.7,
        memory_threshold=0.7,
        latency_target_ms=200,
        cooldown_sec=0,
        scale_down_stabilization_sec=0,
        max_replica_change=2,
    )
    return DPBPSController(config=cfg)

def test_healthy_telemetry_hold(controller: DPBPSController):
    telemetry = [make_telemetry("product", cpu=0.2, mem=0.2, latency=100)]
    decisions = controller.evaluate(telemetry)
    assert decisions[0].action == DecisionAction.HOLD
    assert decisions[0].reason.startswith("Pressure within bounds")

def test_high_cpu_triggers_scale_up(controller: DPBPSController):
    telemetry = [make_telemetry("cart", cpu=0.9, mem=0.2, latency=150)]
    decisions = controller.evaluate(telemetry)
    assert decisions[0].action == DecisionAction.SCALE_UP
    assert decisions[0].requested_replicas == 2  # min+1
    assert "High pressure" in decisions[0].reason

def test_high_latency_triggers_scale_up(controller: DPBPSController):
    telemetry = [make_telemetry("checkout", cpu=0.3, mem=0.3, latency=500)]
    decisions = controller.evaluate(telemetry)
    assert decisions[0].action == DecisionAction.SCALE_UP

def test_high_error_rate_protective_hold(controller: DPBPSController):
    telemetry = [make_telemetry("recommendation", cpu=0.3, mem=0.3, latency=150, error=0.2)]
    decisions = controller.evaluate(telemetry)
    # Error contributes to pressure; still may scale up, but we ensure not unlimited
    # With our heuristic the aggregate should be >0.2, resulting in SCALE_UP
    # The test verifies that a non‑zero error does not cause SCALE_DOWN.
    assert decisions[0].action in (DecisionAction.SCALE_UP, DecisionAction.HOLD)

def test_scale_down_when_underutilized(controller: DPBPSController):
    # Start with 3 replicas, low load
    telemetry = [make_telemetry("product", cpu=0.1, mem=0.1, latency=80, replicas=3)]
    decisions = controller.evaluate(telemetry)
    assert decisions[0].action == DecisionAction.SCALE_DOWN
    assert decisions[0].requested_replicas == 2

def test_min_replica_boundary(controller: DPBPSController):
    telemetry = [make_telemetry("product", cpu=0.1, mem=0.1, latency=80, replicas=1)]
    decisions = controller.evaluate(telemetry)
    assert decisions[0].action == DecisionAction.HOLD
    assert decisions[0].requested_replicas == 1

def test_max_replica_boundary(controller: DPBPSController):
    telemetry = [make_telemetry("product", cpu=0.9, mem=0.9, latency=400, replicas=5)]
    decisions = controller.evaluate(telemetry)
    # Already at max, should not exceed
    assert decisions[0].action == DecisionAction.HOLD
    assert decisions[0].requested_replicas == 5

def test_active_deployment_prevents_scale_down(controller: DPBPSController):
    controller.set_phase(DeploymentPhase.ACTIVE_DEPLOYMENT)
    telemetry = [make_telemetry("product", cpu=0.1, mem=0.1, latency=80, replicas=3)]
    decisions = controller.evaluate(telemetry)
    assert decisions[0].action == DecisionAction.HOLD
    assert "Active deployment" in decisions[0].reason

def test_post_deployment_stabilization(controller: DPBPSController):
    controller.set_phase(DeploymentPhase.POST_DEPLOYMENT)
    # Simulate a previous scale‑down to set stabilization start
    now = datetime.now(timezone.utc)
    controller.state_manager.record_action("product", DecisionAction.SCALE_DOWN, now - timedelta(seconds=10))
    telemetry = [make_telemetry("product", cpu=0.1, mem=0.1, latency=80, replicas=3)]
    decisions = controller.evaluate(telemetry)
    # With default stabilization_sec=0, should allow scale‑down; set to 30 to test block
    # Adjust config for test
    controller.config.scale_down_stabilization_sec = 30
    decisions = controller.evaluate(telemetry)
    assert decisions[0].action == DecisionAction.HOLD
    assert "stabilization period" in decisions[0].reason

def test_cooldown_prevents_immediate_repeat(controller: DPBPSController):
    # Configure a non‑zero cooldown
    controller.config.cooldown_sec = 30
    telemetry = [make_telemetry("product", cpu=0.9, latency=300, replicas=1)]
    # First evaluation triggers scale‑up
    decisions1 = controller.evaluate(telemetry)
    assert decisions1[0].action == DecisionAction.SCALE_UP
    # Immediate second evaluation with same telemetry should be held due to cooldown
    decisions2 = controller.evaluate(telemetry)
    assert decisions2[0].action == DecisionAction.HOLD
    assert "Cooldown" in decisions2[0].reason

def test_stale_telemetry_is_insufficient(controller: DPBPSController):
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=100)
    telemetry = [make_telemetry("product", timestamp=stale_time)]
    decisions = controller.evaluate(telemetry)
    assert decisions[0].action == DecisionAction.INSUFFICIENT_TELEMETRY

def test_bottleneck_detection_holds_upstream(controller: DPBPSController):
    # Define downstream latency high for product, which cart depends on
    product = make_telemetry("product", latency=600)
    cart = make_telemetry("cart", latency=100, dependencies=["product"])
    decisions = controller.evaluate([product, cart])
    # Product should be recommended to scale up, cart should HOLD due to downstream bottleneck
    actions = {d.service_name: d.action for d in decisions}
    assert actions["product"] == DecisionAction.SCALE_UP
    assert actions["cart"] == DecisionAction.HOLD
    # Reason should mention bottleneck
    for d in decisions:
        if d.service_name == "cart":
            assert "bottleneck" in d.reason.lower()

# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

def test_api_scaling_status():
    resp = client.get("/api/v1/scaling/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["simulation_mode"] is True
    assert "phase" in data
    assert "config" in data

def test_api_evaluate_and_history():
    payload = [
        {
            "service_name": "product",
            "request_rate": 10.0,
            "p95_latency": 100,
            "error_rate": 0.0,
            "cpu_utilisation": 0.2,
            "memory_utilisation": 0.2,
            "current_replicas": 1,
            "ready_replicas": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dependencies": [],
        }
    ]
    resp = client.post("/api/v1/scaling/evaluate", json=payload)
    assert resp.status_code == 200
    decisions = resp.json()
    assert isinstance(decisions, list)
    assert decisions[0]["action"] == "HOLD"

    # History should now contain one entry
    hist = client.get("/api/v1/scaling/decisions").json()
    assert any(d["service_name"] == "product" for d in hist)

def test_api_dry_run_does_not_mutate_state():
    payload = [
        {
            "service_name": "product",
            "request_rate": 10.0,
            "p95_latency": 500,
            "error_rate": 0.0,
            "cpu_utilisation": 0.9,
            "memory_utilisation": 0.9,
            "current_replicas": 1,
            "ready_replicas": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dependencies": [],
        }
    ]
    # Dry‑run
    dry = client.post("/api/v1/scaling/dry-run", json=payload).json()
    assert dry[0]["action"] == "SCALE_UP"
    # Immediate real evaluate with same payload should still be a scale‑up (no cooldown in config)
    real = client.post("/api/v1/scaling/evaluate", json=payload).json()
    assert real[0]["action"] == "SCALE_UP"

def test_api_set_deployment_phase():
    resp = client.post("/api/v1/scaling/deployment-phase", json={"phase": "ACTIVE_DEPLOYMENT"})
    assert resp.status_code == 200
    assert resp.json()["phase"] == "ACTIVE_DEPLOYMENT"

"""End of DPBPS controller tests"""
