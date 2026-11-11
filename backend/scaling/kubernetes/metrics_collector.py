"""
Kubernetes metrics collector for the DPBPS framework.

Collects actual CPU and memory utilization
from the Kubernetes Metrics API.

This module is read-only.
It does not perform scaling operations.
"""

import logging
import re
from typing import Any

from kubernetes.client import ApiException

from backend.scaling.kubernetes.client import create_api_client


logger = logging.getLogger(__name__)


def parse_cpu(value: str) -> float:
    """
    Convert Kubernetes CPU quantities into millicores.

    Examples:
        100m -> 100
        1    -> 1000
        500u -> 0.5
    """

    if value.endswith("n"):
        return float(value[:-1]) / 1_000_000

    if value.endswith("u"):
        return float(value[:-1]) / 1_000

    if value.endswith("m"):
        return float(value[:-1])

    return float(value) * 1000


def parse_memory(value: str) -> float:
    """
    Convert Kubernetes memory quantities into MiB.
    """

    units = {
        "Ki": 1 / 1024,
        "Mi": 1,
        "Gi": 1024,
        "Ti": 1024 * 1024,
        "K": 1 / 1024,
        "M": 1_000_000 / 1_048_576,
        "G": 1_000_000_000 / 1_048_576,
    }

    match = re.fullmatch(
        r"([0-9]+(?:\.[0-9]+)?)([a-zA-Z]*)",
        value
    )

    if not match:
        raise ValueError(f"Unsupported memory quantity: {value}")

    amount = float(match.group(1))
    unit = match.group(2)

    if unit == "":
        return amount / (1024 * 1024)

    if unit not in units:
        raise ValueError(f"Unsupported memory unit: {unit}")

    return amount * units[unit]


class KubernetesMetricsCollector:
    """
    Read-only Kubernetes pod metrics collector.
    """

    def __init__(self, namespace: str = "online-boutique"):

        self.namespace = namespace

        self.api_client = create_api_client()

    def get_pod_metrics(self) -> list[dict[str, Any]]:
        """
        Retrieve CPU and memory metrics for namespace pods.

        Requires Kubernetes Metrics Server.
        """

        try:

            response = self.api_client.call_api(
                "/apis/metrics.k8s.io/v1beta1/namespaces/{namespace}/pods",
                "GET",
                path_params={
                    "namespace": self.namespace
                },
                query_params=[],
                header_params={
                    "Accept": "application/json"
                },
                body=None,
                post_params=[],
                files={},
                response_type="object",
                auth_settings=["BearerToken"],
                async_req=False,
                _return_http_data_only=True,
                _preload_content=True
            )

            results = []

            for pod in response.get("items", []):

                container_metrics = []

                total_cpu = 0.0
                total_memory = 0.0

                for container in pod.get("containers", []):

                    usage = container.get("usage", {})

                    cpu = parse_cpu(usage.get("cpu", "0"))
                    memory = parse_memory(usage.get("memory", "0"))

                    total_cpu += cpu
                    total_memory += memory

                    container_metrics.append({
                        "container": container.get("name"),
                        "cpu_millicores": cpu,
                        "memory_mib": memory
                    })

                results.append({
                    "pod_name": pod.get("metadata", {}).get("name"),
                    "namespace": self.namespace,
                    "timestamp": pod.get("timestamp"),
                    "window": pod.get("window"),
                    "cpu_millicores": total_cpu,
                    "memory_mib": total_memory,
                    "containers": container_metrics
                })

            return results

        except ApiException as exc:

            logger.exception(
                "Unable to retrieve Kubernetes pod metrics."
            )

            raise RuntimeError(
                f"Kubernetes Metrics API error: {exc.reason}"
            ) from exc

    def get_metrics_summary(self) -> dict[str, Any]:
        """
        Generate a summary of collected pod metrics.
        """

        metrics = self.get_pod_metrics()

        return {
            "namespace": self.namespace,
            "pod_count": len(metrics),
            "total_cpu_millicores": round(
                sum(item["cpu_millicores"] for item in metrics),
                2
            ),
            "total_memory_mib": round(
                sum(item["memory_mib"] for item in metrics),
                2
            ),
            "pods": metrics
        }