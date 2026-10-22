# backend/tests/test_actuator_safety.py
"""Comprehensive safety tests for the actuator with mocked Docker interactions.
These tests cover:
1. Successful scaling with correct replica count and healthy containers.
2. Replica‑count mismatch leading to ScalingError.
3. Replica‑count mismatch followed by successful rollback.
4. Rollback failure.
5. Unhealthy replica detection.
6. Replica remains in starting state until timeout.
7. Container without health check.
8. Docker command failures (ps, inspect, scaling command).
9. Scaling disabled.
10. Service not in allow‑list.
11. Host‑port mapping rejection.
12. Min/Max replica limits.
13. Max replica‑change limit.
14. Verification timeout handling.
15. No Docker scaling invocation when pre‑flight validation fails.
"""

import pytest
from unittest.mock import patch, MagicMock

# Import the actuator functions and classes
from backend.scaling.actuator import (
    apply_decision,
    ScalingError,
    get_replica_count,
)
from backend.scaling.models import DecisionOutput, DecisionAction, ScalingConfig
import backend.config as cfg

# Helper to construct a DecisionOutput instance
def make_decision(service_name: str, action: DecisionAction, previous: int, requested: int):
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

# Fixture to enable scaling and set an allowlist for most tests
@pytest.fixture(autouse=True)
def enable_scaling(monkeypatch):
    monkeypatch.setattr(cfg, "SCALING_ENABLED", True)
    monkeypatch.setattr(cfg, "SCALING_ALLOWLIST", ["dummy-service"])
    yield
    # Reset to defaults after each test (optional)
    monkeypatch.setattr(cfg, "SCALING_ENABLED", False)
    monkeypatch.setattr(cfg, "SCALING_ALLOWLIST", [])

# Factory to mock subprocess.run behaviour
def mock_subprocess_run_factory(
    ps_output="",
    inspect_running="true",
    inspect_health="healthy",
    ps_error=False,
    inspect_error=False,
    scale_error=False,
    health_missing=False,
):
    """Return a side‑effect function for subprocess.run.
    It distinguishes docker commands by their argument list.
    """
    def _run(cmd, **kwargs):
        # docker compose ps -q <service>
        if cmd[:3] == ["docker", "compose", "ps"]:
            if ps_error:
                return MagicMock(returncode=1, stdout="", stderr="ps error")
            return MagicMock(returncode=0, stdout=ps_output, stderr="")
        # docker inspect -f <format> <container>
        if cmd[:2] == ["docker", "inspect"]:
            template = cmd[3]
            if inspect_error:
                return MagicMock(returncode=1, stdout="", stderr="inspect error")
            if "Running" in template:
                return MagicMock(returncode=0, stdout=inspect_running, stderr="")
            if "Health.Status" in template:
                if health_missing:
                    return MagicMock(returncode=1, stdout="", stderr="no health")
                return MagicMock(returncode=0, stdout=inspect_health, stderr="")
        # docker compose up -d --scale <service>=<n>
        if cmd[:3] == ["docker", "compose", "up"]:
            if scale_error:
                return MagicMock(returncode=1, stdout="", stderr="scale error")
            return MagicMock(returncode=0, stdout="", stderr="")
        # default fallback
        return MagicMock(returncode=0, stdout="", stderr="")
    return _run

# 1. Successful scaling
def test_successful_scaling():
    decision = make_decision("dummy-service", DecisionAction.SCALE_UP, previous=1, requested=2)
    with patch("subprocess.run", side_effect=mock_subprocess_run_factory(ps_output="id1\nid2\n")):
        apply_decision(decision)
        assert get_replica_count("dummy-service") == 2

# 2. Replica count mismatch → ScalingError
def test_replica_count_mismatch():
    decision = make_decision("dummy-service", DecisionAction.SCALE_UP, previous=1, requested=3)
    with patch("subprocess.run", side_effect=mock_subprocess_run_factory(ps_output="id1\n")):
        with pytest.raises(ScalingError) as exc:
            apply_decision(decision)
        assert "replica count verification" in str(exc.value).lower()

# 3. Mismatch with successful rollback
def test_replica_mismatch_rollback_success():
    decision = make_decision("dummy-service", DecisionAction.SCALE_UP, previous=1, requested=3)
    # Sequence: after scaling ps returns 1, during rollback ps returns original 1
    ps_sequence = ["id1\n", "id1\n"]
    def side_effect(cmd, **kwargs):
        if cmd[:3] == ["docker", "compose", "ps"]:
            output = ps_sequence.pop(0)
            return MagicMock(returncode=0, stdout=output, stderr="")
        if cmd[:2] == ["docker", "inspect"]:
            return MagicMock(returncode=0, stdout="true", stderr="")
        if cmd[:3] == ["docker", "compose", "up"]:
            return MagicMock(returncode=0, stdout="", stderr="")
        return MagicMock(returncode=0, stdout="", stderr="")
    with patch("subprocess.run", side_effect=side_effect):
        with pytest.raises(ScalingError) as exc:
            apply_decision(decision)
        assert "replica count verification" in str(exc.value).lower()
        # After rollback original count should be restored
        assert get_replica_count("dummy-service") == 1

# 4. Rollback failure
def test_rollback_failure():
    decision = make_decision("dummy-service", DecisionAction.SCALE_UP, previous=1, requested=3)
    def side_effect(cmd, **kwargs):
        if cmd[:3] == ["docker", "compose", "ps"]:
            return MagicMock(returncode=0, stdout="id1\n", stderr="")
        if cmd[:2] == ["docker", "inspect"]:
            return MagicMock(returncode=0, stdout="true", stderr="")
        if cmd[:3] == ["docker", "compose", "up"]:
            # First call (scaling) succeeds, second call (rollback) fails
            if "--scale" in cmd[5]:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="rollback error")
        return MagicMock(returncode=0, stdout="", stderr="")
    with patch("subprocess.run", side_effect=side_effect):
        with pytest.raises(ScalingError) as exc:
            apply_decision(decision)
        assert "rollback failed" in str(exc.value).lower()

# 5. Unhealthy replica detection
def test_unhealthy_replica():
    decision = make_decision("dummy-service", DecisionAction.SCALE_UP, previous=1, requested=2)
    with patch(
        "subprocess.run",
        side_effect=mock_subprocess_run_factory(ps_output="id1\nid2\n", inspect_health="unhealthy"),
    ):
        with pytest.raises(ScalingError) as exc:
            apply_decision(decision)
        assert "health verification" in str(exc.value).lower()

# 6. Starting replica timeout
def test_starting_replica_timeout():
    decision = make_decision("dummy-service", DecisionAction.SCALE_UP, previous=1, requested=2)
    def side_effect(cmd, **kwargs):
        if cmd[:3] == ["docker", "compose", "ps"]:
            return MagicMock(returncode=0, stdout="id1\nid2\n", stderr="")
        if cmd[:2] == ["docker", "inspect"]:
            if "Health.Status" in cmd[3]:
                return MagicMock(returncode=0, stdout="starting", stderr="")
            return MagicMock(returncode=0, stdout="true", stderr="")
        if cmd[:3] == ["docker", "compose", "up"]:
            return MagicMock(returncode=0, stdout="", stderr="")
        return MagicMock(returncode=0, stdout="", stderr="")
    with patch("subprocess.run", side_effect=side_effect):
        with pytest.raises(ScalingError) as exc:
            apply_decision(decision)
        assert "health verification" in str(exc.value).lower()

# 7. No health check defined (docker inspect fails for health)
def test_no_health_check_defined():
    decision = make_decision("dummy-service", DecisionAction.SCALE_UP, previous=1, requested=2)
    with patch(
        "subprocess.run",
        side_effect=mock_subprocess_run_factory(
            ps_output="id1\nid2\n", inspect_running="true", health_missing=True
        ),
    ):
        with pytest.raises(ScalingError) as exc:
            apply_decision(decision)
        assert "no health status" in str(exc.value).lower()

# 8. Docker ps command failure
def test_ps_command_failure():
    decision = make_decision("dummy-service", DecisionAction.SCALE_UP, previous=1, requested=2)
    with patch("subprocess.run", side_effect=mock_subprocess_run_factory(ps_error=True)):
        with pytest.raises(ScalingError) as exc:
            apply_decision(decision)
        assert "docker compose ps error" in str(exc.value).lower()

# 9. Docker scaling command failure
def test_scaling_command_failure():
    decision = make_decision("dummy-service", DecisionAction.SCALE_UP, previous=1, requested=2)
    with patch("subprocess.run", side_effect=mock_subprocess_run_factory(scale_error=True)):
        with pytest.raises(ScalingError) as exc:
            apply_decision(decision)
        assert "docker compose scaling failed" in str(exc.value).lower()

# 10. Scaling disabled
def test_scaling_disabled(monkeypatch):
    monkeypatch.setattr(cfg, "SCALING_ENABLED", False)
    decision = make_decision("dummy-service", DecisionAction.SCALE_UP, previous=1, requested=2)
    with pytest.raises(ScalingError) as exc:
        apply_decision(decision)
    assert "live scaling is disabled" in str(exc.value).lower()

# 11. Service not in allowlist
def test_not_in_allowlist(monkeypatch):
    monkeypatch.setattr(cfg, "SCALING_ENABLED", True)
    monkeypatch.setattr(cfg, "SCALING_ALLOWLIST", ["other-service"])
    decision = make_decision("dummy-service", DecisionAction.SCALE_UP, previous=1, requested=2)
    with pytest.raises(ScalingError) as exc:
        apply_decision(decision)
    assert "not in the scaling allowlist" in str(exc.value).lower()

# 12. Host‑port mapping rejection
def test_host_port_rejection(monkeypatch):
    from backend.scaling import actuator as act
    monkeypatch.setattr(act, "_service_has_host_port", lambda name: True)
    decision = make_decision("dummy-service", DecisionAction.SCALE_UP, previous=1, requested=2)
    with pytest.raises(ScalingError) as exc:
        apply_decision(decision)
    assert "defines a host‑port mapping" in str(exc.value).lower()

# 13. Min/Max replica limits
def test_replica_limits(monkeypatch):
    cfg = ScalingConfig(min_replicas=2, max_replicas=5, max_replica_change=2)
    monkeypatch.setattr("backend.scaling.models.ScalingConfig", lambda: cfg)
    # Below min
    decision = make_decision("dummy-service", DecisionAction.SCALE_UP, previous=1, requested=1)
    with pytest.raises(ScalingError) as exc:
        apply_decision(decision)
    assert "out of allowed range" in str(exc.value).lower()
    # Above max
    decision2 = make_decision("dummy-service", DecisionAction.SCALE_UP, previous=1, requested=6)
    with pytest.raises(ScalingError) as exc2:
        apply_decision(decision2)
    assert "out of allowed range" in str(exc2.value).lower()

# 14. Max replica‑change limit
def test_max_change_limit(monkeypatch):
    cfg = ScalingConfig(min_replicas=1, max_replicas=10, max_replica_change=1)
    monkeypatch.setattr("backend.scaling.models.ScalingConfig", lambda: cfg)
    decision = make_decision("dummy-service", DecisionAction.SCALE_UP, previous=1, requested=3)
    with pytest.raises(ScalingError) as exc:
        apply_decision(decision)
    assert "replica change exceeds max allowed" in str(exc.value).lower()

# 15. Verification timeout (replica count never reaches expected)
def test_replica_verification_timeout(monkeypatch):
    decision = make_decision("dummy-service", DecisionAction.SCALE_UP, previous=1, requested=3)
    with patch(
        "subprocess.run",
        side_effect=mock_subprocess_run_factory(ps_output="id1\n", inspect_running="true"),
    ):
        with pytest.raises(ScalingError) as exc:
            apply_decision(decision)
        assert "replica count verification failed" in str(exc.value).lower()

# 16. No Docker scaling invocation when pre‑flight fails (e.g., empty allowlist)
def test_no_scaling_invocation_on_preflight_failure(monkeypatch):
    monkeypatch.setattr(cfg, "SCALING_ALLOWLIST", [])
    decision = make_decision("dummy-service", DecisionAction.SCALE_UP, previous=1, requested=2)
    with patch("subprocess.run") as mock_run:
        with pytest.raises(ScalingError):
            apply_decision(decision)
        mock_run.assert_not_called()
"""End of tests"""
