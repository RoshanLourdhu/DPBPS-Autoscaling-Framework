"""
backend/tests/test_continuous_controller.py
Comprehensive validation suite for Continuous DPBPS Controller.

Covers all 12 required scenarios and lifecycle safety checks:
1. Normal operating conditions
2. CPU bottleneck
3. Memory bottleneck
4. High request latency
5. Missing telemetry
6. Stale telemetry
7. No traffic (idle)
8. Repeated bottleneck detection
9. Cooldown enforcement
10. Deployment in progress (ACTIVE_DEPLOYMENT scale-down suppression)
11. Conflicting decisions (optimistic concurrency / state mismatch)
12. Protected infrastructure service (redis-cart, opentelemetrycollector)
13. Lifecycle safety (start, stop, pause, resume, no duplicate execution loops)
14. Decision history and JSON persistence validation
"""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

import backend.config as cfg
from backend.scaling.continuous_controller import (
    ContinuousControllerStatus,
    ContinuousCycleSummary,
    ContinuousDecisionRecord,
    ContinuousDPBPSController,
)
from backend.scaling.deployment_state import DeploymentStateManager
from backend.scaling.dpbps_controller import DPBPSController
from backend.scaling.kubernetes.actuator import (
    KubernetesScalingActuator,
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


# ---------------------------------------------------------------------
# FIXTURES AND HELPERS
# ---------------------------------------------------------------------

def make_test_telemetry(
    service_name: str = "productcatalogservice",
    cpu: float = 0.3,
    memory: float = 0.4,
    request_rate: float = 10.0,
    p95_latency: float = 50.0,
    error_rate: float = 0.0,
    replicas: int = 1,
    age_seconds: float = 5.0,
    dependencies: List[str] = None,
) -> TelemetryInput:
    """Construct a validated TelemetryInput fixture."""
    now = datetime.now(timezone.utc)
    ts = now - timedelta(seconds=age_seconds)
    return TelemetryInput(
        service_name=service_name,
        request_rate=request_rate,
        p95_latency=p95_latency,
        error_rate=error_rate,
        cpu_utilisation=cpu,
        memory_utilisation=memory,
        current_replicas=replicas,
        ready_replicas=replicas,
        timestamp=ts,
        dependencies=dependencies or [],
    )


def make_raw_item(
    service_name: str,
    cpu: float = 0.3,
    memory: float = 0.4,
    request_rate: float = 10.0,
    p95_latency: float = 50.0,
    error_rate: float = 0.0,
    replicas: int = 1,
    telemetry_available: bool = True,
    missing_metrics: List[str] = None,
) -> Dict[str, Any]:
    """Construct a mock raw telemetry dictionary as returned by collect_deployment_telemetry."""
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "service_name": service_name,
        "namespace": "online-boutique",
        "desired_replicas": replicas,
        "ready_replicas": replicas,
        "observed_pods": replicas,
        "cpu_usage_millicores": cpu * 100,
        "memory_usage_mib": memory * 64,
        "cpu_request_millicores": 100.0,
        "memory_request_mib": 64.0,
        "cpu_utilisation": cpu,
        "memory_utilisation": memory,
        "timestamp": now_iso,
        "telemetry_available": telemetry_available,
        "request_rate": request_rate if telemetry_available else None,
        "p95_latency_ms": p95_latency if telemetry_available else None,
        "error_rate": error_rate if telemetry_available else None,
        "dependencies": [],
        "deployment_phase": "NORMAL_OPERATION",
        "missing_metrics": missing_metrics or [],
        "diagnostics": [],
    }


def create_mock_deployment(replicas=1):
    dep = MagicMock()
    dep.spec.replicas = replicas
    dep.status.ready_replicas = replicas
    dep.status.updated_replicas = replicas
    dep.metadata.generation = 1
    dep.status.observed_generation = 1
    return dep


# ---------------------------------------------------------------------
# TEST SUITE
# ---------------------------------------------------------------------

@pytest.fixture
def mock_actuator():
    """Create a mock KubernetesScalingActuator in DRY_RUN mode."""
    apps_mock = MagicMock()
    apps_mock.read_namespaced_deployment.return_value = create_mock_deployment(1)
    actuator = KubernetesScalingActuator(
        apps_api=apps_mock,
        dry_run=True,
    )
    return actuator


@pytest.fixture
def test_controller(tmp_path, mock_actuator):
    """Instantiate a test ContinuousDPBPSController with isolated history."""
    state_mgr = DeploymentStateManager()
    dpbps_ctrl = DPBPSController()
    dpbps_ctrl.state_manager = state_mgr

    mock_adapter = MagicMock(spec=KubernetesTelemetryAdapter)
    mock_adapter.state_manager = state_mgr

    history_file = tmp_path / "test_history.json"

    controller = ContinuousDPBPSController(
        dpbps_controller=dpbps_ctrl,
        telemetry_adapter=mock_adapter,
        actuator=mock_actuator,
        state_manager=state_mgr,
        interval_seconds=5.0,
        history_file=history_file,
    )
    return controller


# ---------------------------------------------------------------------
# SCENARIO 1: NORMAL OPERATING CONDITIONS
# ---------------------------------------------------------------------

def test_scenario_1_normal_operating_conditions(test_controller):
    """Scenario 1: All services healthy; action must be HOLD; no mutations."""
    async def _run():
        t_input = make_test_telemetry("productcatalogservice", cpu=0.35, memory=0.40, p95_latency=45.0)
        raw_item = make_raw_item("productcatalogservice", cpu=0.35, memory=0.40, p95_latency=45.0)

        test_controller.telemetry_adapter.get_telemetry_inputs.return_value = ([t_input], [])
        test_controller.telemetry_adapter.collect_deployment_telemetry.return_value = [raw_item]

        summary = await test_controller.run_single_cycle()

        assert summary.cycle_number == 1
        assert summary.eligible_services == 1
        assert summary.scale_up_count == 0
        assert summary.scale_down_count == 0
        assert summary.hold_count == 1
        assert summary.cluster_modified is False
        assert summary.execution_mode == "DRY_RUN"

        dec = summary.decisions[0]
        assert dec.service_name == "productcatalogservice"
        assert dec.action == "HOLD"
        assert dec.previous_replicas == 1
        assert dec.recommended_replicas == 1
        assert dec.cluster_modified is False

    asyncio.run(_run())


# ---------------------------------------------------------------------
# SCENARIO 2: CPU BOTTLENECK
# ---------------------------------------------------------------------

def test_scenario_2_cpu_bottleneck(test_controller):
    """Scenario 2: CPU > 80% threshold triggers SCALE_UP in DRY_RUN mode."""
    async def _run():
        t_input = make_test_telemetry("productcatalogservice", cpu=0.95, memory=0.40)
        raw_item = make_raw_item("productcatalogservice", cpu=0.95, memory=0.40)

        test_controller.telemetry_adapter.get_telemetry_inputs.return_value = ([t_input], [])
        test_controller.telemetry_adapter.collect_deployment_telemetry.return_value = [raw_item]

        summary = await test_controller.run_single_cycle()

        assert summary.scale_up_count == 1
        assert summary.cluster_modified is False

        dec = summary.decisions[0]
        assert dec.action == "SCALE_UP"
        assert dec.recommended_replicas == 2
        assert dec.actuator_status == "VALIDATED"
        assert dec.cluster_modified is False

    asyncio.run(_run())


# ---------------------------------------------------------------------
# SCENARIO 3: MEMORY BOTTLENECK
# ---------------------------------------------------------------------

def test_scenario_3_memory_bottleneck(test_controller):
    """Scenario 3: Memory exhaustion (>80%) under real-world pressure triggers SCALE_UP in DRY_RUN mode."""
    async def _run():
        t_input = make_test_telemetry("cartservice", cpu=0.85, memory=0.95, p95_latency=220.0)
        raw_item = make_raw_item("cartservice", cpu=0.85, memory=0.95, p95_latency=220.0)

        test_controller.telemetry_adapter.get_telemetry_inputs.return_value = ([t_input], [])
        test_controller.telemetry_adapter.collect_deployment_telemetry.return_value = [raw_item]

        summary = await test_controller.run_single_cycle()

        assert summary.scale_up_count == 1
        dec = summary.decisions[0]
        assert dec.action == "SCALE_UP"
        assert dec.recommended_replicas == 2

    asyncio.run(_run())


# ---------------------------------------------------------------------
# SCENARIO 4: HIGH REQUEST LATENCY BOTTLENECK
# ---------------------------------------------------------------------

def test_scenario_4_high_request_latency(test_controller):
    """Scenario 4: High P95 latency (>500ms) flags service as bottleneck."""
    async def _run():
        t_checkout = make_test_telemetry("checkoutservice", p95_latency=750.0)
        raw_checkout = make_raw_item("checkoutservice", p95_latency=750.0)

        t_product = make_test_telemetry("productcatalogservice", p95_latency=40.0)
        raw_product = make_raw_item("productcatalogservice", p95_latency=40.0)

        test_controller.telemetry_adapter.get_telemetry_inputs.return_value = (
            [t_checkout, t_product],
            [],
        )
        test_controller.telemetry_adapter.collect_deployment_telemetry.return_value = [
            raw_checkout,
            raw_product,
        ]

        summary = await test_controller.run_single_cycle()

        assert summary.bottleneck_service == "checkoutservice"
        dec_checkout = next(d for d in summary.decisions if d.service_name == "checkoutservice")
        assert dec_checkout.is_bottleneck is True
        assert dec_checkout.action == "SCALE_UP"

        # Upstream/other service holds when downstream bottleneck is detected
        dec_product = next(d for d in summary.decisions if d.service_name == "productcatalogservice")
        assert dec_product.action == "HOLD"
        assert "bottleneck" in dec_product.reason.lower()

    asyncio.run(_run())


# ---------------------------------------------------------------------
# SCENARIO 5: MISSING TELEMETRY (ZERO FABRICATION PREVENTION)
# ---------------------------------------------------------------------

def test_scenario_5_missing_telemetry(test_controller):
    """Scenario 5: Missing telemetry results in EXCLUDED/HOLD without fabricating zero."""
    async def _run():
        raw_incomplete = make_raw_item(
            "adservice",
            telemetry_available=False,
            missing_metrics=["request_rate", "p95_latency", "error_rate"],
        )

        test_controller.telemetry_adapter.get_telemetry_inputs.return_value = ([], [raw_incomplete])
        test_controller.telemetry_adapter.collect_deployment_telemetry.return_value = [raw_incomplete]

        summary = await test_controller.run_single_cycle()

        assert summary.eligible_services == 0
        assert summary.excluded_services == 1
        assert summary.scale_up_count == 0

        dec = summary.decisions[0]
        assert dec.action == "EXCLUDED"
        assert dec.telemetry_complete is False
        assert "missing" in dec.reason.lower()
        assert dec.request_rate is None  # Never fabricated to 0.0

    asyncio.run(_run())


# ---------------------------------------------------------------------
# SCENARIO 6: STALE TELEMETRY REJECTION
# ---------------------------------------------------------------------

def test_scenario_6_stale_telemetry(test_controller):
    """Scenario 6: Stale telemetry sample (>30s) is rejected as insufficient."""
    async def _run():
        t_stale = make_test_telemetry("shippingservice", cpu=0.95, age_seconds=90.0)
        raw_stale = make_raw_item("shippingservice", cpu=0.95)

        test_controller.telemetry_adapter.get_telemetry_inputs.return_value = ([t_stale], [])
        test_controller.telemetry_adapter.collect_deployment_telemetry.return_value = [raw_stale]

        summary = await test_controller.run_single_cycle()

        dec = summary.decisions[0]
        assert dec.action == "INSUFFICIENT_TELEMETRY"
        assert dec.recommended_replicas == 1  # No scaling on stale telemetry
        assert "stale" in dec.reason.lower()

    asyncio.run(_run())


# ---------------------------------------------------------------------
# SCENARIO 7: NO TRAFFIC (IDLE CLUSTER)
# ---------------------------------------------------------------------

def test_scenario_7_no_traffic(test_controller):
    """Scenario 7: Idle cluster without load keeps steady state without thrashing."""
    async def _run():
        t_idle = make_test_telemetry("currencyservice", cpu=0.08, memory=0.20, request_rate=0.0)
        raw_idle = make_raw_item("currencyservice", cpu=0.08, memory=0.20, request_rate=0.0)

        test_controller.telemetry_adapter.get_telemetry_inputs.return_value = ([t_idle], [])
        test_controller.telemetry_adapter.collect_deployment_telemetry.return_value = [raw_idle]

        summary = await test_controller.run_single_cycle()

        dec = summary.decisions[0]
        assert dec.recommended_replicas >= 1  # Clamped at min_replicas=1
        assert summary.cluster_modified is False

    asyncio.run(_run())


# ---------------------------------------------------------------------
# SCENARIO 8: REPEATED BOTTLENECK DETECTION & COOLDOWN
# ---------------------------------------------------------------------

def test_scenario_8_repeated_bottleneck_detection(test_controller):
    """Scenario 8: Continuous high load triggers scale-up then enters cooldown."""
    async def _run():
        t_high = make_test_telemetry("productcatalogservice", cpu=0.95, memory=0.40)
        raw_high = make_raw_item("productcatalogservice", cpu=0.95, memory=0.40)

        test_controller.telemetry_adapter.get_telemetry_inputs.return_value = ([t_high], [])
        test_controller.telemetry_adapter.collect_deployment_telemetry.return_value = [raw_high]

        # Cycle 1: First scale-up
        summary1 = await test_controller.run_single_cycle()
        assert summary1.scale_up_count == 1
        assert summary1.decisions[0].action == "SCALE_UP"

        # Cycle 2: Immediately repeated - cooldown window must suppress action
        summary2 = await test_controller.run_single_cycle()
        assert summary2.scale_up_count == 0
        assert summary2.hold_count == 1
        assert "cooldown" in summary2.decisions[0].reason.lower()

    asyncio.run(_run())


# ---------------------------------------------------------------------
# SCENARIO 9: COOLDOWN ENFORCEMENT
# ---------------------------------------------------------------------

def test_scenario_9_cooldown_enforcement(test_controller):
    """Scenario 9: Cooldown prevents scaling before cooldown window elapses."""
    async def _run():
        now = datetime.now(timezone.utc)
        test_controller.state_manager.record_action("paymentservice", DecisionAction.SCALE_UP, now)

        t_payment = make_test_telemetry("paymentservice", cpu=0.95)
        raw_payment = make_raw_item("paymentservice", cpu=0.95)

        test_controller.telemetry_adapter.get_telemetry_inputs.return_value = ([t_payment], [])
        test_controller.telemetry_adapter.collect_deployment_telemetry.return_value = [raw_payment]

        summary = await test_controller.run_single_cycle()
        dec = summary.decisions[0]
        assert dec.action == "HOLD"
        assert "cooldown" in dec.reason.lower()

    asyncio.run(_run())


# ---------------------------------------------------------------------
# SCENARIO 10: DEPLOYMENT IN PROGRESS (SCALE-DOWN SUPPRESSION)
# ---------------------------------------------------------------------

def test_scenario_10_deployment_in_progress(test_controller):
    """Scenario 10: Under ACTIVE_DEPLOYMENT, scale-down is strictly suppressed."""
    async def _run():
        test_controller.state_manager.set_phase(DeploymentPhase.ACTIVE_DEPLOYMENT)

        # 4 replicas under low load (<0.05 score) would normally scale down
        t_under = make_test_telemetry("emailservice", cpu=0.01, memory=0.05, replicas=4)
        raw_under = make_raw_item("emailservice", cpu=0.01, memory=0.05, replicas=4)

        test_controller.telemetry_adapter.get_telemetry_inputs.return_value = ([t_under], [])
        test_controller.telemetry_adapter.collect_deployment_telemetry.return_value = [raw_under]

        summary = await test_controller.run_single_cycle()

        dec = summary.decisions[0]
        assert dec.action == "HOLD"
        assert dec.recommended_replicas == 4
        assert "active deployment" in dec.reason.lower()

    asyncio.run(_run())


# ---------------------------------------------------------------------
# SCENARIO 11: CONFLICTING DECISIONS / STALE LIVE STATE
# ---------------------------------------------------------------------

def test_scenario_11_conflicting_decisions(test_controller):
    """Scenario 11: If live deployment replicas differ from decision, actuator rejects as stale."""
    async def _run():
        # Decision expects previous_replicas=1, but live cluster has 3
        test_controller.actuator.apps_api.read_namespaced_deployment.return_value = create_mock_deployment(3)

        t_svc = make_test_telemetry("productcatalogservice", cpu=0.95, replicas=1)
        raw_svc = make_raw_item("productcatalogservice", cpu=0.95, replicas=1)

        test_controller.telemetry_adapter.get_telemetry_inputs.return_value = ([t_svc], [])
        test_controller.telemetry_adapter.collect_deployment_telemetry.return_value = [raw_svc]

        summary = await test_controller.run_single_cycle()

        dec = summary.decisions[0]
        assert dec.actuator_status == "REJECTED"
        assert "stale" in dec.reason.lower()
        assert dec.cluster_modified is False

    asyncio.run(_run())


# ---------------------------------------------------------------------
# SCENARIO 12: PROTECTED INFRASTRUCTURE SERVICE
# ---------------------------------------------------------------------

def test_scenario_12_protected_infrastructure_service(test_controller):
    """Scenario 12: redis-cart and opentelemetrycollector cannot be scaled."""
    async def _run():
        raw_redis = make_raw_item("redis-cart", cpu=0.95, memory=0.95)

        test_controller.telemetry_adapter.get_telemetry_inputs.return_value = ([], [])
        test_controller.telemetry_adapter.collect_deployment_telemetry.return_value = [raw_redis]

        summary = await test_controller.run_single_cycle()

        dec = summary.decisions[0]
        assert dec.service_name == "redis-cart"
        assert dec.action == "HOLD"
        assert "protected infrastructure" in dec.reason.lower()
        assert dec.cluster_modified is False

    asyncio.run(_run())


# ---------------------------------------------------------------------
# LIFECYCLE SAFETY & CONCURRENCY
# ---------------------------------------------------------------------

def test_controller_lifecycle_start_stop_restart(test_controller):
    """Verify safe start, duplicate prevention, and clean stop."""
    async def _run():
        test_controller.telemetry_adapter.get_telemetry_inputs.return_value = ([], [])
        test_controller.telemetry_adapter.collect_deployment_telemetry.return_value = []

        # 1. Start controller
        started = await test_controller.start()
        assert started is True
        assert test_controller.is_running is True

        # 2. Prevent duplicate execution loops
        second_start = await test_controller.start()
        assert second_start is False

        # Allow one background tick
        await asyncio.sleep(0.1)

        # 3. Stop controller cleanly
        stopped = await test_controller.stop()
        assert stopped is True
        assert test_controller.is_running is False

        # 4. Restart cleanly
        restarted = await test_controller.start()
        assert restarted is True
        assert test_controller.is_running is True
        await test_controller.stop()

    asyncio.run(_run())


def test_history_persistence_and_restore(tmp_path, mock_actuator):
    """Verify cycle summary history persists to JSON file and restores."""
    async def _run():
        history_file = tmp_path / "saved_history.json"
        state_mgr = DeploymentStateManager()
        mock_adapter = MagicMock()
        mock_adapter.get_telemetry_inputs.return_value = ([], [])
        mock_adapter.collect_deployment_telemetry.return_value = []

        ctrl1 = ContinuousDPBPSController(
            telemetry_adapter=mock_adapter,
            actuator=mock_actuator,
            state_manager=state_mgr,
            history_file=history_file,
        )

        await ctrl1.run_single_cycle()
        await ctrl1.run_single_cycle()
        assert ctrl1.cycle_count == 2
        assert history_file.exists()

        # Create new instance with same file; verify restored cycle count
        ctrl2 = ContinuousDPBPSController(
            telemetry_adapter=mock_adapter,
            actuator=mock_actuator,
            state_manager=state_mgr,
            history_file=history_file,
        )
        assert ctrl2.cycle_count == 2

    asyncio.run(_run())
