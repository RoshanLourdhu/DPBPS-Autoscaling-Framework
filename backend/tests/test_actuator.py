"""
Unit tests for the DPBPS scaling actuator.

All Docker operations are mocked.
These tests must never execute real Docker scaling commands.
"""

import asyncio
import subprocess
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend import config as cfg
from backend.scaling import actuator as act
from backend.scaling.actuator import (
    ScalingError,
    apply_decision,
    apply_decisions,
    _validate_decision,
    _run_docker_compose,
)
from backend.scaling.models import (
    DecisionAction,
    DecisionOutput,
    DeploymentPhase,
    ScalingConfig,
)


# ---------------------------------------------------------------------
# TEST HELPERS
# ---------------------------------------------------------------------

def make_decision(
    service_name="dummy-service",
    action=DecisionAction.SCALE_UP,
    previous=1,
    requested=2,
):
    """Create a valid DecisionOutput for actuator testing."""

    return DecisionOutput(
        service_name=service_name,
        action=action,
        previous_replicas=previous,
        requested_replicas=requested,
        phase=DeploymentPhase.NORMAL_OPERATION,
        reason="Unit test decision",
        timestamp=datetime.now(timezone.utc),
        simulated=False,
    )


@pytest.fixture(autouse=True)
def reset_scaling_configuration(monkeypatch):
    """
    Reset scaling configuration before every test.

    Live scaling remains disabled unless a test explicitly enables it.
    """

    monkeypatch.setattr(cfg, "SCALING_ENABLED", False)
    monkeypatch.setattr(cfg, "SCALING_ALLOWLIST", [])

    # Keep tests independent of the actual Compose file.
    monkeypatch.setattr(
        act,
        "_get_service_definition",
        lambda service_name: {},
    )

    monkeypatch.setattr(
        act,
        "_service_has_host_port",
        lambda service_name: False,
    )

    monkeypatch.setattr(
        act,
        "_service_has_health_check",
        lambda service_name: True,
    )


def enable_scaling(monkeypatch, services=None):
    """Enable scaling for explicitly selected test services."""

    if services is None:
        services = ["dummy-service"]

    monkeypatch.setattr(cfg, "SCALING_ENABLED", True)
    monkeypatch.setattr(cfg, "SCALING_ALLOWLIST", services)


def mock_successful_scaling(monkeypatch):
    """
    Mock the scaling command and both post-scaling verification stages.

    This prevents any Docker subprocess from being executed.
    """

    monkeypatch.setattr(
        act,
        "_run_docker_compose",
        MagicMock(return_value=None),
    )

    monkeypatch.setattr(
        act,
        "_verify_replica_count",
        MagicMock(return_value=None),
    )

    monkeypatch.setattr(
        act,
        "_verify_replica_health",
        MagicMock(return_value=None),
    )


# ---------------------------------------------------------------------
# 1. GLOBAL SAFETY CHECKS
# ---------------------------------------------------------------------

def test_scaling_disabled_prevents_subprocess(monkeypatch):
    """Scaling must be rejected when the global switch is disabled."""

    monkeypatch.setattr(cfg, "SCALING_ENABLED", False)
    monkeypatch.setattr(cfg, "SCALING_ALLOWLIST", ["dummy-service"])

    decision = make_decision()

    with patch("subprocess.run") as mock_run:
        with pytest.raises(ScalingError) as exc:
            apply_decision(decision)

        assert "live scaling is disabled" in str(exc.value).lower()
        mock_run.assert_not_called()


def test_empty_allowlist_rejects(monkeypatch):
    """An empty allowlist must fail closed."""

    enable_scaling(monkeypatch, [])

    decision = make_decision()

    with patch("subprocess.run") as mock_run:
        with pytest.raises(ScalingError) as exc:
            apply_decision(decision)

        assert "allowlist" in str(exc.value).lower()
        mock_run.assert_not_called()


def test_service_not_in_allowlist_rejected(monkeypatch):
    """A service outside the allowlist must not be scaled."""

    enable_scaling(monkeypatch, ["product-service"])

    decision = make_decision("dummy-service")

    with patch("subprocess.run") as mock_run:
        with pytest.raises(ScalingError) as exc:
            apply_decision(decision)

        assert "not in the scaling allowlist" in str(exc.value).lower()
        mock_run.assert_not_called()


# ---------------------------------------------------------------------
# 2. ALLOWED SERVICE
# ---------------------------------------------------------------------

def test_allowed_service_without_host_port_allowed(monkeypatch):
    """
    An allowlisted service without a host-port mapping should pass
    decision validation.

    Docker operations and verification are mocked.
    """

    enable_scaling(monkeypatch, ["product-service"])

    decision = make_decision("product-service")

    mock_successful_scaling(monkeypatch)

    # This must complete without raising an exception.
    apply_decision(decision)

    act._run_docker_compose.assert_called_once_with(
        "product-service",
        2,
    )

    act._verify_replica_count.assert_called_once_with(
        "product-service",
        2,
    )

    act._verify_replica_health.assert_called_once_with(
        "product-service",
    )


def test_postgres_rejected_explicitly(monkeypatch):
    """PostgreSQL must be rejected because it is stateful."""

    enable_scaling(monkeypatch, ["postgres"])

    monkeypatch.setattr(
        act,
        "_service_has_host_port",
        lambda service_name: True,
    )

    decision = make_decision(
        service_name="postgres",
        previous=1,
        requested=2,
    )

    with pytest.raises(ScalingError) as exc:
        apply_decision(decision)

    assert "host-port mapping" in str(exc.value).lower()


def test_host_port_mapping_rejected(monkeypatch):
    """Any service with a host-port mapping must be rejected."""

    enable_scaling(monkeypatch)

    monkeypatch.setattr(
        act,
        "_service_has_host_port",
        lambda service_name: True,
    )

    decision = make_decision()

    with pytest.raises(ScalingError) as exc:
        apply_decision(decision)

    assert "host-port mapping" in str(exc.value).lower()


# ---------------------------------------------------------------------
# 3. REPLICA LIMIT VALIDATION
# ---------------------------------------------------------------------

def test_replica_below_min_rejected(monkeypatch):
    """Requested replicas below the configured minimum must fail."""

    enable_scaling(monkeypatch)

    custom_config = ScalingConfig(
        min_replicas=2,
        max_replicas=5,
        max_replica_change=2,
    )

    monkeypatch.setattr(
        act,
        "ScalingConfig",
        lambda: custom_config,
    )

    decision = make_decision(
        previous=2,
        requested=1,
    )

    with pytest.raises(ScalingError) as exc:
        apply_decision(decision)

    assert "out of allowed range" in str(exc.value).lower()


def test_replica_above_max_rejected(monkeypatch):
    """Requested replicas above the configured maximum must fail."""

    enable_scaling(monkeypatch)

    custom_config = ScalingConfig(
        min_replicas=1,
        max_replicas=5,
        max_replica_change=5,
    )

    monkeypatch.setattr(
        act,
        "ScalingConfig",
        lambda: custom_config,
    )

    decision = make_decision(
        previous=4,
        requested=6,
    )

    with pytest.raises(ScalingError) as exc:
        apply_decision(decision)

    assert "out of allowed range" in str(exc.value).lower()


def test_max_replica_change_exceeded(monkeypatch):
    """A decision cannot change replicas beyond max_replica_change."""

    enable_scaling(monkeypatch)

    custom_config = ScalingConfig(
        min_replicas=1,
        max_replicas=10,
        max_replica_change=1,
    )

    monkeypatch.setattr(
        act,
        "ScalingConfig",
        lambda: custom_config,
    )

    decision = make_decision(
        previous=1,
        requested=3,
    )

    with pytest.raises(ScalingError) as exc:
        apply_decision(decision)

    assert "replica change exceeds max allowed" in str(exc.value).lower()


def test_noop_decision_rejected(monkeypatch):
    """A decision requesting no replica change must not execute Docker."""

    enable_scaling(monkeypatch)

    decision = make_decision(
        previous=2,
        requested=2,
    )

    with patch.object(act, "_run_docker_compose") as mock_scale:
        with pytest.raises(ScalingError) as exc:
            apply_decision(decision)

        assert "no replica change" in str(exc.value).lower()
        mock_scale.assert_not_called()


# ---------------------------------------------------------------------
# 4. DOCKER COMMAND ERROR HANDLING
# ---------------------------------------------------------------------

def test_subprocess_failure_raises(monkeypatch):
    """A non-zero Docker Compose exit code must raise ScalingError."""

    result = MagicMock(
        returncode=1,
        stdout="",
        stderr="Docker command failed",
    )

    with patch(
        "subprocess.run",
        return_value=result,
    ):
        with pytest.raises(ScalingError) as exc:
            _run_docker_compose("dummy-service", 2)

    assert "docker compose scaling failed" in str(exc.value).lower()


def test_subprocess_timeout_raises(monkeypatch):
    """A Docker command timeout must raise ScalingError."""

    with patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(
            cmd="docker compose up",
            timeout=30,
        ),
    ):
        with pytest.raises(ScalingError) as exc:
            _run_docker_compose("dummy-service", 2)

    assert "timed out" in str(exc.value).lower()


def test_timeout_error_raises():
    """A standard TimeoutError must also be handled."""

    with patch(
        "subprocess.run",
        side_effect=TimeoutError("timeout"),
    ):
        with pytest.raises(ScalingError) as exc:
            _run_docker_compose("dummy-service", 2)

    assert "timed out" in str(exc.value).lower()


def test_docker_command_uses_project_root():
    """Docker Compose must execute from the dynamically resolved project root."""

    result = MagicMock(
        returncode=0,
        stdout="",
        stderr="",
    )

    with patch(
        "subprocess.run",
        return_value=result,
    ) as mock_run:

        _run_docker_compose("product-service", 2)

    kwargs = mock_run.call_args.kwargs

    assert kwargs["cwd"] == str(act.PROJECT_ROOT)


# ---------------------------------------------------------------------
# 5. MULTIPLE DECISIONS
# ---------------------------------------------------------------------

def test_apply_decisions_stops_on_first_failure(monkeypatch):
    """
    Processing must stop when one decision fails.

    The test mocks the individual decision application so that it
    specifically tests sequential failure handling.
    """

    enable_scaling(
        monkeypatch,
        ["dummy-service", "product-service"],
    )

    good = make_decision(
        "dummy-service",
        previous=1,
        requested=2,
    )

    bad = make_decision(
        "product-service",
        previous=1,
        requested=2,
    )

    monkeypatch.setattr(
        act,
        "validate_scaling_configuration",
        lambda: [],
    )

    with patch.object(
        act,
        "apply_decision",
        side_effect=[
            None,
            ScalingError("Simulated scaling failure"),
        ],
    ) as mock_apply:

        with pytest.raises(ScalingError):
            apply_decisions([good, bad])

        assert mock_apply.call_count == 2


def test_apply_decisions_preflight_failure_prevents_scaling(monkeypatch):
    """Configuration validation failure must prevent all scaling."""

    enable_scaling(monkeypatch)

    decision = make_decision()

    monkeypatch.setattr(
        act,
        "validate_scaling_configuration",
        lambda: ["Invalid scaling configuration"],
    )

    with patch.object(act, "apply_decision") as mock_apply:

        with pytest.raises(ScalingError) as exc:
            apply_decisions([decision])

        assert "configuration validation failed" in str(exc.value).lower()
        mock_apply.assert_not_called()


# ---------------------------------------------------------------------
# 6. API SIMULATION SAFETY
# ---------------------------------------------------------------------

def test_api_evaluate_without_live_scaling(monkeypatch):
    import importlib
    from fastapi.testclient import TestClient
    from backend.app.main import app

    # Import the actual Python module, not the APIRouter object.
    api_module = importlib.import_module(
        "backend.app.api.v1_router"
    )

    # Keep live scaling disabled.
    monkeypatch.setenv("SCALING_ENABLED", "false")

    calls = {"count": 0}

    def fake_evaluate(telemetry):
        calls["count"] += 1
        return []

    monkeypatch.setattr(
        api_module.dpbps_controller,
        "evaluate",
        fake_evaluate
    )

    client = TestClient(app)

    response = client.post(
        "/api/v1/scaling/evaluate",
        json=[]
    )

    assert response.status_code == 200
    assert response.json() == []
    assert calls["count"] == 1