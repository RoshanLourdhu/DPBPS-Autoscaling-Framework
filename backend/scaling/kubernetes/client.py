"""
Kubernetes API client for the DPBPS framework.

Supports:
1. Local development using kubeconfig.
2. In-cluster authentication when deployed inside Kubernetes.

The client only establishes API connectivity.
It does not modify cluster resources.
"""

import logging
import os

from kubernetes import client, config
from kubernetes.config.config_exception import ConfigException


logger = logging.getLogger(__name__)


def create_api_client() -> client.ApiClient:
    """
    Create an authenticated Kubernetes API client.

    Local kubeconfig is preferred for development.
    In-cluster configuration is used as a fallback.

    Returns:
        client.ApiClient: Authenticated Kubernetes API client.

    Raises:
        RuntimeError: If Kubernetes authentication fails.
    """

    configuration = client.Configuration()

    context = os.getenv("KUBERNETES_CONTEXT")

    # Option 1: Load local kubeconfig.
    try:
        config.load_kube_config(
            client_configuration=configuration,
            context=context
        )

        logger.info("Connected using local Kubernetes configuration.")

        return client.ApiClient(configuration=configuration)

    except ConfigException as local_error:

        logger.warning(
            "Local Kubernetes configuration unavailable: %s",
            local_error
        )

    # Option 2: Load in-cluster configuration.
    try:
        config.load_incluster_config(
            client_configuration=configuration
        )

        logger.info("Connected using in-cluster Kubernetes configuration.")

        return client.ApiClient(configuration=configuration)

    except ConfigException as cluster_error:

        raise RuntimeError(
            "Unable to connect to Kubernetes. "
            "Check kubeconfig or in-cluster service account configuration."
        ) from cluster_error


def get_core_v1_api() -> client.CoreV1Api:
    """
    Return the Kubernetes Core V1 API.

    Used for:
    - Nodes
    - Pods
    - Services
    """

    api_client = create_api_client()

    return client.CoreV1Api(api_client)


def get_apps_v1_api() -> client.AppsV1Api:
    """
    Return the Kubernetes Apps V1 API.

    Used for:
    - Deployments
    - ReplicaSets
    - StatefulSets
    """

    api_client = create_api_client()

    return client.AppsV1Api(api_client)


def get_autoscaling_v2_api() -> client.AutoscalingV2Api:
    """
    Return the Kubernetes Autoscaling V2 API.

    Used for:
    - HorizontalPodAutoscalers (HPAs)
    """

    api_client = create_api_client()

    return client.AutoscalingV2Api(api_client)
