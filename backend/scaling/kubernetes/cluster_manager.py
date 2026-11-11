"""
Kubernetes cluster manager for the DPBPS framework.

Provides read-only access to Kubernetes deployments,
replica information, and pod health.

This module does not perform scaling operations.
"""

import logging
from typing import Any

from kubernetes.client import ApiException

from backend.scaling.kubernetes.client import get_apps_v1_api
from backend.scaling.kubernetes.client import get_core_v1_api


logger = logging.getLogger(__name__)


class KubernetesClusterManager:
    """
    Read-only manager for Kubernetes cluster resources.

    Responsibilities:
    - Retrieve deployments.
    - Retrieve replica information.
    - Retrieve deployment readiness.
    - Retrieve pod health.
    """

    def __init__(self, namespace: str = "online-boutique"):
        self.namespace = namespace

        self.apps_api = get_apps_v1_api()
        self.core_api = get_core_v1_api()

    def get_deployments(self) -> list[dict[str, Any]]:
        """
        Retrieve deployments from the configured namespace.
        """

        try:
            deployments = self.apps_api.list_namespaced_deployment(
                namespace=self.namespace
            )

            results = []

            for deployment in deployments.items:

                status = deployment.status
                spec = deployment.spec

                results.append({
                    "name": deployment.metadata.name,
                    "namespace": deployment.metadata.namespace,
                    "desired_replicas": spec.replicas or 0,
                    "ready_replicas": status.ready_replicas or 0,
                    "available_replicas": status.available_replicas or 0,
                    "updated_replicas": status.updated_replicas or 0,
                    "generation": deployment.metadata.generation,
                    "observed_generation": status.observed_generation,
                    "ready": (
                        (status.ready_replicas or 0)
                        == (spec.replicas or 0)
                    )
                })

            return results

        except ApiException as exc:
            logger.exception(
                "Failed to retrieve Kubernetes deployments."
            )

            raise RuntimeError(
                f"Kubernetes deployment retrieval failed: {exc.reason}"
            ) from exc

    def get_deployment(
        self,
        deployment_name: str
    ) -> dict[str, Any] | None:
        """
        Retrieve one deployment by name.
        """

        try:
            deployment = self.apps_api.read_namespaced_deployment(
                name=deployment_name,
                namespace=self.namespace
            )

            status = deployment.status
            spec = deployment.spec

            return {
                "name": deployment.metadata.name,
                "namespace": deployment.metadata.namespace,
                "desired_replicas": spec.replicas or 0,
                "ready_replicas": status.ready_replicas or 0,
                "available_replicas": status.available_replicas or 0,
                "updated_replicas": status.updated_replicas or 0,
                "ready": (
                    (status.ready_replicas or 0)
                    == (spec.replicas or 0)
                )
            }

        except ApiException as exc:

            if exc.status == 404:
                return None

            logger.exception(
                "Failed to retrieve deployment: %s",
                deployment_name
            )

            raise RuntimeError(
                f"Deployment retrieval failed: {exc.reason}"
            ) from exc

    def get_pod_health(self) -> list[dict[str, Any]]:
        """
        Retrieve pod health information from the namespace.
        """

        try:
            pods = self.core_api.list_namespaced_pod(
                namespace=self.namespace
            )

            results = []

            for pod in pods.items:

                container_statuses = (
                    pod.status.container_statuses or []
                )

                containers_ready = all(
                    container.ready
                    for container in container_statuses
                )

                results.append({
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "phase": pod.status.phase,
                    "pod_ip": pod.status.pod_ip,
                    "node_name": pod.spec.node_name,
                    "containers_ready": containers_ready,
                    "restart_count": sum(
                        container.restart_count
                        for container in container_statuses
                    )
                })

            return results

        except ApiException as exc:
            logger.exception(
                "Failed to retrieve Kubernetes pod health."
            )

            raise RuntimeError(
                f"Kubernetes pod retrieval failed: {exc.reason}"
            ) from exc

    def get_cluster_summary(self) -> dict[str, Any]:
        """
        Return a summary of deployments and pod health.
        """

        deployments = self.get_deployments()
        pods = self.get_pod_health()

        return {
            "namespace": self.namespace,
            "deployment_count": len(deployments),
            "pod_count": len(pods),
            "healthy_deployments": sum(
                1 for deployment in deployments
                if deployment["ready"]
            ),
            "running_pods": sum(
                1 for pod in pods
                if pod["phase"] == "Running"
                and pod["containers_ready"]
            ),
            "deployments": deployments,
            "pods": pods
        }