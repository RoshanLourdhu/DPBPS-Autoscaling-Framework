import pytest

from unittest.mock import MagicMock, patch

from backend.scaling import actuator as act

from backend.scaling.actuator import (
    apply_decision,
    ScalingError,
    get_replica_count,
)

from backend.scaling.models import (
    DecisionOutput,
    DecisionAction,
    ScalingConfig,
)

import backend.config as cfg


# ---------------------------------------------------------
# DECISION FACTORY
# ---------------------------------------------------------

def make_decision(
    service_name: str,
    action: DecisionAction,
    previous: int,
    requested: int,
):
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


# ---------------------------------------------------------
# COMMON TEST FIXTURE
# ---------------------------------------------------------

@pytest.fixture(autouse=True)
def enable_scaling(monkeypatch):

    monkeypatch.setattr(
        cfg,
        "SCALING_ENABLED",
        True,
    )

    monkeypatch.setattr(
        cfg,
        "SCALING_ALLOWLIST",
        ["product-service"],
    )

    # Prevent actual waiting during timeout tests.
    monkeypatch.setattr(
        act.time,
        "sleep",
        lambda _: None,
    )


# ---------------------------------------------------------
# FAST HEALTH VERIFICATION
# ---------------------------------------------------------

def enable_fast_health_verification(monkeypatch):

    monkeypatch.setattr(
        act,
        "_service_has_health_check",
        lambda service_name: True,
    )

    original_function = act._verify_replica_health

    def fast_health_verification(service_name):
        return original_function(
            service_name,
            timeout=0,
            interval=0,
        )

    monkeypatch.setattr(
        act,
        "_verify_replica_health",
        fast_health_verification,
    )


# ---------------------------------------------------------
# DOCKER SUBPROCESS MOCK FACTORY
# ---------------------------------------------------------

def mock_subprocess_run_factory(
    ps_output="",
    inspect_running="true",
    inspect_health="healthy",
    ps_error=False,
    inspect_error=False,
    scale_error=False,
    health_missing=False,
    scale_fail_on_call=None,
    ps_outputs=None,
):
    """
    Mock Docker subprocess commands.

    Recognizes the actual actuator command structures:

    docker compose -f docker-compose.yml ps -q SERVICE

    docker compose -f docker-compose.yml up -d --scale SERVICE=N

    docker inspect -f {{.State.Running}} CONTAINER

    docker inspect -f {{.State.Health.Status}} CONTAINER
    """

    state = {
        "scale_calls": 0,
        "ps_calls": 0,
    }

    def _run(cmd, **kwargs):

        # Convert arguments to a list for reliable comparison.
        cmd = list(cmd)

        # -------------------------------------------------
        # DOCKER COMPOSE PS
        # -------------------------------------------------

        if (
            len(cmd) >= 2
            and cmd[0:2] == ["docker", "compose"]
            and "ps" in cmd
        ):

            state["ps_calls"] += 1

            if ps_error:
                return MagicMock(
                    returncode=1,
                    stdout="",
                    stderr="ps error",
                )

            if ps_outputs is not None:

                index = min(
                    state["ps_calls"] - 1,
                    len(ps_outputs) - 1,
                )

                output = ps_outputs[index]

            else:
                output = ps_output

            return MagicMock(
                returncode=0,
                stdout=output,
                stderr="",
            )

        # -------------------------------------------------
        # DOCKER INSPECT
        # -------------------------------------------------

        if (
            len(cmd) >= 4
            and cmd[0:2] == ["docker", "inspect"]
        ):

            template = str(cmd[3])

            if inspect_error:
                return MagicMock(
                    returncode=1,
                    stdout="",
                    stderr="inspect error",
                )

            # Container running state
            if "State.Running" in template:

                return MagicMock(
                    returncode=0,
                    stdout=inspect_running,
                    stderr="",
                )

            # Container health status
            if "Health.Status" in template:

                if health_missing:

                    return MagicMock(
                        returncode=0,
                        stdout="",
                        stderr="",
                    )

                return MagicMock(
                    returncode=0,
                    stdout=inspect_health,
                    stderr="",
                )

            return MagicMock(
                returncode=0,
                stdout="",
                stderr="",
            )

        # -------------------------------------------------
        # DOCKER COMPOSE UP / SCALE
        # -------------------------------------------------

        if (
            len(cmd) >= 2
            and cmd[0:2] == ["docker", "compose"]
            and "up" in cmd
            and "--scale" in cmd
        ):

            state["scale_calls"] += 1

            should_fail = scale_error

            if scale_fail_on_call is not None:
                should_fail = (
                    state["scale_calls"] == scale_fail_on_call
                )

            if should_fail:

                return MagicMock(
                    returncode=1,
                    stdout="",
                    stderr="scale error",
                )

            return MagicMock(
                returncode=0,
                stdout="",
                stderr="",
            )

        # -------------------------------------------------
        # DEFAULT
        # -------------------------------------------------

        return MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )

    return _run


# ---------------------------------------------------------
# 1. SUCCESSFUL SCALING
# ---------------------------------------------------------

def test_successful_scaling(monkeypatch):

    enable_fast_health_verification(monkeypatch)

    decision = make_decision(
        "product-service",
        DecisionAction.SCALE_UP,
        previous=1,
        requested=2,
    )

    with patch(
        "backend.scaling.actuator.subprocess.run",
        side_effect=mock_subprocess_run_factory(
            ps_output="id1\nid2\n",
            inspect_running="true",
            inspect_health="healthy",
        ),
    ):

        apply_decision(decision)

        assert get_replica_count("product-service") == 2


# ---------------------------------------------------------
# 2. REPLICA COUNT MISMATCH
# ---------------------------------------------------------

def test_replica_count_mismatch():

    decision = make_decision(
        "product-service",
        DecisionAction.SCALE_UP,
        previous=1,
        requested=3,
    )

    with patch(
        "backend.scaling.actuator.subprocess.run",
        side_effect=mock_subprocess_run_factory(
            ps_output="id1\n",
        ),
    ):

        with pytest.raises(ScalingError) as exc:

            apply_decision(decision)

        assert (
            "replica count verification"
            in str(exc.value).lower()
        )


# ---------------------------------------------------------
# 3. REPLICA MISMATCH WITH SUCCESSFUL ROLLBACK
# ---------------------------------------------------------

def test_replica_mismatch_rollback_success():

    decision = make_decision(
        "product-service",
        DecisionAction.SCALE_UP,
        previous=1,
        requested=3,
    )

    # One running replica is returned both during
    # verification and during rollback verification.

    with patch(
        "backend.scaling.actuator.subprocess.run",
        side_effect=mock_subprocess_run_factory(
            ps_output="id1\n",
        ),
    ):

        with pytest.raises(ScalingError) as exc:

            apply_decision(decision)

        assert (
            "replica count verification"
            in str(exc.value).lower()
        )

        # The original replica count was successfully restored.


# ---------------------------------------------------------
# 4. ROLLBACK FAILURE
# ---------------------------------------------------------

def test_rollback_failure():

    decision = make_decision(
        "product-service",
        DecisionAction.SCALE_UP,
        previous=1,
        requested=3,
    )

    with patch(
        "backend.scaling.actuator.subprocess.run",
        side_effect=mock_subprocess_run_factory(
            ps_output="id1\n",
            scale_fail_on_call=2,
        ),
    ):

        with pytest.raises(ScalingError) as exc:

            apply_decision(decision)

        assert (
            "rollback failed"
            in str(exc.value).lower()
        )


# ---------------------------------------------------------
# 5. UNHEALTHY REPLICA
# ---------------------------------------------------------

def test_unhealthy_replica(monkeypatch):

    enable_fast_health_verification(monkeypatch)

    decision = make_decision(
        "product-service",
        DecisionAction.SCALE_UP,
        previous=1,
        requested=2,
    )

    with patch(
        "backend.scaling.actuator.subprocess.run",
        side_effect=mock_subprocess_run_factory(
            ps_outputs=[
                "id1\nid2\n",
                "id1\nid2\n",
                "id1\n",
            ],
            inspect_running="true",
            inspect_health="unhealthy",
        ),
    ):

        with pytest.raises(ScalingError) as exc:

            apply_decision(decision)

        assert (
            "health verification"
            in str(exc.value).lower()
        )


# ---------------------------------------------------------
# 6. STARTING REPLICA TIMEOUT
# ---------------------------------------------------------

def test_starting_replica_timeout(monkeypatch):

    enable_fast_health_verification(monkeypatch)

    decision = make_decision(
        "product-service",
        DecisionAction.SCALE_UP,
        previous=1,
        requested=2,
    )

    with patch(
        "backend.scaling.actuator.subprocess.run",
        side_effect=mock_subprocess_run_factory(
            ps_outputs=[
                "id1\nid2\n",
                "id1\nid2\n",
                "id1\n",
            ],
            inspect_running="true",
            inspect_health="starting",
        ),
    ):

        with pytest.raises(ScalingError) as exc:

            apply_decision(decision)

        assert (
            "health verification"
            in str(exc.value).lower()
        )


# ---------------------------------------------------------
# 7. NO HEALTHCHECK DEFINED
# ---------------------------------------------------------

def test_no_health_check_defined(monkeypatch):

    monkeypatch.setattr(
        act,
        "_service_has_health_check",
        lambda service_name: False,
    )

    decision = make_decision(
        "product-service",
        DecisionAction.SCALE_UP,
        previous=1,
        requested=2,
    )

    with patch(
        "backend.scaling.actuator.subprocess.run",
        side_effect=mock_subprocess_run_factory(
            ps_outputs=[
                "id1\nid2\n",
                "id1\n",
            ],
            inspect_running="true",
        ),
    ):

        with pytest.raises(ScalingError) as exc:

            apply_decision(decision)

        assert (
            "no healthcheck"
            in str(exc.value).lower()
        )


# ---------------------------------------------------------
# 8. DOCKER PS COMMAND FAILURE
# ---------------------------------------------------------

def test_ps_command_failure():

    decision = make_decision(
        "product-service",
        DecisionAction.SCALE_UP,
        previous=1,
        requested=2,
    )

    with patch(
        "backend.scaling.actuator.subprocess.run",
        side_effect=mock_subprocess_run_factory(
            ps_error=True,
        ),
    ):

        with pytest.raises(ScalingError) as exc:

            apply_decision(decision)

        assert (
            "docker compose ps error"
            in str(exc.value).lower()
        )


# ---------------------------------------------------------
# 9. DOCKER SCALING COMMAND FAILURE
# ---------------------------------------------------------

def test_scaling_command_failure():

    decision = make_decision(
        "product-service",
        DecisionAction.SCALE_UP,
        previous=1,
        requested=2,
    )

    with patch(
        "backend.scaling.actuator.subprocess.run",
        side_effect=mock_subprocess_run_factory(
            scale_error=True,
        ),
    ):

        with pytest.raises(ScalingError) as exc:

            apply_decision(decision)

        assert (
            "docker compose scaling failed"
            in str(exc.value).lower()
        )


# ---------------------------------------------------------
# 10. SCALING DISABLED
# ---------------------------------------------------------

def test_scaling_disabled(monkeypatch):

    monkeypatch.setattr(
        cfg,
        "SCALING_ENABLED",
        False,
    )

    decision = make_decision(
        "product-service",
        DecisionAction.SCALE_UP,
        previous=1,
        requested=2,
    )

    with pytest.raises(ScalingError) as exc:

        apply_decision(decision)

    assert (
        "live scaling is disabled"
        in str(exc.value).lower()
    )


# ---------------------------------------------------------
# 11. SERVICE NOT IN ALLOWLIST
# ---------------------------------------------------------

def test_not_in_allowlist(monkeypatch):

    monkeypatch.setattr(
        cfg,
        "SCALING_ENABLED",
        True,
    )

    monkeypatch.setattr(
        cfg,
        "SCALING_ALLOWLIST",
        ["other-service"],
    )

    decision = make_decision(
        "product-service",
        DecisionAction.SCALE_UP,
        previous=1,
        requested=2,
    )

    with pytest.raises(ScalingError) as exc:

        apply_decision(decision)

    assert (
        "not in the scaling allowlist"
        in str(exc.value).lower()
    )


# ---------------------------------------------------------
# 12. HOST PORT MAPPING REJECTION
# ---------------------------------------------------------

def test_host_port_rejection(monkeypatch):

    monkeypatch.setattr(
        act,
        "_service_has_host_port",
        lambda name: True,
    )

    decision = make_decision(
        "product-service",
        DecisionAction.SCALE_UP,
        previous=1,
        requested=2,
    )

    with pytest.raises(ScalingError) as exc:

        apply_decision(decision)

    assert (
        "defines a host-port mapping"
        in str(exc.value).lower()
    )


# ---------------------------------------------------------
# 13. MINIMUM AND MAXIMUM REPLICA LIMITS
# ---------------------------------------------------------

def test_replica_limits(monkeypatch):

    test_config = ScalingConfig(
        min_replicas=2,
        max_replicas=5,
        max_replica_change=2,
    )

    # Patch the symbol imported by actuator.py.
    monkeypatch.setattr(
        act,
        "ScalingConfig",
        lambda: test_config,
    )

    # Requested replicas below minimum.
    decision_below = make_decision(
        "product-service",
        DecisionAction.SCALE_DOWN,
        previous=2,
        requested=1,
    )

    with pytest.raises(ScalingError) as exc:

        apply_decision(decision_below)

    assert (
        "out of allowed range"
        in str(exc.value).lower()
    )

    # Requested replicas above maximum.
    decision_above = make_decision(
        "product-service",
        DecisionAction.SCALE_UP,
        previous=2,
        requested=6,
    )

    with pytest.raises(ScalingError) as exc2:

        apply_decision(decision_above)

    assert (
        "out of allowed range"
        in str(exc2.value).lower()
    )


# ---------------------------------------------------------
# 14. MAXIMUM REPLICA CHANGE LIMIT
# ---------------------------------------------------------

def test_max_change_limit(monkeypatch):

    test_config = ScalingConfig(
        min_replicas=1,
        max_replicas=10,
        max_replica_change=1,
    )

    monkeypatch.setattr(
        act,
        "ScalingConfig",
        lambda: test_config,
    )

    decision = make_decision(
        "product-service",
        DecisionAction.SCALE_UP,
        previous=1,
        requested=3,
    )

    with pytest.raises(ScalingError) as exc:

        apply_decision(decision)

    assert (
        "replica change exceeds max allowed"
        in str(exc.value).lower()
    )


# ---------------------------------------------------------
# 15. REPLICA VERIFICATION TIMEOUT
# ---------------------------------------------------------

def test_replica_verification_timeout():

    decision = make_decision(
        "product-service",
        DecisionAction.SCALE_UP,
        previous=1,
        requested=2,
    )

    with patch(
        "backend.scaling.actuator.subprocess.run",
        side_effect=mock_subprocess_run_factory(
            ps_output="id1\n",
        ),
    ):

        with pytest.raises(ScalingError) as exc:

            apply_decision(decision)

        assert (
            "replica count verification failed"
            in str(exc.value).lower()
        )


# ---------------------------------------------------------
# 16. NO SCALING INVOCATION AFTER PREFLIGHT FAILURE
# ---------------------------------------------------------

def test_no_scaling_invocation_on_preflight_failure(monkeypatch):

    monkeypatch.setattr(
        cfg,
        "SCALING_ALLOWLIST",
        [],
    )

    decision = make_decision(
        "product-service",
        DecisionAction.SCALE_UP,
        previous=1,
        requested=2,
    )

    with patch(
        "backend.scaling.actuator.subprocess.run"
    ) as mock_run:

        with pytest.raises(ScalingError):

            apply_decision(decision)

        # No Docker command should execute.
        mock_run.assert_not_called()