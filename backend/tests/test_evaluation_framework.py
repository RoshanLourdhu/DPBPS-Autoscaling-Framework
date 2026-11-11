"""
Unit and integration tests for Stage 9 Comparative Evaluation Framework.
Covers trace loading, baseline policies, replay determinism, and metric calculations.
"""

import pytest
from datetime import datetime, timezone
from backend.evaluation.models import (
    PolicyType,
    ScalingAction,
    NormalizedObservation,
    PolicyRecommendation
)
from backend.evaluation.baselines.static_policy import StaticPolicy
from backend.evaluation.baselines.cpu_threshold_policy import CPUThresholdPolicy
from backend.evaluation.baselines.hpa_style_policy import HPAStylePolicy
from backend.evaluation.dpbps_adapter import DPBPSAdapter
from backend.evaluation.trace_loader import TraceLoader, EXPERIMENT_CATALOG
from backend.evaluation.replay_engine import TraceReplayEngine


def test_static_policy():
    """Verify Static Policy maintains constant replica count and HOLD decisions."""
    policy = StaticPolicy(initial_replicas=1)
    obs = NormalizedObservation(
        experiment_id="test",
        service_name="frontend",
        timestamp=datetime.now(timezone.utc).isoformat(),
        elapsed_seconds=10.0,
        cpu_utilization_ratio=0.95,
        p95_latency_ms=1500.0,
        telemetry_available=True
    )
    rec = policy.evaluate(obs)
    assert rec.action == ScalingAction.HOLD
    assert rec.target_replicas == 1
    assert rec.replica_delta == 0
    assert policy.get_current_replicas("frontend") == 1


def test_cpu_threshold_scale_up_and_cooldown():
    """Verify CPU Threshold policy scales up on sustained high CPU and respects cooldown."""
    policy = CPUThresholdPolicy(
        scale_up_threshold=0.70,
        scale_down_threshold=0.30,
        cooldown_sec=30.0,
        consecutive_required=2
    )

    # 1st cycle above threshold -> HOLD (requires 2 consecutive)
    obs1 = NormalizedObservation(
        experiment_id="test",
        service_name="frontend",
        timestamp="2026-11-10T00:00:10Z",
        elapsed_seconds=10.0,
        cpu_utilization_ratio=0.85,
        telemetry_available=True
    )
    rec1 = policy.evaluate(obs1)
    assert rec1.action == ScalingAction.HOLD

    # 2nd consecutive cycle above threshold -> SCALE_UP
    obs2 = NormalizedObservation(
        experiment_id="test",
        service_name="frontend",
        timestamp="2026-11-10T00:00:20Z",
        elapsed_seconds=20.0,
        cpu_utilization_ratio=0.85,
        telemetry_available=True
    )
    rec2 = policy.evaluate(obs2)
    assert rec2.action == ScalingAction.SCALE_UP
    assert rec2.target_replicas == 2
    assert policy.get_current_replicas("frontend") == 2

    # 3rd cycle (t=25s) -> counter becomes 1
    obs3 = NormalizedObservation(
        experiment_id="test",
        service_name="frontend",
        timestamp="2026-11-10T00:00:25Z",
        elapsed_seconds=25.0,
        cpu_utilization_ratio=0.90,
        telemetry_available=True
    )
    rec3 = policy.evaluate(obs3)
    assert rec3.action == ScalingAction.HOLD

    # 4th cycle (t=35s) -> counter becomes 2, but (35s - 20s) = 15s < 30s cooldown -> HOLD (cooldown)
    obs4 = NormalizedObservation(
        experiment_id="test",
        service_name="frontend",
        timestamp="2026-11-10T00:00:35Z",
        elapsed_seconds=35.0,
        cpu_utilization_ratio=0.90,
        telemetry_available=True
    )
    rec4 = policy.evaluate(obs4)
    assert rec4.action == ScalingAction.HOLD
    assert "cooldown" in rec4.reason.lower()


def test_cpu_threshold_bounds():
    """Verify CPU Threshold respects min and max replica limits."""
    policy = CPUThresholdPolicy(min_replicas=1, max_replicas=3, consecutive_required=1, cooldown_sec=0)
    policy.set_current_replicas("frontend", 3)
    
    obs = NormalizedObservation(
        experiment_id="test",
        service_name="frontend",
        timestamp="2026-11-10T00:00:10Z",
        elapsed_seconds=10.0,
        cpu_utilization_ratio=0.95,
        telemetry_available=True
    )
    rec = policy.evaluate(obs)
    assert rec.action == ScalingAction.HOLD
    assert "max replicas" in rec.reason.lower()


def test_hpa_style_formula():
    """Verify HPA formula: desired = ceil[current * (util / 0.70)]."""
    policy = HPAStylePolicy(target_cpu_utilization=0.70, tolerance=0.10)
    # Ratio = 1.05 / 0.70 = 1.5 -> ceil(1 * 1.5) = 2
    obs = NormalizedObservation(
        experiment_id="test",
        service_name="frontend",
        timestamp="2026-11-10T00:00:10Z",
        elapsed_seconds=10.0,
        cpu_utilization_ratio=1.05,
        telemetry_available=True
    )
    rec = policy.evaluate(obs)
    assert rec.action == ScalingAction.SCALE_UP
    assert rec.target_replicas == 2


def test_hpa_style_tolerance():
    """Verify HPA tolerance band: +/-10% around target produces HOLD."""
    policy = HPAStylePolicy(target_cpu_utilization=0.70, tolerance=0.10)
    # 0.72 is within [0.63, 0.77]
    obs = NormalizedObservation(
        experiment_id="test",
        service_name="frontend",
        timestamp="2026-11-10T00:00:10Z",
        elapsed_seconds=10.0,
        cpu_utilization_ratio=0.72,
        telemetry_available=True
    )
    rec = policy.evaluate(obs)
    assert rec.action == ScalingAction.HOLD
    assert "tolerance" in rec.reason.lower()


def test_unpopulated_telemetry_handling():
    """Verify all policies output INSUFFICIENT_DATA or HOLD when telemetry is unavailable."""
    obs_unavail = NormalizedObservation(
        experiment_id="test",
        service_name="frontend",
        timestamp="2026-11-10T00:00:10Z",
        elapsed_seconds=10.0,
        telemetry_available=False
    )
    p_cpu = CPUThresholdPolicy()
    p_hpa = HPAStylePolicy()
    p_dpbps = DPBPSAdapter()

    assert p_cpu.evaluate(obs_unavail).action == ScalingAction.INSUFFICIENT_DATA
    assert p_hpa.evaluate(obs_unavail).action == ScalingAction.INSUFFICIENT_DATA
    assert p_dpbps.evaluate(obs_unavail).action == ScalingAction.INSUFFICIENT_DATA


def test_trace_loader_experiment_catalog():
    """Verify TraceLoader successfully loads an actual experiment trace."""
    loader = TraceLoader()
    observations, empirical_decs, meta = loader.load_experiment_trace("E01")
    assert meta["profile"] == "NORMAL_TRAFFIC"
    assert len(observations) == 140  # 14 snapshots * 10 services
    assert "frontend" in empirical_decs


def test_trace_replay_engine_determinism():
    """Verify trace replay engine is 100% deterministic on identical input traces."""
    engine = TraceReplayEngine()
    results1 = engine.replay_experiment("E01")
    results2 = engine.replay_experiment("E01")

    summ1 = results1[PolicyType.DPBPS][1]
    summ2 = results2[PolicyType.DPBPS][1]

    assert summ1.total_evaluations == summ2.total_evaluations
    assert summ1.hold_count == summ2.hold_count
    assert summ1.scale_up_count == summ2.scale_up_count
    assert summ1.scale_down_count == summ2.scale_down_count
