"""
Scaling configuration validation for DPBPS.

Validates the Docker Compose configuration and ensures that
only explicitly authorized, safely scalable services are
included in the scaling allowlist.
"""

import logging
from pathlib import Path
from typing import List

import yaml

import backend.config as cfg


logger = logging.getLogger(__name__)

# Resolve the project root independently of the current working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

COMPOSE_PATH = PROJECT_ROOT / "docker-compose.yml"

# Services that must never be dynamically scaled by this actuator.
PROTECTED_SERVICES = {
    "postgres",
    "frontend",
    "orchestration-api",
}


def load_compose() -> dict:
    """
    Load and parse docker-compose.yml.

    Returns:
        dict: Docker Compose configuration.

    Raises:
        FileNotFoundError: If the Compose file does not exist.
        ValueError: If the configuration is invalid.
    """

    if not COMPOSE_PATH.exists():
        raise FileNotFoundError(
            f"Docker Compose file not found: {COMPOSE_PATH}"
        )

    try:
        with COMPOSE_PATH.open("r", encoding="utf-8") as file:
            compose = yaml.safe_load(file) or {}

    except yaml.YAMLError as exc:
        raise ValueError(
            f"Invalid Docker Compose YAML: {exc}"
        ) from exc

    if not isinstance(compose, dict):
        raise ValueError(
            "Docker Compose configuration must be a YAML mapping."
        )

    return compose


def get_service_definitions(compose: dict) -> dict:
    """
    Extract service definitions from the Compose configuration.
    """

    services = compose.get("services", {})

    if not isinstance(services, dict):
        raise ValueError(
            "Docker Compose services section must be a mapping."
        )

    return services


def get_scaling_allowlist() -> List[str]:
    """
    Return the explicitly configured scaling allowlist.

    The backend configuration is the single source of truth.
    An empty allowlist authorizes no services.
    """

    raw = getattr(cfg, "SCALING_ALLOWLIST", [])

    if raw is None:
        return []

    if isinstance(raw, str):
        return [
            service.strip()
            for service in raw.split(",")
            if service.strip()
        ]

    return [
        str(service).strip()
        for service in raw
        if str(service).strip()
    ]


def validate_scaling_configuration() -> List[str]:
    """
    Validate the complete scaling configuration.

    Checks:
    1. Compose configuration can be loaded.
    2. Scaling allowlist is not empty.
    3. Every allowlisted service exists.
    4. Protected services cannot be scaled.
    5. Services cannot expose host-port mappings.
    6. Every scalable service must define a healthcheck.

    Returns:
        List[str]: Validation errors. An empty list means the
        configuration passed these checks.
    """

    errors: List[str] = []

    try:
        compose = load_compose()
        services = get_service_definitions(compose)

    except (FileNotFoundError, ValueError, OSError) as exc:
        errors.append(
            f"Unable to load Docker Compose configuration: {exc}"
        )
        return errors

    allowlist = get_scaling_allowlist()

    # Fail closed: an empty allowlist must never authorize scaling.
    if not allowlist:
        errors.append(
            "Scaling allowlist is empty. No services are authorized for scaling."
        )
        return errors

    # Avoid duplicate validation work.
    allowlist = list(dict.fromkeys(allowlist))

    for service_name in allowlist:

        # Check that the service exists.
        if service_name not in services:
            errors.append(
                f"Service '{service_name}' does not exist in docker-compose.yml."
            )
            continue

        service = services[service_name]

        if not isinstance(service, dict):
            errors.append(
                f"Invalid Compose definition for service '{service_name}'."
            )
            continue

        # Protected services cannot be scaled.
        if service_name in PROTECTED_SERVICES:
            errors.append(
                f"Service '{service_name}' is protected and cannot be scaled."
            )

        # Services with host-port mappings are unsafe to replicate.
        if service.get("ports"):
            errors.append(
                f"Service '{service_name}' has host-port mapping and cannot be scaled."
            )

        # Health verification is mandatory.
        if not service.get("healthcheck"):
            errors.append(
                f"Service '{service_name}' does not define a healthcheck."
            )

    if errors:
        for error in errors:
            logger.error("Scaling configuration error: %s", error)

    else:
        logger.info(
            "Scaling configuration validation successful. "
            "Authorized services: %s",
            ", ".join(allowlist),
        )

    return errors