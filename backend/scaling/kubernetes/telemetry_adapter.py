"""
Kubernetes telemetry adapter for the DPBPS framework.

Combines:
1. Kubernetes deployment information (desired, ready, and available replicas).
2. Kubernetes pod resource metrics from Metrics Server (CPU millicores, Memory MiB).
3. CPU and memory resource requests from deployment specifications.
4. Application-level metrics from Prometheus (request rate, P95 latency, error rate).
5. Microservice dependency mapping for bottleneck prioritization.
6. Deployment phase awareness from DeploymentStateManager.

Calculates normalized CPU and memory utilization fractions [0.0, 1.0],
strictly enforcing DPBPS TelemetryInput schema validation.

Safe telemetry handling:
- Distinguishes genuine zero measurements (idle service) from missing or stale telemetry.
- Incomplete telemetry is excluded from scaling-ready TelemetryInput objects.
- This module is read-only and does not perform scaling operations.
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.scaling.kubernetes.client import get_apps_v1_api
from backend.scaling.kubernetes.cluster_manager import (
    KubernetesClusterManager,
)
from backend.scaling.kubernetes.metrics_collector import (
    KubernetesMetricsCollector,
)
from backend.scaling.kubernetes.prometheus_client import (
    PrometheusClient,
    ServiceTelemetryResult,
)
from backend.scaling.models import (
    DeploymentPhase,
    TelemetryInput,
)
from backend.scaling.deployment_state import (
    DeploymentStateManager,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# CANONICAL ONLINE BOUTIQUE DEPENDENCY MAP
# ---------------------------------------------------------------------
# Represents the call-graph topology of the 10 Online Boutique microservices.
# Used by bottleneck detection to trace downstream service latency and errors.

ONLINE_BOUTIQUE_DEPENDENCIES: Dict[str, List[str]] = {
    "frontend": [
        "adservice",
        "cartservice",
        "checkoutservice",
        "currencyservice",
        "productcatalogservice",
        "recommendationservice",
        "shippingservice",
    ],
    "checkoutservice": [
        "cartservice",
        "currencyservice",
        "emailservice",
        "paymentservice",
        "productcatalogservice",
        "shippingservice",
    ],
    "recommendationservice": [
        "productcatalogservice",
    ],
    "cartservice": [
        "redis-cart",
    ],
    "productcatalogservice": [],
    "currencyservice": [],
    "paymentservice": [],
    "shippingservice": [],
    "emailservice": [],
    "adservice": [],
}


class KubernetesTelemetryAdapter:
    """
    Converts Kubernetes deployment and pod metrics along with Prometheus
    application metrics into validated DPBPS deployment telemetry.
    """

    def __init__(
        self,
        namespace: str = "online-boutique",
        cluster_manager: Optional[KubernetesClusterManager] = None,
        metrics_collector: Optional[KubernetesMetricsCollector] = None,
        prometheus_client: Optional[PrometheusClient] = None,
        state_manager: Optional[DeploymentStateManager] = None,
        apps_api: Optional[Any] = None,
        prometheus_base_url: Optional[str] = None,
        dependency_map: Optional[Dict[str, List[str]]] = None,
    ):
        """
        Initialize the Kubernetes telemetry adapter.

        Args:
            namespace: Target Kubernetes namespace (default: "online-boutique").
            cluster_manager: Optional KubernetesClusterManager instance (for testing/DI).
            metrics_collector: Optional KubernetesMetricsCollector instance (for testing/DI).
            prometheus_client: Optional PrometheusClient instance (for testing/DI).
            state_manager: Optional DeploymentStateManager instance (for testing/DI).
            apps_api: Optional Kubernetes AppsV1Api instance (for testing/DI).
            prometheus_base_url: Optional Prometheus base URL if creating default PrometheusClient.
            dependency_map: Optional custom dependency graph (defaults to ONLINE_BOUTIQUE_DEPENDENCIES).
        """
        self.namespace = namespace

        self.cluster_manager = cluster_manager or KubernetesClusterManager(
            namespace=namespace
        )

        self.metrics_collector = metrics_collector or KubernetesMetricsCollector(
            namespace=namespace
        )

        self.apps_api = apps_api or get_apps_v1_api()

        self.prometheus_client = prometheus_client or PrometheusClient(
            base_url=prometheus_base_url
        )

        self.state_manager = state_manager or DeploymentStateManager()

        self.dependency_map = (
            dependency_map
            if dependency_map is not None
            else ONLINE_BOUTIQUE_DEPENDENCIES
        )

    # -----------------------------------------------------------------
    # DEPLOYMENT PHASE INTEGRATION
    # -----------------------------------------------------------------

    def set_deployment_phase(self, phase: DeploymentPhase) -> None:
        """Update the active deployment phase in the state manager."""
        self.state_manager.set_phase(phase)

    def get_deployment_phase(self) -> DeploymentPhase:
        """Return the current active deployment phase."""
        return self.state_manager.get_phase()

    # -----------------------------------------------------------------
    # RESOURCE UNIT CONVERSIONS
    # -----------------------------------------------------------------

    @staticmethod
    def _cpu_to_millicores(value: str) -> float:
        """
        Convert Kubernetes CPU resource requests to millicores.
        """
        value = str(value)

        if value.endswith("n"):
            return float(value[:-1]) / 1_000_000

        if value.endswith("u"):
            return float(value[:-1]) / 1_000

        if value.endswith("m"):
            return float(value[:-1])

        return float(value) * 1000

    @staticmethod
    def _memory_to_mib(value: str) -> float:
        """
        Convert Kubernetes memory resource requests to MiB.
        """
        units = {
            "Ki": 1 / 1024,
            "Mi": 1,
            "Gi": 1024,
            "Ti": 1024 * 1024,
            "K": 1000 / (1024 * 1024),
            "M": 1_000_000 / (1024 * 1024),
            "G": 1_000_000_000 / (1024 * 1024),
        }

        value = str(value)

        for unit, multiplier in units.items():
            if value.endswith(unit):
                amount = float(value[:-len(unit)])
                return amount * multiplier

        return float(value) / (1024 * 1024)

    def _get_deployment_requests(
        self,
        deployment_name: str
    ) -> dict[str, float]:
        """
        Retrieve total CPU and memory requests for one replica.

        Supports multiple containers within a deployment.
        """
        deployment = self.apps_api.read_namespaced_deployment(
            name=deployment_name,
            namespace=self.namespace
        )

        total_cpu = 0.0
        total_memory = 0.0

        for container in deployment.spec.template.spec.containers:
            requests = (
                container.resources.requests
                if container.resources
                else None
            )

            if not requests:
                raise ValueError(
                    f"Resource requests missing for container "
                    f"{container.name} in {deployment_name}"
                )

            cpu_request = requests.get("cpu")
            memory_request = requests.get("memory")

            if cpu_request is None or memory_request is None:
                raise ValueError(
                    f"CPU or memory request missing for container "
                    f"{container.name} in {deployment_name}"
                )

            total_cpu += self._cpu_to_millicores(cpu_request)
            total_memory += self._memory_to_mib(memory_request)

        return {
            "cpu_request_millicores_per_replica": total_cpu,
            "memory_request_mib_per_replica": total_memory
        }

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        """
        Convert a Kubernetes RFC3339 timestamp into UTC datetime.
        """
        timestamp = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        return timestamp.astimezone(timezone.utc)

    @staticmethod
    def _normalize_utilization(
        usage: float,
        request_total: float,
        resource_name: str,
        diagnostics: List[str],
    ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Calculate normalized utilization fraction [0.0, 1.0], uncapped ratio, and percentage.

        Denominator baseline:
            Measured relative to the aggregate Kubernetes resource requests of
            desired replicas (e.g., usage / (request_per_replica * desired_replicas)).

        Constraint Handling:
            TelemetryInput strictly validates `cpu_utilisation: float = Field(..., ge=0, le=1)`.
            When actual pod usage exceeds requested capacity (container bursting into limits),
            the normalized fraction is clamped to 1.0 to satisfy model constraints without
            throwing validation errors.
            The uncapped ratio and percentage are preserved in telemetry diagnostics and metadata
            so no operational insight is silently discarded.

        Returns:
            (fraction, ratio, percent) where:
            - fraction: clamped to [0.0, 1.0] for TelemetryInput.
            - ratio: raw uncapped ratio (can exceed 1.0).
            - percent: percentage (ratio * 100).
        """
        if request_total <= 0:
            diagnostics.append(
                f"{resource_name} aggregate request is non-positive ({request_total})."
            )
            return None, None, None

        raw_ratio = usage / request_total
        percent = raw_ratio * 100.0

        if raw_ratio > 1.0:
            diagnostics.append(
                f"{resource_name} usage ({usage:.2f}) exceeds requested capacity ({request_total:.2f}); "
                f"uncapped_ratio={raw_ratio:.4f} ({percent:.2f}%), clamped to 1.0 for model constraints."
            )
            fraction = 1.0
        else:
            fraction = max(0.0, raw_ratio)

        return round(fraction, 4), round(raw_ratio, 4), round(percent, 2)

    # -----------------------------------------------------------------
    # TELEMETRY COLLECTION
    # -----------------------------------------------------------------

    def collect_deployment_telemetry(
        self
    ) -> list[dict[str, Any]]:
        """
        Collect and aggregate infrastructure and application telemetry for all deployments.

        Combines:
        - Kubernetes deployment status (desired, ready, available replicas).
        - Metrics Server pod CPU and memory usage.
        - Container CPU and memory resource requests.
        - Prometheus application metrics (request rate, P95 latency, error rate).
        - Online Boutique dependency graph.
        - Active deployment phase.

        Returns a list of dictionaries with normalized utilization, completeness flags,
        and diagnostic details.
        """
        deployments = self.cluster_manager.get_deployments()
        pods = self.cluster_manager.get_pod_health()
        pod_metrics = self.metrics_collector.get_pod_metrics()

        # Map pod names to health status
        pod_health = {
            pod["name"]: pod
            for pod in pods
        }

        # Map deployment names to pod metrics
        grouped_metrics = defaultdict(list)

        for metric in pod_metrics:
            pod_name = metric["pod_name"]
            pod = pod_health.get(pod_name)

            if not pod:
                continue

            if pod["phase"] != "Running":
                continue

            if not pod["containers_ready"]:
                continue

            # Deployment pod names match <deployment-name>-<replicaset-hash>-<pod-id>
            deployment_name = None
            for deployment in deployments:
                prefix = deployment["name"] + "-"
                if pod_name.startswith(prefix):
                    if (
                        deployment_name is None
                        or len(deployment["name"]) > len(deployment_name)
                    ):
                        deployment_name = deployment["name"]

            if deployment_name:
                grouped_metrics[deployment_name].append(metric)

        current_phase = self.state_manager.get_phase().value
        results = []

        for deployment in deployments:
            name = deployment["name"]
            desired_replicas = deployment["desired_replicas"]
            ready_replicas = deployment["ready_replicas"]
            metrics = grouped_metrics.get(name, [])
            observed_pods = len(metrics)

            missing_metrics: List[str] = []
            diagnostics: List[str] = []
            dependencies = self.dependency_map.get(name, [])

            # Deployments with zero desired replicas (e.g. loadgenerator)
            # do not participate in active scaling telemetry.
            if desired_replicas == 0:
                results.append({
                    "service_name": name,
                    "namespace": self.namespace,
                    "desired_replicas": 0,
                    "ready_replicas": 0,
                    "observed_pods": 0,
                    "cpu_usage_millicores": 0.0,
                    "memory_usage_mib": 0.0,
                    "cpu_request_millicores": 0.0,
                    "memory_request_mib": 0.0,
                    "cpu_utilisation": None,
                    "memory_utilisation": None,
                    "cpu_utilization_ratio": None,
                    "memory_utilization_ratio": None,
                    "cpu_utilization_percent": None,
                    "memory_utilization_percent": None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "telemetry_available": False,
                    "request_rate": None,
                    "p95_latency_ms": None,
                    "error_rate": None,
                    "dependencies": dependencies,
                    "deployment_phase": current_phase,
                    "missing_metrics": ["desired_replicas_is_zero"],
                    "diagnostics": ["Deployment has zero desired replicas."],
                    "reason": "Deployment has zero desired replicas."
                })
                continue

            # Retrieve container resource requests
            try:
                requests = self._get_deployment_requests(name)
                cpu_req_replica = requests["cpu_request_millicores_per_replica"]
                mem_req_replica = requests["memory_request_mib_per_replica"]
            except Exception as exc:
                diagnostics.append(f"Failed to retrieve resource requests: {exc}")
                requests = None
                cpu_req_replica = 0.0
                mem_req_replica = 0.0
                missing_metrics.append("resource_requests")

            cpu_usage = sum(metric["cpu_millicores"] for metric in metrics)
            memory_usage = sum(metric["memory_mib"] for metric in metrics)

            cpu_request_total = cpu_req_replica * desired_replicas
            memory_request_total = mem_req_replica * desired_replicas

            # Complete resource measurement requires all desired replicas to be
            # running, ready, and observed by Metrics Server.
            complete_resource_measurement = (
                observed_pods == ready_replicas
                and ready_replicas == desired_replicas
                and observed_pods > 0
                and requests is not None
            )

            if complete_resource_measurement:
                cpu_fraction, cpu_ratio, cpu_percent = self._normalize_utilization(
                    cpu_usage, cpu_request_total, "CPU", diagnostics
                )
                mem_fraction, mem_ratio, mem_percent = self._normalize_utilization(
                    memory_usage, memory_request_total, "Memory", diagnostics
                )
            else:
                cpu_fraction, cpu_ratio, cpu_percent = None, None, None
                mem_fraction, mem_ratio, mem_percent = None, None, None
                missing_metrics.append("complete_resource_measurements")
                if observed_pods != ready_replicas or ready_replicas != desired_replicas:
                    diagnostics.append(
                        f"Pod count mismatch: observed_pods={observed_pods}, "
                        f"ready_replicas={ready_replicas}, desired_replicas={desired_replicas}"
                    )

            # Query Prometheus for application-level metrics
            prom_result: Optional[ServiceTelemetryResult] = None
            if self.prometheus_client:
                try:
                    prom_result = self.prometheus_client.get_service_telemetry(
                        service_name=name,
                        namespace=self.namespace,
                    )
                except Exception as exc:
                    logger.warning(
                        f"Failed to query Prometheus for service {name}: {exc}"
                    )
                    diagnostics.append(f"Prometheus query failure: {exc}")

            if prom_result:
                request_rate = prom_result.request_rate
                p95_latency_ms = prom_result.p95_latency_ms
                error_rate = prom_result.error_rate

                if prom_result.missing_metrics:
                    # Filter out duplicate infrastructure metrics since we compute
                    # them directly from Kubernetes Metrics Server
                    for m in prom_result.missing_metrics:
                        if m not in missing_metrics and m in {"request_rate", "p95_latency", "error_rate"}:
                            missing_metrics.append(m)

                if prom_result.diagnostic_messages:
                    diagnostics.extend(prom_result.diagnostic_messages)
            else:
                request_rate = None
                p95_latency_ms = None
                error_rate = None
                missing_metrics.extend(["request_rate", "p95_latency", "error_rate"])

            # Timestamps
            metric_timestamps = [
                self._parse_timestamp(metric["timestamp"])
                for metric in metrics
                if metric.get("timestamp")
            ]
            latest_timestamp = (
                max(metric_timestamps).isoformat()
                if metric_timestamps
                else (
                    prom_result.timestamp.isoformat()
                    if prom_result and prom_result.timestamp
                    else datetime.now(timezone.utc).isoformat()
                )
            )

            # Overall completeness check:
            # Requires all metrics to be present, non-null, and no missing metric flags.
            has_app_metrics = (
                request_rate is not None
                and p95_latency_ms is not None
                and error_rate is not None
            )
            has_res_metrics = (
                complete_resource_measurement
                and cpu_fraction is not None
                and mem_fraction is not None
            )

            is_telemetry_complete = (
                has_app_metrics
                and has_res_metrics
                and len(missing_metrics) == 0
            )

            results.append({
                "service_name": name,
                "namespace": self.namespace,
                "desired_replicas": desired_replicas,
                "ready_replicas": ready_replicas,
                "observed_pods": observed_pods,
                "cpu_usage_millicores": round(cpu_usage, 3),
                "memory_usage_mib": round(memory_usage, 3),
                "cpu_request_millicores": round(cpu_request_total, 3),
                "memory_request_mib": round(memory_request_total, 3),
                "cpu_utilisation": cpu_fraction,
                "memory_utilisation": mem_fraction,
                "cpu_utilization_ratio": cpu_ratio,
                "memory_utilization_ratio": mem_ratio,
                "cpu_utilization_percent": cpu_percent,
                "memory_utilization_percent": mem_percent,
                "timestamp": latest_timestamp,
                "telemetry_available": is_telemetry_complete,
                "request_rate": request_rate,
                "p95_latency_ms": p95_latency_ms,
                "error_rate": error_rate,
                "dependencies": dependencies,
                "deployment_phase": current_phase,
                "missing_metrics": sorted(list(set(missing_metrics))),
                "diagnostics": diagnostics,
            })

        return results

    # -----------------------------------------------------------------
    # VALIDATED TELEMETRY INPUT GENERATION
    # -----------------------------------------------------------------

    def get_telemetry_inputs(
        self,
    ) -> Tuple[List[TelemetryInput], List[Dict[str, Any]]]:
        """
        Produce validated TelemetryInput objects for services with complete, fresh telemetry.

        Returns:
            A tuple of (valid_inputs, excluded_telemetry) where:
            - valid_inputs: List of validated TelemetryInput instances ready for DPBPS evaluation.
            - excluded_telemetry: List of raw telemetry dictionaries for services that were
              excluded due to missing, stale, or incomplete metrics (retaining diagnostic reasons).
        """
        raw_telemetry = self.collect_deployment_telemetry()
        valid_inputs: List[TelemetryInput] = []
        excluded_telemetry: List[Dict[str, Any]] = []

        now_utc = datetime.now(timezone.utc)

        for item in raw_telemetry:
            # Strict completeness check: exclude if telemetry is not complete
            if not item.get("telemetry_available", False) or item.get("missing_metrics"):
                excluded_telemetry.append(item)
                continue

            try:
                # Parse timestamp
                ts_str = item.get("timestamp")
                if ts_str:
                    dt = self._parse_timestamp(ts_str)
                else:
                    dt = now_utc

                # Clamp clock drift if timestamp is slightly in future
                if dt > now_utc:
                    dt = now_utc

                t_input = TelemetryInput(
                    service_name=item["service_name"],
                    request_rate=float(item["request_rate"]),
                    p95_latency=float(item["p95_latency_ms"]),
                    error_rate=float(item["error_rate"]),
                    cpu_utilisation=float(item["cpu_utilisation"]),
                    memory_utilisation=float(item["memory_utilisation"]),
                    current_replicas=int(item["desired_replicas"]),
                    ready_replicas=(
                        int(item["ready_replicas"])
                        if item.get("ready_replicas") is not None
                        else None
                    ),
                    timestamp=dt,
                    dependencies=list(item.get("dependencies", [])),
                )
                valid_inputs.append(t_input)
            except Exception as exc:
                logger.warning(
                    f"Failed to create TelemetryInput for {item.get('service_name')}: {exc}"
                )
                item["validation_error"] = str(exc)
                excluded_telemetry.append(item)

        return valid_inputs, excluded_telemetry

    # -----------------------------------------------------------------
    # SUMMARY
    # -----------------------------------------------------------------

    def get_telemetry_summary(self) -> dict[str, Any]:
        """
        Return deployment-level telemetry summary.
        """
        telemetry = self.collect_deployment_telemetry()

        complete_count = sum(1 for item in telemetry if item["telemetry_available"])
        incomplete_count = len(telemetry) - complete_count

        return {
            "namespace": self.namespace,
            "deployment_count": len(telemetry),
            "complete_telemetry_count": complete_count,
            "incomplete_telemetry_count": incomplete_count,
            "resource_telemetry_available": complete_count,
            "resource_telemetry_unavailable": incomplete_count,
            "application_metrics_integrated": True,
            "deployment_phase": self.state_manager.get_phase().value,
            "deployments": telemetry,
        }
