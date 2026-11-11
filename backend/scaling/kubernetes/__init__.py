"""
Kubernetes and Prometheus integration package for DPBPS framework.
"""

from .client import (
    create_api_client,
    get_apps_v1_api,
    get_core_v1_api,
    get_autoscaling_v2_api,
)
from .cluster_manager import KubernetesClusterManager
from .metrics_collector import KubernetesMetricsCollector, parse_cpu, parse_memory
from .telemetry_adapter import (
    KubernetesTelemetryAdapter,
    ONLINE_BOUTIQUE_DEPENDENCIES,
)
from .actuator import (
    KubernetesScalingActuator,
    KubernetesScalingResult,
    ScalingExecutionStatus,
    PROTECTED_INFRASTRUCTURE,
)
from .prometheus_client import (
    PrometheusClient,
    PrometheusClientError,
    PrometheusConnectionError,
    PrometheusResponseError,
    PrometheusDataError,
    MetricSample,
    MetricQueryResult,
    ServiceTelemetryResult,
)

__all__ = [
    "create_api_client",
    "get_apps_v1_api",
    "get_core_v1_api",
    "get_autoscaling_v2_api",
    "KubernetesClusterManager",
    "KubernetesMetricsCollector",
    "parse_cpu",
    "parse_memory",
    "KubernetesTelemetryAdapter",
    "ONLINE_BOUTIQUE_DEPENDENCIES",
    "KubernetesScalingActuator",
    "KubernetesScalingResult",
    "ScalingExecutionStatus",
    "PROTECTED_INFRASTRUCTURE",
    "PrometheusClient",
    "PrometheusClientError",
    "PrometheusConnectionError",
    "PrometheusResponseError",
    "PrometheusDataError",
    "MetricSample",
    "MetricQueryResult",
    "ServiceTelemetryResult",
]

