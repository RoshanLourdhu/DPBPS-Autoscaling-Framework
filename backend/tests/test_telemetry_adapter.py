"""
Automated unit tests for DPBPS KubernetesTelemetryAdapter.

Verifies:
1. Adapter initialization (default and custom dependency maps, state managers, APIs).
2. Prometheus integration (retrieval of request_rate, p95_latency_ms, error_rate).
3. Full telemetry collection across infrastructure and application metrics.
4. CPU utilization normalization to fractions [0.0, 1.0].
5. Memory utilization normalization to fractions [0.0, 1.0].
6. Handling of resource usage exceeding resource requests (clamping fraction at 1.0, uncapped ratio preserved).
7. Missing Prometheus metrics handling (excluded from TelemetryInput, missing_metrics flag).
8. Missing CPU and memory metrics handling from Metrics Server.
9. Stale telemetry handling (excluded from TelemetryInput).
10. Kubernetes API failure handling (graceful per-service error handling).
11. Metrics Server failure handling.
12. Zero desired replicas handling (e.g. loadgenerator excluded from active scaling).
13. Multiple replicas scaling and request aggregation.
14. Not-ready replicas detection and incomplete measurement handling.
15. Dependency graph population matching Online Boutique topology.
16. Deployment-phase awareness and propagation (all 4 phases).
17. Multi-service batch telemetry collection.
18. Incomplete telemetry safety (strict schema validation, zero-fabrication prevention).
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest

from backend.scaling.models import (
    DeploymentPhase,
    TelemetryInput,
)
from backend.scaling.deployment_state import DeploymentStateManager
from backend.scaling.kubernetes.telemetry_adapter import (
    KubernetesTelemetryAdapter,
    ONLINE_BOUTIQUE_DEPENDENCIES,
)
from backend.scaling.kubernetes.prometheus_client import ServiceTelemetryResult


# ---------------------------------------------------------------------
# FIXTURES AND TEST HELPERS
# ---------------------------------------------------------------------

def create_mock_container(name: str, cpu_req: str = "100m", mem_req: str = "100Mi") -> MagicMock:
    """Create a mock container with resource requests."""
    container = MagicMock()
    container.name = name
    container.resources.requests = {"cpu": cpu_req, "memory": mem_req}
    return container


def create_mock_deployment(name: str, cpu_req: str = "100m", mem_req: str = "100Mi") -> MagicMock:
    """Create a mock Kubernetes Deployment API object."""
    dep = MagicMock()
    dep.metadata.name = name
    container = create_mock_container(name, cpu_req, mem_req)
    dep.spec.template.spec.containers = [container]
    return dep


def make_adapter_with_mocks(
    deployments: list,
    pods: list,
    pod_metrics: list,
    deployment_objects: dict,
    prom_results: dict,
    phase: DeploymentPhase = DeploymentPhase.NORMAL_OPERATION,
) -> KubernetesTelemetryAdapter:
    """Assemble a KubernetesTelemetryAdapter with mocked subcomponents."""
    mock_cluster_manager = MagicMock()
    mock_cluster_manager.get_deployments.return_value = deployments
    mock_cluster_manager.get_pod_health.return_value = pods

    mock_metrics_collector = MagicMock()
    mock_metrics_collector.get_pod_metrics.return_value = pod_metrics

    mock_apps_api = MagicMock()
    def read_deployment_side_effect(name, namespace):
        if name in deployment_objects:
            return deployment_objects[name]
        raise ValueError(f"Deployment {name} not found")
    mock_apps_api.read_namespaced_deployment.side_effect = read_deployment_side_effect

    mock_prom_client = MagicMock()
    def get_prom_telemetry_side_effect(service_name, namespace="online-boutique", window="1m"):
        if service_name in prom_results:
            return prom_results[service_name]
        return ServiceTelemetryResult(
            service_name=service_name,
            request_rate=None,
            p95_latency_ms=None,
            error_rate=None,
            timestamp=datetime.now(timezone.utc),
            is_complete=False,
            missing_metrics=["request_rate", "p95_latency", "error_rate"],
        )
    mock_prom_client.get_service_telemetry.side_effect = get_prom_telemetry_side_effect

    state_manager = DeploymentStateManager()
    state_manager.set_phase(phase)

    adapter = KubernetesTelemetryAdapter(
        namespace="online-boutique",
        cluster_manager=mock_cluster_manager,
        metrics_collector=mock_metrics_collector,
        prometheus_client=mock_prom_client,
        state_manager=state_manager,
        apps_api=mock_apps_api,
    )
    return adapter


# ---------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------

def test_1_adapter_initialization():
    """Verify adapter initializes with custom and default parameters."""
    mock_cluster = MagicMock()
    mock_metrics = MagicMock()
    mock_prom = MagicMock()
    mock_state = DeploymentStateManager()
    mock_apps = MagicMock()

    custom_deps = {"service-a": ["service-b"]}

    adapter = KubernetesTelemetryAdapter(
        namespace="test-ns",
        cluster_manager=mock_cluster,
        metrics_collector=mock_metrics,
        prometheus_client=mock_prom,
        state_manager=mock_state,
        apps_api=mock_apps,
        dependency_map=custom_deps,
    )

    assert adapter.namespace == "test-ns"
    assert adapter.cluster_manager is mock_cluster
    assert adapter.metrics_collector is mock_metrics
    assert adapter.prometheus_client is mock_prom
    assert adapter.state_manager is mock_state
    assert adapter.apps_api is mock_apps
    assert adapter.dependency_map == custom_deps
    assert adapter.get_deployment_phase() == DeploymentPhase.NORMAL_OPERATION


def test_2_prometheus_integration():
    """Verify application metrics from PrometheusClient are integrated."""
    deployments = [{
        "name": "cartservice",
        "namespace": "online-boutique",
        "desired_replicas": 1,
        "ready_replicas": 1,
        "available_replicas": 1,
        "updated_replicas": 1,
        "generation": 1,
        "observed_generation": 1,
        "ready": True,
    }]
    pods = [{
        "name": "cartservice-5f778f-abcde",
        "namespace": "online-boutique",
        "phase": "Running",
        "ready": True,
        "containers_ready": True,
        "restart_count": 0,
    }]
    pod_metrics = [{
        "pod_name": "cartservice-5f778f-abcde",
        "namespace": "online-boutique",
        "cpu_millicores": 20.0,
        "memory_mib": 60.0,
        "timestamp": "2026-11-09T10:00:00Z",
    }]
    dep_objs = {"cartservice": create_mock_deployment("cartservice", "200m", "100Mi")}
    prom_results = {
        "cartservice": ServiceTelemetryResult(
            service_name="cartservice",
            request_rate=24.5,
            p95_latency_ms=12.4,
            error_rate=0.0,
            timestamp=datetime.now(timezone.utc),
            is_complete=True,
            missing_metrics=[],
            diagnostic_messages=[],
        )
    }

    adapter = make_adapter_with_mocks(deployments, pods, pod_metrics, dep_objs, prom_results)
    results = adapter.collect_deployment_telemetry()

    assert len(results) == 1
    item = results[0]
    assert item["service_name"] == "cartservice"
    assert item["request_rate"] == 24.5
    assert item["p95_latency_ms"] == 12.4
    assert item["error_rate"] == 0.0
    assert item["telemetry_available"] is True


def test_3_full_telemetry_collection():
    """Verify end-to-end telemetry collection populates all expected fields."""
    deployments = [{
        "name": "frontend",
        "namespace": "online-boutique",
        "desired_replicas": 1,
        "ready_replicas": 1,
        "available_replicas": 1,
        "updated_replicas": 1,
        "generation": 1,
        "observed_generation": 1,
        "ready": True,
    }]
    pods = [{
        "name": "frontend-6d58498-abcde",
        "namespace": "online-boutique",
        "phase": "Running",
        "ready": True,
        "containers_ready": True,
        "restart_count": 0,
    }]
    pod_metrics = [{
        "pod_name": "frontend-6d58498-abcde",
        "namespace": "online-boutique",
        "cpu_millicores": 50.0,
        "memory_mib": 80.0,
        "timestamp": "2026-11-09T10:00:00Z",
    }]
    dep_objs = {"frontend": create_mock_deployment("frontend", "100m", "100Mi")}
    prom_results = {
        "frontend": ServiceTelemetryResult(
            service_name="frontend",
            request_rate=30.0,
            p95_latency_ms=45.0,
            error_rate=0.005,
            timestamp=datetime.now(timezone.utc),
            is_complete=True,
            missing_metrics=[],
            diagnostic_messages=[],
        )
    }

    adapter = make_adapter_with_mocks(deployments, pods, pod_metrics, dep_objs, prom_results)
    results = adapter.collect_deployment_telemetry()
    assert len(results) == 1
    item = results[0]

    assert item["service_name"] == "frontend"
    assert item["namespace"] == "online-boutique"
    assert item["desired_replicas"] == 1
    assert item["ready_replicas"] == 1
    assert item["observed_pods"] == 1
    assert item["cpu_usage_millicores"] == 50.0
    assert item["memory_usage_mib"] == 80.0
    assert item["cpu_request_millicores"] == 100.0
    assert item["memory_request_mib"] == 100.0
    assert item["cpu_utilisation"] == 0.50
    assert item["memory_utilisation"] == 0.80
    assert item["cpu_utilization_ratio"] == 0.50
    assert item["memory_utilization_ratio"] == 0.80
    assert item["cpu_utilization_percent"] == 50.0
    assert item["memory_utilization_percent"] == 80.0
    assert item["request_rate"] == 30.0
    assert item["p95_latency_ms"] == 45.0
    assert item["error_rate"] == 0.005
    assert item["telemetry_available"] is True
    assert item["missing_metrics"] == []
    assert len(item["dependencies"]) == 7


def test_4_cpu_normalization():
    """Verify CPU normalization handles 0%, 25%, 50%, 100% ratios as fractions."""
    dep_objs = {"service": create_mock_deployment("service", "1000m", "1000Mi")}
    deployments = [{
        "name": "service",
        "namespace": "online-boutique",
        "desired_replicas": 1,
        "ready_replicas": 1,
        "available_replicas": 1,
        "updated_replicas": 1,
        "generation": 1,
        "observed_generation": 1,
        "ready": True,
    }]
    pods = [{
        "name": "service-xyz-123",
        "namespace": "online-boutique",
        "phase": "Running",
        "ready": True,
        "containers_ready": True,
        "restart_count": 0,
    }]
    prom_results = {
        "service": ServiceTelemetryResult(
            service_name="service",
            request_rate=10.0,
            p95_latency_ms=20.0,
            error_rate=0.0,
            timestamp=datetime.now(timezone.utc),
            is_complete=True,
            missing_metrics=[],
        )
    }

    test_cases = [
        (0.0, 0.0, 0.0),
        (250.0, 0.25, 25.0),
        (500.0, 0.50, 50.0),
        (1000.0, 1.0, 100.0),
    ]

    for millicores, expected_fraction, expected_percent in test_cases:
        pod_metrics = [{
            "pod_name": "service-xyz-123",
            "namespace": "online-boutique",
            "cpu_millicores": millicores,
            "memory_mib": 500.0,
            "timestamp": "2026-11-09T10:00:00Z",
        }]
        adapter = make_adapter_with_mocks(deployments, pods, pod_metrics, dep_objs, prom_results)
        res = adapter.collect_deployment_telemetry()[0]
        assert res["cpu_utilisation"] == expected_fraction
        assert res["cpu_utilization_ratio"] == expected_fraction
        assert res["cpu_utilization_percent"] == expected_percent


def test_5_memory_normalization():
    """Verify Memory normalization handles 0%, 25%, 50%, 100% ratios as fractions."""
    dep_objs = {"service": create_mock_deployment("service", "500m", "400Mi")}
    deployments = [{
        "name": "service",
        "namespace": "online-boutique",
        "desired_replicas": 1,
        "ready_replicas": 1,
        "available_replicas": 1,
        "updated_replicas": 1,
        "generation": 1,
        "observed_generation": 1,
        "ready": True,
    }]
    pods = [{
        "name": "service-xyz-123",
        "namespace": "online-boutique",
        "phase": "Running",
        "ready": True,
        "containers_ready": True,
        "restart_count": 0,
    }]
    prom_results = {
        "service": ServiceTelemetryResult(
            service_name="service",
            request_rate=10.0,
            p95_latency_ms=20.0,
            error_rate=0.0,
            timestamp=datetime.now(timezone.utc),
            is_complete=True,
            missing_metrics=[],
        )
    }

    test_cases = [
        (0.0, 0.0, 0.0),
        (100.0, 0.25, 25.0),
        (200.0, 0.50, 50.0),
        (400.0, 1.0, 100.0),
    ]

    for mib, expected_fraction, expected_percent in test_cases:
        pod_metrics = [{
            "pod_name": "service-xyz-123",
            "namespace": "online-boutique",
            "cpu_millicores": 250.0,
            "memory_mib": mib,
            "timestamp": "2026-11-09T10:00:00Z",
        }]
        adapter = make_adapter_with_mocks(deployments, pods, pod_metrics, dep_objs, prom_results)
        res = adapter.collect_deployment_telemetry()[0]
        assert res["memory_utilisation"] == expected_fraction
        assert res["memory_utilization_ratio"] == expected_fraction
        assert res["memory_utilization_percent"] == expected_percent


def test_6_usage_exceeding_resource_requests():
    """Verify usage exceeding requests clamps fraction to 1.0 and preserves uncapped ratio."""
    dep_objs = {"service": create_mock_deployment("service", "200m", "100Mi")}
    deployments = [{
        "name": "service",
        "namespace": "online-boutique",
        "desired_replicas": 1,
        "ready_replicas": 1,
        "available_replicas": 1,
        "updated_replicas": 1,
        "generation": 1,
        "observed_generation": 1,
        "ready": True,
    }]
    pods = [{
        "name": "service-xyz-123",
        "namespace": "online-boutique",
        "phase": "Running",
        "ready": True,
        "containers_ready": True,
        "restart_count": 0,
    }]
    # Pod usage exceeds request: 300m CPU (150%) and 150Mi Memory (150%)
    pod_metrics = [{
        "pod_name": "service-xyz-123",
        "namespace": "online-boutique",
        "cpu_millicores": 300.0,
        "memory_mib": 150.0,
        "timestamp": "2026-11-09T10:00:00Z",
    }]
    prom_results = {
        "service": ServiceTelemetryResult(
            service_name="service",
            request_rate=50.0,
            p95_latency_ms=120.0,
            error_rate=0.0,
            timestamp=datetime.now(timezone.utc),
            is_complete=True,
            missing_metrics=[],
        )
    }

    adapter = make_adapter_with_mocks(deployments, pods, pod_metrics, dep_objs, prom_results)
    results = adapter.collect_deployment_telemetry()
    res = results[0]

    # Model constraints: clamped to 1.0
    assert res["cpu_utilisation"] == 1.0
    assert res["memory_utilisation"] == 1.0

    # Uncapped metrics preserved
    assert res["cpu_utilization_ratio"] == 1.5
    assert res["memory_utilization_ratio"] == 1.5
    assert res["cpu_utilization_percent"] == 150.0
    assert res["memory_utilization_percent"] == 150.0

    # Diagnostic note added
    assert any("exceeds requested capacity" in d for d in res["diagnostics"])

    # Generates a valid TelemetryInput without raising validation error
    valid_inputs, excluded = adapter.get_telemetry_inputs()
    assert len(valid_inputs) == 1
    assert len(excluded) == 0
    t_in = valid_inputs[0]
    assert t_in.cpu_utilisation == 1.0
    assert t_in.memory_utilisation == 1.0


def test_7_missing_prometheus_metrics():
    """Verify service with missing Prometheus metrics is marked unavailable and excluded."""
    dep_objs = {"service": create_mock_deployment("service", "100m", "100Mi")}
    deployments = [{
        "name": "service",
        "namespace": "online-boutique",
        "desired_replicas": 1,
        "ready_replicas": 1,
        "available_replicas": 1,
        "updated_replicas": 1,
        "generation": 1,
        "observed_generation": 1,
        "ready": True,
    }]
    pods = [{
        "name": "service-xyz-123",
        "namespace": "online-boutique",
        "phase": "Running",
        "ready": True,
        "containers_ready": True,
        "restart_count": 0,
    }]
    pod_metrics = [{
        "pod_name": "service-xyz-123",
        "namespace": "online-boutique",
        "cpu_millicores": 20.0,
        "memory_mib": 30.0,
        "timestamp": "2026-11-09T10:00:00Z",
    }]
    prom_results = {
        "service": ServiceTelemetryResult(
            service_name="service",
            request_rate=None,  # Missing!
            p95_latency_ms=None,
            error_rate=None,
            timestamp=datetime.now(timezone.utc),
            is_complete=False,
            missing_metrics=["request_rate", "p95_latency", "error_rate"],
        )
    }

    adapter = make_adapter_with_mocks(deployments, pods, pod_metrics, dep_objs, prom_results)
    results = adapter.collect_deployment_telemetry()
    res = results[0]

    assert res["telemetry_available"] is False
    assert "request_rate" in res["missing_metrics"]
    assert res["request_rate"] is None

    valid_inputs, excluded = adapter.get_telemetry_inputs()
    assert len(valid_inputs) == 0
    assert len(excluded) == 1
    assert excluded[0]["service_name"] == "service"


def test_8_missing_cpu_and_memory_metrics():
    """Verify service with missing pod metrics is marked unavailable and excluded."""
    dep_objs = {"service": create_mock_deployment("service", "100m", "100Mi")}
    deployments = [{
        "name": "service",
        "namespace": "online-boutique",
        "desired_replicas": 1,
        "ready_replicas": 1,
        "available_replicas": 1,
        "updated_replicas": 1,
        "generation": 1,
        "observed_generation": 1,
        "ready": True,
    }]
    pods = [{
        "name": "service-xyz-123",
        "namespace": "online-boutique",
        "phase": "Running",
        "ready": True,
        "containers_ready": True,
        "restart_count": 0,
    }]
    # Pod has no Metrics Server measurements
    pod_metrics = []
    prom_results = {
        "service": ServiceTelemetryResult(
            service_name="service",
            request_rate=15.0,
            p95_latency_ms=25.0,
            error_rate=0.0,
            timestamp=datetime.now(timezone.utc),
            is_complete=True,
            missing_metrics=[],
        )
    }

    adapter = make_adapter_with_mocks(deployments, pods, pod_metrics, dep_objs, prom_results)
    results = adapter.collect_deployment_telemetry()
    res = results[0]

    assert res["telemetry_available"] is False
    assert "complete_resource_measurements" in res["missing_metrics"]
    assert res["cpu_utilisation"] is None
    assert res["memory_utilisation"] is None

    valid_inputs, excluded = adapter.get_telemetry_inputs()
    assert len(valid_inputs) == 0
    assert len(excluded) == 1


def test_9_stale_telemetry():
    """Verify stale application telemetry is flagged and excluded."""
    dep_objs = {"service": create_mock_deployment("service", "100m", "100Mi")}
    deployments = [{
        "name": "service",
        "namespace": "online-boutique",
        "desired_replicas": 1,
        "ready_replicas": 1,
        "available_replicas": 1,
        "updated_replicas": 1,
        "generation": 1,
        "observed_generation": 1,
        "ready": True,
    }]
    pods = [{
        "name": "service-xyz-123",
        "namespace": "online-boutique",
        "phase": "Running",
        "ready": True,
        "containers_ready": True,
        "restart_count": 0,
    }]
    pod_metrics = [{
        "pod_name": "service-xyz-123",
        "namespace": "online-boutique",
        "cpu_millicores": 20.0,
        "memory_mib": 30.0,
        "timestamp": "2026-11-09T10:00:00Z",
    }]
    # Prometheus client marked telemetry stale (is_complete=False)
    prom_results = {
        "service": ServiceTelemetryResult(
            service_name="service",
            request_rate=None,
            p95_latency_ms=None,
            error_rate=None,
            timestamp=datetime.now(timezone.utc),
            is_complete=False,
            missing_metrics=["request_rate", "p95_latency"],
            diagnostic_messages=["Request rate is stale (exceeds max_age_seconds)."],
        )
    }

    adapter = make_adapter_with_mocks(deployments, pods, pod_metrics, dep_objs, prom_results)
    results = adapter.collect_deployment_telemetry()
    res = results[0]

    assert res["telemetry_available"] is False
    assert "request_rate" in res["missing_metrics"]

    valid_inputs, excluded = adapter.get_telemetry_inputs()
    assert len(valid_inputs) == 0
    assert len(excluded) == 1


def test_10_kubernetes_api_failures():
    """Verify Kubernetes API exceptions when reading deployment spec are handled gracefully."""
    deployments = [{
        "name": "failing-service",
        "namespace": "online-boutique",
        "desired_replicas": 1,
        "ready_replicas": 1,
        "available_replicas": 1,
        "updated_replicas": 1,
        "generation": 1,
        "observed_generation": 1,
        "ready": True,
    }]
    pods = [{
        "name": "failing-service-xyz-123",
        "namespace": "online-boutique",
        "phase": "Running",
        "ready": True,
        "containers_ready": True,
        "restart_count": 0,
    }]
    pod_metrics = [{
        "pod_name": "failing-service-xyz-123",
        "namespace": "online-boutique",
        "cpu_millicores": 20.0,
        "memory_mib": 30.0,
        "timestamp": "2026-11-09T10:00:00Z",
    }]
    # Empty deployment_objects forces ValueError in read_namespaced_deployment
    dep_objs = {}
    prom_results = {
        "failing-service": ServiceTelemetryResult(
            service_name="failing-service",
            request_rate=10.0,
            p95_latency_ms=20.0,
            error_rate=0.0,
            timestamp=datetime.now(timezone.utc),
            is_complete=True,
            missing_metrics=[],
        )
    }

    adapter = make_adapter_with_mocks(deployments, pods, pod_metrics, dep_objs, prom_results)
    # Must not raise unhandled exception
    results = adapter.collect_deployment_telemetry()
    res = results[0]

    assert res["telemetry_available"] is False
    assert "resource_requests" in res["missing_metrics"]
    assert any("Failed to retrieve resource requests" in d for d in res["diagnostics"])


def test_11_metrics_server_failures():
    """Verify empty pod metrics from Metrics Server are handled gracefully."""
    dep_objs = {"service": create_mock_deployment("service", "100m", "100Mi")}
    deployments = [{
        "name": "service",
        "namespace": "online-boutique",
        "desired_replicas": 1,
        "ready_replicas": 1,
        "available_replicas": 1,
        "updated_replicas": 1,
        "generation": 1,
        "observed_generation": 1,
        "ready": True,
    }]
    pods = [{
        "name": "service-xyz-123",
        "namespace": "online-boutique",
        "phase": "Running",
        "ready": True,
        "containers_ready": True,
        "restart_count": 0,
    }]
    prom_results = {
        "service": ServiceTelemetryResult(
            service_name="service",
            request_rate=10.0,
            p95_latency_ms=20.0,
            error_rate=0.0,
            timestamp=datetime.now(timezone.utc),
            is_complete=True,
            missing_metrics=[],
        )
    }

    adapter = make_adapter_with_mocks(deployments, pods, [], dep_objs, prom_results)
    results = adapter.collect_deployment_telemetry()
    assert results[0]["telemetry_available"] is False
    assert "complete_resource_measurements" in results[0]["missing_metrics"]


def test_12_zero_replicas():
    """Verify deployment with zero desired replicas (loadgenerator) is handled safely."""
    deployments = [{
        "name": "loadgenerator",
        "namespace": "online-boutique",
        "desired_replicas": 0,
        "ready_replicas": 0,
        "available_replicas": 0,
        "updated_replicas": 0,
        "generation": 1,
        "observed_generation": 1,
        "ready": True,
    }]
    pods = []
    pod_metrics = []
    dep_objs = {"loadgenerator": create_mock_deployment("loadgenerator", "300m", "256Mi")}
    prom_results = {}

    adapter = make_adapter_with_mocks(deployments, pods, pod_metrics, dep_objs, prom_results)
    results = adapter.collect_deployment_telemetry()
    item = results[0]

    assert item["service_name"] == "loadgenerator"
    assert item["desired_replicas"] == 0
    assert item["ready_replicas"] == 0
    assert item["telemetry_available"] is False
    assert "desired_replicas_is_zero" in item["missing_metrics"]

    valid_inputs, excluded = adapter.get_telemetry_inputs()
    assert len(valid_inputs) == 0
    assert len(excluded) == 1
    assert excluded[0]["service_name"] == "loadgenerator"


def test_13_multiple_replicas():
    """Verify multi-replica deployment aggregates usage and scales requests accordingly."""
    dep_objs = {"paymentservice": create_mock_deployment("paymentservice", "100m", "100Mi")}
    deployments = [{
        "name": "paymentservice",
        "namespace": "online-boutique",
        "desired_replicas": 3,
        "ready_replicas": 3,
        "available_replicas": 3,
        "updated_replicas": 3,
        "generation": 1,
        "observed_generation": 1,
        "ready": True,
    }]
    pods = [
        {"name": "paymentservice-hash-p1", "namespace": "online-boutique", "phase": "Running", "ready": True, "containers_ready": True, "restart_count": 0},
        {"name": "paymentservice-hash-p2", "namespace": "online-boutique", "phase": "Running", "ready": True, "containers_ready": True, "restart_count": 0},
        {"name": "paymentservice-hash-p3", "namespace": "online-boutique", "phase": "Running", "ready": True, "containers_ready": True, "restart_count": 0},
    ]
    # Each pod consumes 30m CPU and 30Mi memory -> Total usage: 90m CPU, 90Mi memory
    # Total request: 3 * 100m = 300m, 3 * 100Mi = 300Mi -> 30% utilization
    pod_metrics = [
        {"pod_name": "paymentservice-hash-p1", "namespace": "online-boutique", "cpu_millicores": 30.0, "memory_mib": 30.0, "timestamp": "2026-11-09T10:00:00Z"},
        {"pod_name": "paymentservice-hash-p2", "namespace": "online-boutique", "cpu_millicores": 30.0, "memory_mib": 30.0, "timestamp": "2026-11-09T10:00:00Z"},
        {"pod_name": "paymentservice-hash-p3", "namespace": "online-boutique", "cpu_millicores": 30.0, "memory_mib": 30.0, "timestamp": "2026-11-09T10:00:00Z"},
    ]
    prom_results = {
        "paymentservice": ServiceTelemetryResult(
            service_name="paymentservice",
            request_rate=45.0,
            p95_latency_ms=18.0,
            error_rate=0.0,
            timestamp=datetime.now(timezone.utc),
            is_complete=True,
            missing_metrics=[],
        )
    }

    adapter = make_adapter_with_mocks(deployments, pods, pod_metrics, dep_objs, prom_results)
    results = adapter.collect_deployment_telemetry()
    res = results[0]

    assert res["desired_replicas"] == 3
    assert res["ready_replicas"] == 3
    assert res["observed_pods"] == 3
    assert res["cpu_usage_millicores"] == 90.0
    assert res["memory_usage_mib"] == 90.0
    assert res["cpu_request_millicores"] == 300.0
    assert res["memory_request_mib"] == 300.0
    assert res["cpu_utilisation"] == 0.30
    assert res["memory_utilisation"] == 0.30
    assert res["telemetry_available"] is True

    valid_inputs, excluded = adapter.get_telemetry_inputs()
    assert len(valid_inputs) == 1
    assert valid_inputs[0].current_replicas == 3
    assert valid_inputs[0].ready_replicas == 3


def test_14_not_ready_replicas():
    """Verify deployment with unready replicas is marked unavailable and excluded."""
    dep_objs = {"service": create_mock_deployment("service", "100m", "100Mi")}
    deployments = [{
        "name": "service",
        "namespace": "online-boutique",
        "desired_replicas": 2,
        "ready_replicas": 1,  # Only 1 ready!
        "available_replicas": 1,
        "updated_replicas": 2,
        "generation": 1,
        "observed_generation": 1,
        "ready": False,
    }]
    pods = [
        {"name": "service-hash-p1", "namespace": "online-boutique", "phase": "Running", "ready": True, "containers_ready": True, "restart_count": 0},
        {"name": "service-hash-p2", "namespace": "online-boutique", "phase": "Running", "ready": False, "containers_ready": False, "restart_count": 0},
    ]
    pod_metrics = [
        {"pod_name": "service-hash-p1", "namespace": "online-boutique", "cpu_millicores": 20.0, "memory_mib": 30.0, "timestamp": "2026-11-09T10:00:00Z"},
    ]
    prom_results = {
        "service": ServiceTelemetryResult(
            service_name="service",
            request_rate=10.0,
            p95_latency_ms=20.0,
            error_rate=0.0,
            timestamp=datetime.now(timezone.utc),
            is_complete=True,
            missing_metrics=[],
        )
    }

    adapter = make_adapter_with_mocks(deployments, pods, pod_metrics, dep_objs, prom_results)
    results = adapter.collect_deployment_telemetry()
    res = results[0]

    assert res["telemetry_available"] is False
    assert "complete_resource_measurements" in res["missing_metrics"]

    valid_inputs, excluded = adapter.get_telemetry_inputs()
    assert len(valid_inputs) == 0
    assert len(excluded) == 1


def test_15_dependency_graph_population():
    """Verify canonical Online Boutique dependencies are attached correctly."""
    services = [
        "frontend", "checkoutservice", "recommendationservice",
        "cartservice", "productcatalogservice", "adservice"
    ]
    deployments = [{
        "name": s,
        "namespace": "online-boutique",
        "desired_replicas": 1,
        "ready_replicas": 1,
        "available_replicas": 1,
        "updated_replicas": 1,
        "generation": 1,
        "observed_generation": 1,
        "ready": True,
    } for s in services]
    pods = [{
        "name": f"{s}-hash-p1",
        "namespace": "online-boutique",
        "phase": "Running",
        "ready": True,
        "containers_ready": True,
        "restart_count": 0,
    } for s in services]
    pod_metrics = [{
        "pod_name": f"{s}-hash-p1",
        "namespace": "online-boutique",
        "cpu_millicores": 20.0,
        "memory_mib": 30.0,
        "timestamp": "2026-11-09T10:00:00Z",
    } for s in services]
    dep_objs = {s: create_mock_deployment(s, "100m", "100Mi") for s in services}
    prom_results = {s: ServiceTelemetryResult(
        service_name=s,
        request_rate=10.0,
        p95_latency_ms=20.0,
        error_rate=0.0,
        timestamp=datetime.now(timezone.utc),
        is_complete=True,
        missing_metrics=[],
    ) for s in services}

    adapter = make_adapter_with_mocks(deployments, pods, pod_metrics, dep_objs, prom_results)
    results = {item["service_name"]: item for item in adapter.collect_deployment_telemetry()}

    assert len(results["frontend"]["dependencies"]) == 7
    assert "checkoutservice" in results["frontend"]["dependencies"]
    assert "cartservice" in results["frontend"]["dependencies"]

    assert len(results["checkoutservice"]["dependencies"]) == 6
    assert "paymentservice" in results["checkoutservice"]["dependencies"]

    assert results["recommendationservice"]["dependencies"] == ["productcatalogservice"]
    assert results["cartservice"]["dependencies"] == ["redis-cart"]
    assert results["productcatalogservice"]["dependencies"] == []
    assert results["adservice"]["dependencies"] == []


def test_16_deployment_phase_integration():
    """Verify deployment phase changes are reflected across all telemetry outputs."""
    dep_objs = {"service": create_mock_deployment("service", "100m", "100Mi")}
    deployments = [{
        "name": "service",
        "namespace": "online-boutique",
        "desired_replicas": 1,
        "ready_replicas": 1,
        "available_replicas": 1,
        "updated_replicas": 1,
        "generation": 1,
        "observed_generation": 1,
        "ready": True,
    }]
    pods = [{
        "name": "service-hash-p1",
        "namespace": "online-boutique",
        "phase": "Running",
        "ready": True,
        "containers_ready": True,
        "restart_count": 0,
    }]
    pod_metrics = [{
        "pod_name": "service-hash-p1",
        "namespace": "online-boutique",
        "cpu_millicores": 20.0,
        "memory_mib": 30.0,
        "timestamp": "2026-11-09T10:00:00Z",
    }]
    prom_results = {
        "service": ServiceTelemetryResult(
            service_name="service",
            request_rate=10.0,
            p95_latency_ms=20.0,
            error_rate=0.0,
            timestamp=datetime.now(timezone.utc),
            is_complete=True,
            missing_metrics=[],
        )
    }

    adapter = make_adapter_with_mocks(deployments, pods, pod_metrics, dep_objs, prom_results)

    for phase in [
        DeploymentPhase.NORMAL_OPERATION,
        DeploymentPhase.PRE_DEPLOYMENT,
        DeploymentPhase.ACTIVE_DEPLOYMENT,
        DeploymentPhase.POST_DEPLOYMENT,
    ]:
        adapter.set_deployment_phase(phase)
        assert adapter.get_deployment_phase() == phase

        telemetry = adapter.collect_deployment_telemetry()
        assert telemetry[0]["deployment_phase"] == phase.value

        summary = adapter.get_telemetry_summary()
        assert summary["deployment_phase"] == phase.value


def test_17_multiple_services_batch_collection():
    """Verify multi-service batch collection correctly separates valid and excluded services."""
    deployments = [
        {"name": "frontend", "namespace": "online-boutique", "desired_replicas": 1, "ready_replicas": 1, "available_replicas": 1, "updated_replicas": 1, "generation": 1, "observed_generation": 1, "ready": True},
        {"name": "paymentservice", "namespace": "online-boutique", "desired_replicas": 1, "ready_replicas": 1, "available_replicas": 1, "updated_replicas": 1, "generation": 1, "observed_generation": 1, "ready": True},
        {"name": "broken-service", "namespace": "online-boutique", "desired_replicas": 1, "ready_replicas": 0, "available_replicas": 0, "updated_replicas": 1, "generation": 1, "observed_generation": 1, "ready": False},
        {"name": "loadgenerator", "namespace": "online-boutique", "desired_replicas": 0, "ready_replicas": 0, "available_replicas": 0, "updated_replicas": 0, "generation": 1, "observed_generation": 1, "ready": True},
    ]
    pods = [
        {"name": "frontend-p1", "namespace": "online-boutique", "phase": "Running", "ready": True, "containers_ready": True, "restart_count": 0},
        {"name": "paymentservice-p1", "namespace": "online-boutique", "phase": "Running", "ready": True, "containers_ready": True, "restart_count": 0},
    ]
    pod_metrics = [
        {"pod_name": "frontend-p1", "namespace": "online-boutique", "cpu_millicores": 25.0, "memory_mib": 50.0, "timestamp": "2026-11-09T10:00:00Z"},
        {"pod_name": "paymentservice-p1", "namespace": "online-boutique", "cpu_millicores": 15.0, "memory_mib": 30.0, "timestamp": "2026-11-09T10:00:00Z"},
    ]
    dep_objs = {
        "frontend": create_mock_deployment("frontend", "100m", "100Mi"),
        "paymentservice": create_mock_deployment("paymentservice", "100m", "100Mi"),
        "broken-service": create_mock_deployment("broken-service", "100m", "100Mi"),
        "loadgenerator": create_mock_deployment("loadgenerator", "100m", "100Mi"),
    }
    prom_results = {
        "frontend": ServiceTelemetryResult(
            service_name="frontend", request_rate=20.0, p95_latency_ms=30.0, error_rate=0.0,
            timestamp=datetime.now(timezone.utc), is_complete=True, missing_metrics=[],
        ),
        "paymentservice": ServiceTelemetryResult(
            service_name="paymentservice", request_rate=15.0, p95_latency_ms=25.0, error_rate=0.0,
            timestamp=datetime.now(timezone.utc), is_complete=True, missing_metrics=[],
        ),
    }

    adapter = make_adapter_with_mocks(deployments, pods, pod_metrics, dep_objs, prom_results)
    valid_inputs, excluded = adapter.get_telemetry_inputs()

    valid_names = {t.service_name for t in valid_inputs}
    excluded_names = {item["service_name"] for item in excluded}

    assert valid_names == {"frontend", "paymentservice"}
    assert excluded_names == {"broken-service", "loadgenerator"}


def test_18_incomplete_telemetry_safety():
    """Verify that incomplete telemetry is never converted into fabricated 0.0 values."""
    dep_objs = {"service": create_mock_deployment("service", "100m", "100Mi")}
    deployments = [{
        "name": "service",
        "namespace": "online-boutique",
        "desired_replicas": 1,
        "ready_replicas": 1,
        "available_replicas": 1,
        "updated_replicas": 1,
        "generation": 1,
        "observed_generation": 1,
        "ready": True,
    }]
    pods = [{
        "name": "service-hash-p1",
        "namespace": "online-boutique",
        "phase": "Running",
        "ready": True,
        "containers_ready": True,
        "restart_count": 0,
    }]
    pod_metrics = [{
        "pod_name": "service-hash-p1",
        "namespace": "online-boutique",
        "cpu_millicores": 20.0,
        "memory_mib": 30.0,
        "timestamp": "2026-11-09T10:00:00Z",
    }]
    # request_rate is None (not 0.0!)
    prom_results = {
        "service": ServiceTelemetryResult(
            service_name="service",
            request_rate=None,
            p95_latency_ms=None,
            error_rate=None,
            timestamp=datetime.now(timezone.utc),
            is_complete=False,
            missing_metrics=["request_rate", "p95_latency", "error_rate"],
        )
    }

    adapter = make_adapter_with_mocks(deployments, pods, pod_metrics, dep_objs, prom_results)
    results = adapter.collect_deployment_telemetry()
    res = results[0]

    # Explicit None, never converted to 0.0
    assert res["request_rate"] is None
    assert res["p95_latency_ms"] is None
    assert res["error_rate"] is None

    # Excluded from TelemetryInput
    valid_inputs, excluded = adapter.get_telemetry_inputs()
    assert len(valid_inputs) == 0
    assert len(excluded) == 1
    assert "request_rate" in excluded[0]["missing_metrics"]

