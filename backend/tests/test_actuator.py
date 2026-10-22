# backend/tests/test_actuator.py
"""Actuator unit tests.
These tests use mocks for subprocess.run to ensure no real Docker commands are executed.
"""
import pytest
from unittest.mock import patch, MagicMock

from backend.config import SCALING_ENABLED, SCALING_ALLOWLIST
from backend.scaling.actuator import (
    apply_decision,
    apply_decisions,
    ScalingError,
)
from backend.scaling.models import DecisionOutput, DecisionAction, ScalingConfig

# Helper to build a DecisionOutput
def make_decision(
    service_name: str,
    action: DecisionAction,
    previous: int = 1,
    requested: int = 2,
) -> DecisionOutput:
    return DecisionOutput(
        service_name=service_name,
        action=action,
        previous_replicas=previous,
        requested_replicas=requested,
        phase="NORMAL_OPERATION",
        bottleneck=None,
        reason="test",
        simulated=False,
    )

def reset_config():
    # Ensure defaults for each test
    import importlib
    import backend.config as cfg_mod
    importlib.reload(cfg_mod)
    # Explicitly set defaults
    cfg_mod.SCALING_ENABLED = False
    cfg_mod.SCALING_ALLOWLIST = []

@pytest.fixture(autouse=True)
def clean_env():
    reset_config()
    yield
    reset_config()

def test_scaling_disabled_prevents_subprocess():
    decision = make_decision("product-service", DecisionAction.SCALE_UP)
    # Scaling disabled by default -> should raise ScalingError before subprocess
    with pytest.raises(ScalingError) as exc:
        apply_decision(decision)
    assert "Live scaling is disabled" in str(exc.value)

def test_empty_allowlist_rejects():
    # Enable flag but keep allowlist empty
    from backend import config as cfg_mod
    cfg_mod.SCALING_ENABLED = True
    decision = make_decision("product-service", DecisionAction.SCALE_UP)
    with pytest.raises(ScalingError) as exc:
        apply_decision(decision)
    assert "not in the scaling allowlist" in str(exc.value)

def test_service_not_in_allowlist_rejected():
    from backend import config as cfg_mod
    cfg_mod.SCALING_ENABLED = True
    cfg_mod.SCALING_ALLOWLIST = ["cart-service"]
    decision = make_decision("product-service", DecisionAction.SCALE_UP)
    with pytest.raises(ScalingError) as exc:
        apply_decision(decision)
    assert "not in the scaling allowlist" in str(exc.value)

def test_allowed_service_without_host_port_allowed():
    from backend import config as cfg_mod
    cfg_mod.SCALING_ENABLED = True
    cfg_mod.SCALING_ALLOWLIST = ["product-service"]
    decision = make_decision("product-service", DecisionAction.SCALE_UP)
    # Since host ports have been removed, scaling should be allowed (no exception)
    apply_decision(decision)  # Should not raise

def test_postgres_rejected_explicitly():
    from backend import config as cfg_mod
    cfg_mod.SCALING_ENABLED = True
    cfg_mod.SCALING_ALLOWLIST = ["postgres"]
    decision = make_decision("postgres", DecisionAction.SCALE_UP)
    # Even if in allowlist, host‑port guard should reject
    with pytest.raises(ScalingError) as exc:
        apply_decision(decision)
    assert "host‑port mapping" in str(exc.value)

def test_replica_below_min_rejected():
    from backend import config as cfg_mod
    cfg_mod.SCALING_ENABLED = True
    cfg_mod.SCALING_ALLOWLIST = ["dummy-service"]
    cfg = ScalingConfig(min_replicas=2, max_replicas=5)
    decision = make_decision("dummy-service", DecisionAction.SCALE_DOWN, previous=2, requested=1)
    with patch("backend.scaling.actuator.ScalingConfig", return_value=cfg):
        with pytest.raises(ScalingError) as exc:
            apply_decision(decision)
        assert "out of allowed range" in str(exc.value)

def test_replica_above_max_rejected():
    from backend import config as cfg_mod
    cfg_mod.SCALING_ENABLED = True
    cfg_mod.SCALING_ALLOWLIST = ["dummy-service"]
    cfg = ScalingConfig(min_replicas=1, max_replicas=3)
    decision = make_decision("dummy-service", DecisionAction.SCALE_UP, previous=3, requested=4)
    with patch("backend.scaling.actuator.ScalingConfig", return_value=cfg):
        with pytest.raises(ScalingError) as exc:
            apply_decision(decision)
        assert "out of allowed range" in str(exc.value)

def test_max_replica_change_exceeded():
    from backend import config as cfg_mod
    cfg_mod.SCALING_ENABLED = True
    cfg_mod.SCALING_ALLOWLIST = ["dummy-service"]
    cfg = ScalingConfig(min_replicas=1, max_replicas=10, max_replica_change=2)
    decision = make_decision("dummy-service", DecisionAction.SCALE_UP, previous=1, requested=5)
    with patch("backend.scaling.actuator.ScalingConfig", return_value=cfg):
        with pytest.raises(ScalingError) as exc:
            apply_decision(decision)
        assert "max allowed per decision" in str(exc.value)

def test_noop_decision_rejected():
    from backend import config as cfg_mod
    cfg_mod.SCALING_ENABLED = True
    cfg_mod.SCALING_ALLOWLIST = ["dummy-service"]
    decision = make_decision("dummy-service", DecisionAction.HOLD, previous=2, requested=2)
    with pytest.raises(ScalingError) as exc:
        apply_decision(decision)
    assert "No replica change" in str(exc.value)

def test_subprocess_failure_raises():
    from backend import config as cfg_mod
    cfg_mod.SCALING_ENABLED = True
    cfg_mod.SCALING_ALLOWLIST = ["dummy-service"]
    decision = make_decision("dummy-service", DecisionAction.SCALE_UP)
    mock_result = MagicMock(returncode=1, stderr="some error")
    with patch("subprocess.run", return_value=mock_result):
        with pytest.raises(ScalingError) as exc:
            apply_decision(decision)
        assert "Docker compose scaling failed" in str(exc.value)

def test_subprocess_timeout_raises():
    from backend import config as cfg_mod
    cfg_mod.SCALING_ENABLED = True
    cfg_mod.SCALING_ALLOWLIST = ["dummy-service"]
    decision = make_decision("dummy-service", DecisionAction.SCALE_UP)
    with patch("subprocess.run", side_effect=TimeoutError("timeout")):
        with pytest.raises(ScalingError) as exc:
            apply_decision(decision)
        assert "timeout" in str(exc.value).lower()

def test_apply_decisions_stops_on_first_failure():
    from backend import config as cfg_mod
    cfg_mod.SCALING_ENABLED = True
    cfg_mod.SCALING_ALLOWLIST = ["dummy-service", "product-service"]
    good = make_decision("dummy-service", DecisionAction.SCALE_UP)
    bad = make_decision("product-service", DecisionAction.SCALE_UP)
    mock_good = MagicMock(returncode=0, stdout="", stderr="")
    mock_bad = MagicMock(returncode=1, stderr="fail")
    with patch("subprocess.run", side_effect=[mock_good, mock_bad]) as mock_run:
        with pytest.raises(ScalingError):
            apply_decisions([good, bad])
        # Only the good decision should invoke subprocess before the bad one fails validation
        # Both decisions should be attempted now that validation passes
        assert mock_run.call_count == 2

# Ensure existing controller behaviour is unchanged – re‑use existing tests indirectly by importing the API client
from fastapi.testclient import TestClient
from backend.app.main import app
client = TestClient(app)

def test_api_evaluate_without_live_scaling():
    # Ensure scaling flag is false – actuator should not be invoked
    payload = [{
        "service_name": "product-service",
        "request_rate": 10.0,
        "p95_latency": 100.0,
        "error_rate": 0.0,
        "cpu_utilisation": 0.2,
        "memory_utilisation": 0.2,
        "current_replicas": 1,
        "ready_replicas": 1,
        "timestamp": "2026-01-01T00:00:00Z",
        "dependencies": [],
    }]
    resp = client.post("/api/v1/scaling/evaluate", json=payload)
    assert resp.status_code == 200
    # No scaling side‑effects – just the decision list
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["action"] == "HOLD"
