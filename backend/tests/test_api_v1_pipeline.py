"""
Automated tests for DPBPS v1 API endpoints and pipeline integration.

Verifies:
1. System health endpoint with Kubernetes and Prometheus status.
2. Services inventory with live telemetry and health status.
3. Deployments endpoint with replica and rollout status.
4. Overview metrics aggregation across microservices.
5. Kubernetes telemetry and completeness summary endpoints.
6. End-to-end DPBPS pipeline evaluation (GET and POST /api/v1/dpbps/pipeline/evaluate).
7. Incomplete telemetry handling in pipeline (excluded services flagged safely).
8. Actuator execution history endpoint.
9. Deployment phase transition propagation across pipeline.
10. Error handling on Kubernetes adapter failure.
11. Validation error handling on invalid requests.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.api.v1_router import (
    set_telemetry_adapter,
    set_kubernetes_actuator,
    shared_state_manager,
    dpbps_controller,
)
from backend.scaling.models import (
    DecisionAction,
    DeploymentPhase,
    TelemetryInput,
)
from backend.scaling.kubernetes.telemetry_adapter import KubernetesTelemetryAdapter
from backend.scaling.kubernetes.actuator import (
    KubernetesScalingActuator,
    KubernetesScalingResult,
    ScalingExecutionStatus,
)

client = TestClient(app)


# ---------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------

@pytest.fixture(autouse=True)
def setup_mock_pipeline(monkeypatch):
    """Set up mock adapter and actuator for fast, deterministic API testing."""
    # Reset phase
    shared_state_manager.set_phase(DeploymentPhase.NORMAL_OPERATION)

    # Mock adapter
    mock_adapter = MagicMock(spec=KubernetesTelemetryAdapter)
    mock_adapter.namespace = "online-boutique"

    raw_telemetry = [
        {
            "service_name": "frontend",
            "namespace": "online-boutique",
            "desired_replicas": 1,
            "ready_replicas": 1,
            "observed_pods": 1,
            "cpu_usage_millicores": 25.0,
            "memory_usage_mib": 50.0,
            "cpu_request_millicores": 100.0,
            "memory_request_mib": 100.0,
            "cpu_utilisation": 0.25,
            "memory_utilisation": 0.50,
            "cpu_utilization_percent": 25.0,
            "memory_utilization_percent": 50.0,
            "timestamp": "2026-11-09T10:00:00Z",
            "telemetry_available": True,
            "request_rate": 20.0,
            "p95_latency_ms": 40.0,
            "error_rate": 0.0,
            "dependencies": ["cartservice", "checkoutservice"],
            "deployment_phase": "NORMAL_OPERATION",
            "missing_metrics": [],
            "diagnostics": [],
        },
        {
            "service_name": "cartservice",
            "namespace": "online-boutique",
            "desired_replicas": 1,
            "ready_replicas": 1,
            "observed_pods": 1,
            "cpu_usage_millicores": 15.0,
            "memory_usage_mib": 60.0,
            "cpu_request_millicores": 200.0,
            "memory_request_mib": 100.0,
            "cpu_utilisation": 0.075,
            "memory_utilisation": 0.60,
            "cpu_utilization_percent": 7.5,
            "memory_utilization_percent": 60.0,
            "timestamp": "2026-11-09T10:00:00Z",
            "telemetry_available": True,
            "request_rate": 15.0,
            "p95_latency_ms": 10.0,
            "error_rate": 0.0,
            "dependencies": ["redis-cart"],
            "deployment_phase": "NORMAL_OPERATION",
            "missing_metrics": [],
            "diagnostics": [],
        },
        {
            "service_name": "redis-cart",
            "namespace": "online-boutique",
            "desired_replicas": 1,
            "ready_replicas": 1,
            "observed_pods": 1,
            "cpu_usage_millicores": 5.0,
            "memory_usage_mib": 20.0,
            "cpu_request_millicores": 50.0,
            "memory_request_mib": 50.0,
            "cpu_utilisation": 0.1,
            "memory_utilisation": 0.4,
            "cpu_utilization_percent": 10.0,
            "memory_utilization_percent": 40.0,
            "timestamp": "2026-11-09T10:00:00Z",
            "telemetry_available": False,
            "request_rate": None,
            "p95_latency_ms": None,
            "error_rate": None,
            "dependencies": [],
            "deployment_phase": "NORMAL_OPERATION",
            "missing_metrics": ["error_rate", "p95_latency", "request_rate"],
            "diagnostics": ["Uninstrumented cache"],
        },
    ]

    mock_adapter.collect_deployment_telemetry.return_value = raw_telemetry

    valid_inputs = [
        TelemetryInput(
            service_name="frontend",
            request_rate=20.0,
            p95_latency=40.0,
            error_rate=0.0,
            cpu_utilisation=0.25,
            memory_utilisation=0.50,
            current_replicas=1,
            ready_replicas=1,
            timestamp=datetime.now(timezone.utc),
            dependencies=["cartservice", "checkoutservice"],
        ),
        TelemetryInput(
            service_name="cartservice",
            request_rate=15.0,
            p95_latency=10.0,
            error_rate=0.0,
            cpu_utilisation=0.075,
            memory_utilisation=0.60,
            current_replicas=1,
            ready_replicas=1,
            timestamp=datetime.now(timezone.utc),
            dependencies=["redis-cart"],
        ),
    ]
    excluded = [raw_telemetry[2]]
    mock_adapter.get_telemetry_inputs.return_value = (valid_inputs, excluded)

    mock_adapter.get_telemetry_summary.return_value = {
        "namespace": "online-boutique",
        "deployment_count": 3,
        "complete_telemetry_count": 2,
        "incomplete_telemetry_count": 1,
        "application_metrics_integrated": True,
        "deployment_phase": "NORMAL_OPERATION",
        "deployments": raw_telemetry,
    }

    set_telemetry_adapter(mock_adapter)

    # Mock actuator
    mock_actuator = MagicMock(spec=KubernetesScalingActuator)
    mock_actuator.dry_run = True
    mock_actuator.namespace = "online-boutique"

    def execute_decisions_side_effect(decisions):
        results = []
        for d in decisions:
            results.append(KubernetesScalingResult(
                service_name=d.service_name,
                namespace="online-boutique",
                current_replicas=d.previous_replicas,
                requested_replicas=d.requested_replicas,
                action=d.action,
                execution_mode="DRY_RUN",
                status=ScalingExecutionStatus.SKIPPED if d.action == DecisionAction.HOLD else ScalingExecutionStatus.VALIDATED,
                cluster_modified=False,
                reason=f"Dry-run executed for {d.service_name}",
                deployment_phase=d.phase,
            ))
        return results

    mock_actuator.execute_decisions.side_effect = execute_decisions_side_effect
    set_kubernetes_actuator(mock_actuator)


# ---------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------

def test_health_endpoint():
    """Verify health endpoint returns status, connectivity and safety flags."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "dpbps-backend"
    assert "kubernetes_connected" in data
    assert "prometheus_connected" in data
    assert data["dry_run"] is True
    assert data["scaling_enabled"] is False


def test_services_endpoint():
    """Verify /api/v1/services returns live service health, replicas and utilization."""
    resp = client.get("/api/v1/services")
    assert resp.status_code == 200
    services = resp.json()
    assert len(services) == 3

    svc_names = {s["name"] for s in services}
    assert "frontend" in svc_names
    assert "cartservice" in svc_names

    frontend = next(s for s in services if s["name"] == "frontend")
    assert frontend["health"] == "HEALTHY"
    assert frontend["cpu_utilisation"] == 0.25
    assert frontend["memory_utilisation"] == 0.50
    assert frontend["ready_replicas"] == 1
    assert frontend["request_rate"] == 20.0
    assert frontend["p95_latency"] == 40.0
    assert frontend["telemetry_available"] is True


def test_deployments_endpoint():
    """Verify /api/v1/deployments lists deployment status and phases."""
    resp = client.get("/api/v1/deployments")
    assert resp.status_code == 200
    deps = resp.json()
    assert len(deps) == 3
    d_map = {d["id"]: d for d in deps}
    assert d_map["frontend"]["status"] == "READY"
    assert d_map["frontend"]["phase"] == "NORMAL_OPERATION"


def test_overview_metrics_endpoint():
    """Verify /api/v1/metrics/overview calculates system-level aggregate metrics."""
    resp = client.get("/api/v1/metrics/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert "metrics" in data
    metrics_by_name = {m["name"]: m for m in data["metrics"]}

    assert "request_rate" in metrics_by_name
    assert metrics_by_name["request_rate"]["value"] == 35.0  # 20.0 + 15.0
    assert metrics_by_name["request_rate"]["unit"] == "req/s"

    assert "p95_latency" in metrics_by_name
    assert metrics_by_name["p95_latency"]["value"] == 25.0  # (40 + 10) / 2

    assert "ready_replicas" in metrics_by_name
    assert metrics_by_name["ready_replicas"]["value"] == 3.0  # 1 + 1 + 1


def test_kubernetes_telemetry_endpoints():
    """Verify direct Kubernetes telemetry collection and summary endpoints."""
    resp_raw = client.get("/api/v1/kubernetes/telemetry")
    assert resp_raw.status_code == 200
    assert len(resp_raw.json()) == 3

    resp_summary = client.get("/api/v1/kubernetes/telemetry/summary")
    assert resp_summary.status_code == 200
    summary = resp_summary.json()
    assert summary["deployment_count"] == 3
    assert summary["complete_telemetry_count"] == 2
    assert summary["incomplete_telemetry_count"] == 1


def test_pipeline_evaluation_get_and_post():
    """Verify consolidated DPBPS pipeline evaluation via GET and POST."""
    for method in ["get", "post"]:
        func = getattr(client, method)
        resp = func("/api/v1/dpbps/pipeline/evaluate")
        assert resp.status_code == 200
        data = resp.json()

        assert data["execution_mode"] == "DRY_RUN"
        assert data["cluster_modified"] is False
        assert data["total_services"] == 3
        assert data["complete_telemetry_services"] == 2
        assert data["incomplete_telemetry_services"] == 1
        assert "services" in data

        svc_map = {s["service_name"]: s for s in data["services"]}

        # 1. Complete service (frontend)
        fe = svc_map["frontend"]
        assert fe["telemetry_complete"] is True
        assert fe["current_replicas"] == 1
        assert fe["proposed_replica_count"] == 1
        assert fe["dpbps_decision"] == "HOLD"
        assert fe["actuator_execution_status"] == "SKIPPED"
        assert fe["cluster_modified"] is False
        assert fe["request_rate"] == 20.0
        assert fe["p95_latency"] == 40.0
        assert fe["cpu_utilization"] == 0.25

        # 2. Incomplete service (redis-cart)
        redis = svc_map["redis-cart"]
        assert redis["telemetry_complete"] is False
        assert redis["dpbps_decision"] == "EXCLUDED"
        assert redis["actuator_execution_status"] == "SKIPPED"
        assert redis["proposed_replica_count"] == 1
        assert "missing metrics" in redis["reason"]


def test_actuator_history_endpoint():
    """Verify that actuator execution records can be queried."""
    # First trigger pipeline to generate records
    client.post("/api/v1/dpbps/pipeline/evaluate")

    resp = client.get("/api/v1/scaling/actuator/history")
    assert resp.status_code == 200
    history = resp.json()
    assert isinstance(history, list)
    assert len(history) > 0
    assert history[0]["execution_mode"] == "DRY_RUN"


def test_deployment_phase_propagation():
    """Verify changing deployment phase propagates into pipeline evaluation."""
    # Set phase to PRE_DEPLOYMENT
    set_resp = client.post("/api/v1/scaling/deployment-phase", json={"phase": "PRE_DEPLOYMENT"})
    assert set_resp.status_code == 200
    assert set_resp.json()["phase"] == "PRE_DEPLOYMENT"

    # Verify pipeline reports updated phase
    pipe_resp = client.get("/api/v1/dpbps/pipeline/evaluate")
    assert pipe_resp.status_code == 200
    data = pipe_resp.json()
    assert data["deployment_phase"] == "PRE_DEPLOYMENT"
    for s in data["services"]:
        assert s["deployment_phase"] == "PRE_DEPLOYMENT"


def test_invalid_deployment_phase_rejected():
    """Verify invalid deployment phase string is rejected with 422."""
    resp = client.post("/api/v1/scaling/deployment-phase", json={"phase": "INVALID_PHASE"})
    assert resp.status_code == 422


def test_pipeline_kubernetes_adapter_failure_handled():
    """Verify that an unexpected exception in adapter returns 500 without crashing backend."""
    failing_adapter = MagicMock()
    failing_adapter.get_telemetry_inputs.side_effect = RuntimeError("Kubernetes API Server Down")
    set_telemetry_adapter(failing_adapter)

    resp = client.get("/api/v1/dpbps/pipeline/evaluate")
    assert resp.status_code == 500
    assert "Telemetry collection failed" in resp.json()["detail"]

