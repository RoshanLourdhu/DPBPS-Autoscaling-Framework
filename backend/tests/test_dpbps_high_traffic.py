"""
Synthetic DPBPS High-Traffic Decision and Algorithm Stress Tests.

NOTE: All tests in this module use SYNTHETIC / MOCKED telemetry models to validate
the mathematical and logical correctness of the DPBPS controller and bottleneck
detector under high load, spike, and sustained traffic patterns.
These do NOT represent real cluster measurements.

Validates:
1. E03 SUDDEN_TRAFFIC_SPIKE handling and cooldown enforcement.
2. E04 SUSTAINED_HIGH_TRAFFIC incremental scale-up and max_replicas ceiling clamping.
3. Downstream bottleneck detection and upstream protective HOLD isolation.
4. Temporary traffic spike recovery vs sustained load stability.
5. Missing and stale telemetry handling (INSUFFICIENT_TELEMETRY).
6. Deployment-phase safety: scale-down suppression during ACTIVE_DEPLOYMENT and POST_DEPLOYMENT.
"""

from datetime import datetime, timezone, timedelta
from typing import List, Optional
import pytest

from backend.scaling.dpbps_controller import DPBPSController
from backend.scaling.bottleneck_detector import detect_bottleneck
from backend.scaling.models import (
    TelemetryInput,
    DecisionAction,
    DeploymentPhase,
    ScalingConfig,
)


def make_synthetic_telemetry(
    service_name: str,
    cpu: float = 0.20,
    mem: float = 0.20,
    latency: float = 50.0,
    error: float = 0.0,
    replicas: int = 1,
    ready: int = 1,
    dependencies: Optional[List[str]] = None,
    timestamp: Optional[datetime] = None,
    request_rate: float = 10.0,
) -> TelemetryInput:
    """Construct synthetic TelemetryInput for controlled pressure testing."""
    return TelemetryInput(
        service_name=service_name,
        request_rate=request_rate,
        p95_latency=latency,
        error_rate=error,
        cpu_utilisation=cpu,
        memory_utilisation=mem,
        current_replicas=replicas,
        ready_replicas=ready,
        timestamp=timestamp or datetime.now(timezone.utc),
        dependencies=dependencies or [],
    )


@pytest.fixture
def high_traffic_controller() -> DPBPSController:
    """Provide a DPBPSController with production-grade scaling bounds."""
    config = ScalingConfig(
        min_replicas=1,
        max_replicas=5,
        cpu_threshold=0.80,
        memory_threshold=0.80,
        latency_target_ms=200.0,
        cooldown_sec=30,
        scale_down_stabilization_sec=60,
        max_replica_change=2,
        weight_cpu=0.35,
        weight_memory=0.15,
        weight_latency=0.35,
        weight_error=0.15,
    )
    return DPBPSController(config=config)


# ---------------------------------------------------------------------
# 1. E03 SUDDEN_TRAFFIC_SPIKE SYNTHETIC VALIDATION
# ---------------------------------------------------------------------

def test_synthetic_e03_sudden_traffic_spike_behavior(high_traffic_controller: DPBPSController):
    """
    Simulates E03: Sudden traffic spike (5 -> 80 users).
    
    Verifies:
    - Idle baseline produces HOLD.
    - Sudden spike produces SCALE_UP with delta within max_replica_change bound.
    - Subsequent evaluation within cooldown window enforces HOLD to prevent thrashing.
    """
    # 1. Baseline idle evaluation
    idle_telemetry = [
        make_synthetic_telemetry("frontend", cpu=0.15, latency=35.0, replicas=1),
    ]
    decisions = high_traffic_controller.evaluate(idle_telemetry)
    assert decisions[0].action == DecisionAction.HOLD
    assert decisions[0].requested_replicas == 1

    # 2. Sudden spike: CPU jumps to 90%, P95 latency jumps to 320ms (> 200ms target)
    spike_telemetry = [
        make_synthetic_telemetry(
            "frontend",
            cpu=0.90,
            mem=0.60,
            latency=320.0,
            request_rate=120.0,
            replicas=1,
        ),
    ]
    spike_decisions = high_traffic_controller.evaluate(spike_telemetry)
    assert spike_decisions[0].action == DecisionAction.SCALE_UP
    assert spike_decisions[0].requested_replicas == 2
    assert "High pressure" in spike_decisions[0].reason

    # 3. Next tick immediately after: high pressure remains, but cooldown (30s) must hold
    tick_telemetry = [
        make_synthetic_telemetry(
            "frontend",
            cpu=0.92,
            mem=0.62,
            latency=340.0,
            request_rate=125.0,
            replicas=2,
        ),
    ]
    tick_decisions = high_traffic_controller.evaluate(tick_telemetry)
    assert tick_decisions[0].action == DecisionAction.HOLD
    assert "Cooldown period active" in tick_decisions[0].reason
    assert tick_decisions[0].requested_replicas == 2


# ---------------------------------------------------------------------
# 2. E04 SUSTAINED_HIGH_TRAFFIC SYNTHETIC VALIDATION
# ---------------------------------------------------------------------

def test_synthetic_e04_sustained_high_traffic_incremental_scale(high_traffic_controller: DPBPSController):
    """
    Simulates E04: Sustained high traffic plateau (60 users).
    
    Verifies:
    - Incremental scaling up as each cooldown window elapses under sustained pressure.
    - Clamping at max_replicas (ceiling = 5) without overshoot.
    """
    current_replicas = 1

    for step in range(1, 6):
        telemetry = [
            make_synthetic_telemetry(
                "cartservice",
                cpu=0.95,
                mem=0.85,
                latency=280.0,
                request_rate=90.0,
                replicas=current_replicas,
            ),
        ]
        decisions = high_traffic_controller.evaluate(telemetry)
        decision = decisions[0]

        if current_replicas < high_traffic_controller.config.max_replicas:
            assert decision.action == DecisionAction.SCALE_UP
            assert decision.requested_replicas == current_replicas + 1
            current_replicas = decision.requested_replicas
        else:
            # Reached max_replicas ceiling: must clamp to max_replicas and HOLD
            assert decision.requested_replicas == 5
            assert decision.action == DecisionAction.HOLD

        # Simulate cooldown elapse by moving last_action_time into the past
        if "cartservice" in high_traffic_controller.state_manager.last_action_time:
            high_traffic_controller.state_manager.last_action_time["cartservice"] -= timedelta(seconds=35)

    assert current_replicas == 5


# ---------------------------------------------------------------------
# 3. BOTTLENECK DETECTION & UPSTREAM PROTECTIVE ISOLATION
# ---------------------------------------------------------------------

def test_synthetic_downstream_bottleneck_isolation(high_traffic_controller: DPBPSController):
    """
    Verifies DPBPS bottleneck detection and upstream service isolation.
    
    Scenario:
    - cartservice suffers severe latency (700ms > 500ms threshold).
    - frontend and checkoutservice depend on cartservice.
    - cartservice must be detected as the root bottleneck.
    - cartservice is allowed to scale up.
    - frontend and checkoutservice must be placed on protective HOLD with downstream reason.
    """
    telemetry = [
        make_synthetic_telemetry(
            "frontend",
            cpu=0.85,
            latency=350.0,
            replicas=2,
            dependencies=["cartservice", "checkoutservice"],
        ),
        make_synthetic_telemetry(
            "checkoutservice",
            cpu=0.82,
            latency=400.0,
            replicas=1,
            dependencies=["cartservice"],
        ),
        make_synthetic_telemetry(
            "cartservice",
            cpu=0.95,
            latency=700.0,  # Severe bottleneck (> 500ms)
            error=0.08,
            replicas=1,
            dependencies=[],
        ),
    ]

    # Verify detector directly
    bottleneck = detect_bottleneck(telemetry)
    assert bottleneck == "cartservice"

    # Evaluate via controller
    decisions = {d.service_name: d for d in high_traffic_controller.evaluate(telemetry)}

    # cartservice should scale up to address the bottleneck
    assert decisions["cartservice"].action == DecisionAction.SCALE_UP
    assert decisions["cartservice"].bottleneck == "cartservice"

    # Upstream services must be held to avoid exacerbating downstream queueing
    assert decisions["frontend"].action == DecisionAction.HOLD
    assert "Downstream bottleneck detected on 'cartservice'" in decisions["frontend"].reason
    assert decisions["frontend"].bottleneck == "cartservice"

    assert decisions["checkoutservice"].action == DecisionAction.HOLD
    assert "Downstream bottleneck detected on 'cartservice'" in decisions["checkoutservice"].reason
    assert decisions["checkoutservice"].bottleneck == "cartservice"


# ---------------------------------------------------------------------
# 4. TEMPORARY SPIKE RECOVERY VS SUSTAINED STABILITY
# ---------------------------------------------------------------------

def test_synthetic_temporary_spike_recovery(high_traffic_controller: DPBPSController):
    """
    Verifies that a transient spike scales up once, and upon load cessation,
    the controller stabilizes without rapid oscillation.
    """
    # 1. Spike at t0 -> Scale Up from 1 to 2
    spike_tel = [make_synthetic_telemetry("emailservice", cpu=0.95, latency=300.0, replicas=1)]
    d1 = high_traffic_controller.evaluate(spike_tel)
    assert d1[0].action == DecisionAction.SCALE_UP
    assert d1[0].requested_replicas == 2

    # 2. Traffic subsides immediately -> Low pressure, but within cooldown -> HOLD
    subside_tel = [make_synthetic_telemetry("emailservice", cpu=0.10, latency=20.0, replicas=2)]
    d2 = high_traffic_controller.evaluate(subside_tel)
    assert d2[0].action == DecisionAction.HOLD
    assert "Cooldown period active" in d2[0].reason

    # 3. Simulate cooldown elapsed (30s) -> Low pressure, scale down is considered
    high_traffic_controller.state_manager.last_action_time["emailservice"] -= timedelta(seconds=35)
    idle_tel = [make_synthetic_telemetry("emailservice", cpu=0.10, latency=20.0, replicas=2)]
    d3 = high_traffic_controller.evaluate(idle_tel)
    assert d3[0].action == DecisionAction.SCALE_DOWN
    assert d3[0].requested_replicas == 1


# ---------------------------------------------------------------------
# 5. UNHEALTHY AND STALE TELEMETRY HANDLING
# ---------------------------------------------------------------------

def test_synthetic_stale_telemetry_isolation(high_traffic_controller: DPBPSController):
    """
    Verifies that stale or missing telemetry triggers INSUFFICIENT_TELEMETRY
    and never modifies replicas.
    """
    stale_timestamp = datetime.now(timezone.utc) - timedelta(seconds=120)  # > 30s threshold
    telemetry = [
        make_synthetic_telemetry(
            "paymentservice",
            cpu=0.99,  # High CPU would normally scale, but stale
            latency=500.0,
            replicas=2,
            timestamp=stale_timestamp,
        ),
    ]

    decisions = high_traffic_controller.evaluate(telemetry)
    assert decisions[0].action == DecisionAction.INSUFFICIENT_TELEMETRY
    assert decisions[0].requested_replicas == 2
    assert "stale or missing" in decisions[0].reason


# ---------------------------------------------------------------------
# 6. DEPLOYMENT-PHASE SAFETY ENFORCEMENT UNDER PRESSURE
# ---------------------------------------------------------------------

def test_synthetic_active_deployment_suppresses_scale_down(high_traffic_controller: DPBPSController):
    """
    Verifies that during ACTIVE_DEPLOYMENT, scale-down is strictly suppressed
    even if traffic is completely absent.
    """
    high_traffic_controller.set_phase(DeploymentPhase.ACTIVE_DEPLOYMENT)

    telemetry = [
        make_synthetic_telemetry("shippingservice", cpu=0.02, latency=10.0, replicas=3),
    ]

    decisions = high_traffic_controller.evaluate(telemetry)
    assert decisions[0].action == DecisionAction.HOLD
    assert decisions[0].requested_replicas == 3
    assert "Active deployment – scale‑down suppressed" in decisions[0].reason


def test_synthetic_post_deployment_stabilization_enforced(high_traffic_controller: DPBPSController):
    """
    Verifies that during POST_DEPLOYMENT, scale-down requires the stabilization
    window (60s) to fully elapse before reducing replicas.
    """
    high_traffic_controller.set_phase(DeploymentPhase.POST_DEPLOYMENT)
    now = datetime.now(timezone.utc)

    # Set last action to 35s ago (so 30s cooldown has passed, but 60s stabilization has NOT)
    high_traffic_controller.state_manager.last_action_time["currencyservice"] = now - timedelta(seconds=35)
    high_traffic_controller.state_manager.scale_down_stabilization_start["currencyservice"] = now - timedelta(seconds=35)

    # First check: cooldown passes, but within 60s stabilization window -> HOLD
    telemetry_1 = [
        make_synthetic_telemetry("currencyservice", cpu=0.05, latency=15.0, replicas=3),
    ]
    d1 = high_traffic_controller.evaluate(telemetry_1)
    assert d1[0].action == DecisionAction.HOLD
    assert "stabilization period not elapsed" in d1[0].reason

    # Second check after simulating stabilization window (60s) elapsed (e.g. 70s ago) -> SCALE_DOWN
    high_traffic_controller.state_manager.scale_down_stabilization_start["currencyservice"] = (
        now - timedelta(seconds=70)
    )
    high_traffic_controller.state_manager.last_action_time["currencyservice"] = (
        now - timedelta(seconds=70)
    )
    d2 = high_traffic_controller.evaluate(telemetry_1)
    assert d2[0].action == DecisionAction.SCALE_DOWN
    assert d2[0].requested_replicas == 2
    assert "stabilization satisfied" in d2[0].reason
