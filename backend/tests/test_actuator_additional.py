import pytest

import backend.config as cfg
import backend.scaling.actuator as actuator

from backend.scaling.actuator import apply_decision, ScalingError
from backend.scaling.models import DecisionOutput, DecisionAction


def make_decision(
    service_name="product-service",
    action=DecisionAction.SCALE_UP,
    previous=1,
    requested=2,
):
    return DecisionOutput(
        service_name=service_name,
        action=action,
        previous_replicas=previous,
        requested_replicas=requested,
        phase="NORMAL_OPERATION",
        bottleneck=None,
        reason="Additional actuator safety test",
        simulated=False,
    )


def configure_scaling(monkeypatch):
    monkeypatch.setattr(cfg, "SCALING_ENABLED", True)
    monkeypatch.setattr(
        cfg,
        "SCALING_ALLOWLIST",
        ["product-service"],
    )


def test_replica_verification_mismatch(monkeypatch):
    monkeypatch.setattr(
        actuator,
        "get_replica_count",
        lambda service_name: 1,
    )

    with pytest.raises(ScalingError) as exc:
        actuator._verify_replica_count(
            service_name="product-service",
            expected=2,
            timeout=0,
            interval=0,
        )

    assert "replica count verification failed" in str(
        exc.value
    ).lower()


def test_no_health_check_after_scale(monkeypatch):
    configure_scaling(monkeypatch)

    decision = make_decision()
    scaling_calls = []

    def fake_scale(service_name, replicas):
        scaling_calls.append((service_name, replicas))

    monkeypatch.setattr(
        actuator,
        "_run_docker_compose",
        fake_scale,
    )

    monkeypatch.setattr(
        actuator,
        "_verify_replica_count",
        lambda service_name, expected, **kwargs: None,
    )

    monkeypatch.setattr(
        actuator,
        "_service_has_health_check",
        lambda service_name: False,
    )

    with pytest.raises(ScalingError) as exc:
        apply_decision(decision)

    assert "no healthcheck is defined" in str(
        exc.value
    ).lower()

    assert scaling_calls == [
        ("product-service", 2),
        ("product-service", 1),
    ]