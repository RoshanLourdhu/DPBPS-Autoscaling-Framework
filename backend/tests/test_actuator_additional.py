# backend/tests/test_actuator_additional.py
"""Additional actuator safety tests to expose missing safeguards.
These tests focus on behaviours not currently covered by existing suite:
* Verification that the number of running replicas matches the requested count after scaling.
* Ensuring that health/readiness of new replicas is checked (currently not implemented).
"""
import pytest
from unittest.mock import patch, MagicMock

from backend.scaling.actuator import apply_decision, ScalingError
from backend.scaling.models import DecisionOutput, DecisionAction

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

def test_replica_verification_mismatch():
    """Actuator should verify that the replica count after scaling matches the request.
    Current implementation does **not** perform this check, so the test is expected to fail.
    """
    decision = make_decision("dummy-service", DecisionAction.SCALE_UP, previous=1, requested=2)
    # Enable scaling and allowlist
    from backend import config as cfg_mod
    cfg_mod.SCALING_ENABLED = True
    cfg_mod.SCALING_ALLOWLIST = ["dummy-service"]
    # Mock subprocess.run to succeed
    mock_run = MagicMock(returncode=0, stdout="", stderr="")
    # Mock get_replica_count to return a different count (e.g., still 1)
    with patch("subprocess.run", return_value=mock_run):
        with patch("backend.scaling.actuator.get_replica_count", return_value=1):
            # Expected: ScalingError because actual replicas != requested
            with pytest.raises(ScalingError) as exc:
                apply_decision(decision)
            assert "replica count verification" in str(exc.value).lower()

def test_no_health_check_after_scale():
    """Actuator should ensure newly scaled replicas are healthy before reporting success.
    This behavior is not present; test demonstrates the gap.
    """
    decision = make_decision("dummy-service", DecisionAction.SCALE_UP, previous=1, requested=2)
    from backend import config as cfg_mod
    cfg_mod.SCALING_ENABLED = True
    cfg_mod.SCALING_ALLOWLIST = ["dummy-service"]
    mock_run = MagicMock(returncode=0, stdout="", stderr="")
    # Assume get_replica_count returns correct count but health check function is missing
    with patch("subprocess.run", return_value=mock_run):
        # No health check function to mock – apply_decision will succeed silently.
        apply_decision(decision)
        # If health check were required, this would raise or log warning.
        # Here we simply assert that the function completed without error, indicating missing safeguard.
        assert True
