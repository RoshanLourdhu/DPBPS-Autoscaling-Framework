"""
Scaling actuator for DPBPS.

Responsible for safely applying validated scaling decisions through
Docker Compose.

Safety principles:
1. Live scaling must be explicitly enabled.
2. Only explicitly allowlisted services can be scaled.
3. Services with host-port mappings cannot be scaled.
4. Replica limits and maximum replica changes are enforced.
5. Replica count must be verified after scaling.
6. Container health must be verified after scaling.
7. Failed post-scaling verification triggers rollback.
8. Docker commands are executed from the project root.
"""

import logging
import subprocess
import time
from pathlib import Path
from typing import List

import yaml

import backend.config as cfg
from .models import DecisionOutput, DecisionAction, ScalingConfig
from .validation import validate_scaling_configuration


logger = logging.getLogger(__name__)

# Project root:
# backend/scaling/actuator.py -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]

COMPOSE_FILE = PROJECT_ROOT / "docker-compose.yml"


class ScalingError(RuntimeError):
    """Raised when a scaling operation cannot be safely completed."""


# ---------------------------------------------------------------------
# DOCKER COMPOSE CONFIGURATION
# ---------------------------------------------------------------------

def _load_compose_config() -> dict:
    """
    Load the Docker Compose configuration.

    Raises:
        ScalingError: If the Compose file cannot be loaded.
    """

    if not COMPOSE_FILE.exists():
        raise ScalingError(
            f"Docker Compose file not found: {COMPOSE_FILE}"
        )

    try:
        with COMPOSE_FILE.open("r", encoding="utf-8") as file:
            compose = yaml.safe_load(file) or {}

        if not isinstance(compose, dict):
            raise ScalingError(
                "Invalid Docker Compose configuration."
            )

        return compose

    except yaml.YAMLError as exc:
        raise ScalingError(
            f"Unable to parse Docker Compose configuration: {exc}"
        ) from exc

    except OSError as exc:
        raise ScalingError(
            f"Unable to read Docker Compose configuration: {exc}"
        ) from exc


def _get_service_definition(service_name: str) -> dict:
    """Return the Compose definition for a service."""

    compose = _load_compose_config()

    services = compose.get("services", {})

    if service_name not in services:
        raise ScalingError(
            f"Service '{service_name}' does not exist in Docker Compose."
        )

    return services[service_name]


def _service_has_host_port(service_name: str) -> bool:
    """
    Return True if a service defines host-port mappings.

    Services exposing host ports are rejected because multiple replicas
    may attempt to bind the same host port.
    """

    service = _get_service_definition(service_name)

    ports = service.get("ports", [])

    return bool(ports)


def _service_has_health_check(service_name: str) -> bool:
    """Return True if the service defines a Docker healthcheck."""

    service = _get_service_definition(service_name)

    return bool(service.get("healthcheck"))


# ---------------------------------------------------------------------
# DECISION VALIDATION
# ---------------------------------------------------------------------

def _validate_decision(decision: DecisionOutput) -> None:
    """
    Validate a scaling decision before executing Docker commands.

    Validation includes:
    - Global scaling configuration.
    - Explicit service allowlist.
    - Valid scaling action.
    - Replica boundaries.
    - Maximum replica change.
    - Host-port restrictions.
    """

    # 1. Global safety switch
    if not cfg.SCALING_ENABLED:
        raise ScalingError(
            "Live scaling is disabled (SCALING_ENABLED=false)."
        )

    # 2. Require an explicit allowlist
    allowlist = getattr(cfg, "SCALING_ALLOWLIST", [])

    if not allowlist:
        raise ScalingError(
            "Scaling allowlist is empty. No services are authorized for scaling."
        )

    if decision.service_name not in allowlist:
        raise ScalingError(
            f"Service '{decision.service_name}' is not in the scaling allowlist."
        )

    # 3. Validate action
    if decision.action not in {
        DecisionAction.SCALE_UP,
        DecisionAction.SCALE_DOWN,
    }:
        raise ScalingError(
            f"Decision action '{decision.action}' is not a scaling operation."
        )

    # 4. Validate replica configuration
    scaling_config = ScalingConfig()

    min_replicas = scaling_config.min_replicas
    max_replicas = scaling_config.max_replicas
    max_change = scaling_config.max_replica_change

    current_replicas = decision.previous_replicas
    requested_replicas = decision.requested_replicas

    # Validate both current and requested replica counts.
    if (
        current_replicas < min_replicas
        or current_replicas > max_replicas
    ):
        raise ScalingError(
            f"Current replicas {current_replicas} out of allowed range "
            f"[{min_replicas}, {max_replicas}]."
        )

    if (
        requested_replicas < min_replicas
        or requested_replicas > max_replicas
    ):
        raise ScalingError(
            f"Requested replicas {requested_replicas} out of allowed range "
            f"[{min_replicas}, {max_replicas}]."
        )

    # 5. Validate maximum replica change
    replica_change = abs(
        requested_replicas - current_replicas
    )

    if replica_change > max_change:
        raise ScalingError(
            f"Replica change exceeds max allowed per decision "
            f"({max_change})."
        )

    # 6. No-op decisions
    if requested_replicas == current_replicas:
        raise ScalingError(
            f"No replica change required for service '{decision.service_name}'."
        )

    # 7. Validate Compose service definition
    service = _get_service_definition(decision.service_name)

    if not isinstance(service, dict):
        raise ScalingError(
            f"Invalid Compose definition for '{decision.service_name}'."
        )

    # 8. Reject host-port mappings
    if _service_has_host_port(decision.service_name):
        raise ScalingError(
            f"Service '{decision.service_name}' defines a host-port mapping "
            "and cannot be safely scaled."
        )


# ---------------------------------------------------------------------
# DOCKER COMPOSE SCALING
# ---------------------------------------------------------------------

def _run_docker_compose(
    service_name: str,
    replicas: int
) -> None:
    """
    Execute Docker Compose scaling.

    This function executes:

        docker compose -f docker-compose.yml up -d --scale service=count

    Commands are executed from the actual project root.
    """

    command = [
        "docker",
        "compose",
        "-f",
        str(COMPOSE_FILE),
        "up",
        "-d",
        "--scale",
        f"{service_name}={replicas}",
    ]

    logger.info(
        "Executing Docker Compose scaling command: %s",
        " ".join(command),
    )

    try:
        result = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    except (subprocess.TimeoutExpired, TimeoutError) as exc:
        raise ScalingError(
            f"Docker compose scaling timed out for {service_name}: {exc}"
        ) from exc

    except OSError as exc:
        raise ScalingError(
            f"Unable to execute Docker Compose for {service_name}: {exc}"
        ) from exc

    if result.returncode != 0:
        raise ScalingError(
            f"Docker compose scaling failed for {service_name}: "
            f"{result.stderr.strip()}"
        )

    logger.info(
        "Docker Compose scaling command completed for %s: replicas=%d",
        service_name,
        replicas,
    )


# ---------------------------------------------------------------------
# CONTAINER DISCOVERY
# ---------------------------------------------------------------------

def _get_running_container_ids(service_name: str) -> List[str]:
    """
    Retrieve running container IDs for a Compose service.
    """

    command = [
        "docker",
        "compose",
        "-f",
        str(COMPOSE_FILE),
        "ps",
        "-q",
        service_name,
    ]

    try:
        result = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    except (subprocess.TimeoutExpired, TimeoutError) as exc:
        raise ScalingError(
            f"Timed out while listing containers for {service_name}: {exc}"
        ) from exc

    except OSError as exc:
        raise ScalingError(
            f"Failed to list containers for {service_name}: {exc}"
        ) from exc

    if result.returncode != 0:
        raise ScalingError(
            f"docker compose ps error for {service_name}: "
            f"{result.stderr.strip()}"
        )

    container_ids = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]

    running_ids: List[str] = []

    for container_id in container_ids:

        inspect_command = [
            "docker",
            "inspect",
            "-f",
            "{{.State.Running}}",
            container_id,
        ]

        try:
            inspect_result = subprocess.run(
                inspect_command,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )

        except (subprocess.TimeoutExpired, TimeoutError) as exc:
            raise ScalingError(
                f"Timed out inspecting container {container_id}: {exc}"
            ) from exc

        except OSError as exc:
            raise ScalingError(
                f"Failed to inspect container {container_id}: {exc}"
            ) from exc

        if inspect_result.returncode != 0:
            raise ScalingError(
                f"Unable to inspect container {container_id}: "
                f"{inspect_result.stderr.strip()}"
            )

        if inspect_result.stdout.strip().lower() == "true":
            running_ids.append(container_id)

    return running_ids


def get_replica_count(service_name: str) -> int:
    """
    Return the number of running replicas.

    This public helper is intentionally simple so it can be mocked
    during unit testing.
    """

    return len(
        _get_running_container_ids(service_name)
    )


# ---------------------------------------------------------------------
# REPLICA COUNT VERIFICATION
# ---------------------------------------------------------------------

def _verify_replica_count(
    service_name: str,
    expected: int,
    timeout: int = 30,
    interval: int = 1,
) -> None:
    """
    Verify that the expected number of replicas are running.

    Raises:
        ScalingError: If the expected replica count is not reached.
    """

    elapsed = 0
    actual = -1

    while elapsed <= timeout:

        actual = get_replica_count(service_name)

        if actual == expected:
            logger.info(
                "Replica verification successful for %s: %d replicas",
                service_name,
                actual,
            )
            return

        if elapsed == timeout:
            break

        time.sleep(interval)
        elapsed += interval

    raise ScalingError(
        f"Replica count verification failed for {service_name}: "
        f"expected {expected}, observed {actual}."
    )


# ---------------------------------------------------------------------
# HEALTH VERIFICATION
# ---------------------------------------------------------------------

def _verify_replica_health(
    service_name: str,
    timeout: int = 30,
    interval: int = 1,
) -> None:
    """
    Verify that every running replica is healthy.

    This function fails closed:
    - Missing healthcheck is an error.
    - Missing health status is an error.
    - Unhealthy or starting containers are not accepted.
    """

    if not _service_has_health_check(service_name):
        raise ScalingError(
            f"Health verification failed for {service_name}: "
            "no healthcheck is defined in Docker Compose."
        )

    elapsed = 0
    last_unhealthy = []

    while elapsed <= timeout:

        container_ids = _get_running_container_ids(service_name)

        if not container_ids:
            last_unhealthy = [
                ("none", "no running containers")
            ]

        else:
            unhealthy = []

            for container_id in container_ids:

                command = [
                    "docker",
                    "inspect",
                    "-f",
                    "{{.State.Health.Status}}",
                    container_id,
                ]

                try:
                    result = subprocess.run(
                        command,
                        capture_output=True,
                        text=True,
                        timeout=5,
                        check=False,
                    )

                except (subprocess.TimeoutExpired, TimeoutError) as exc:
                    raise ScalingError(
                        f"Health inspection timed out for container "
                        f"{container_id}: {exc}"
                    ) from exc

                except OSError as exc:
                    raise ScalingError(
                        f"Health inspection failed for container "
                        f"{container_id}: {exc}"
                    ) from exc

                if result.returncode != 0:
                    raise ScalingError(
                        f"Health inspection failed for container "
                        f"{container_id}: {result.stderr.strip()}"
                    )

                status = result.stdout.strip().lower()

                if not status:
                    raise ScalingError(
                        f"Health verification failed for container "
                        f"{container_id}: no health status is available."
                    )

                if status != "healthy":
                    unhealthy.append(
                        (container_id, status)
                    )

            if not unhealthy:
                logger.info(
                    "All replicas of %s are healthy.",
                    service_name,
                )
                return

            last_unhealthy = unhealthy

        if elapsed == timeout:
            break

        time.sleep(interval)
        elapsed += interval

    container_id, status = last_unhealthy[0]

    raise ScalingError(
        f"Health verification failed for {service_name}: "
        f"container {container_id} status '{status}'."
    )


# ---------------------------------------------------------------------
# ROLLBACK
# ---------------------------------------------------------------------

def _rollback_service(
    service_name: str,
    original_replicas: int,
) -> None:
    """
    Attempt to restore the original replica count.

    Rollback failures are propagated to the caller.
    """

    logger.warning(
        "Attempting rollback for %s to %d replicas.",
        service_name,
        original_replicas,
    )

    try:
        _run_docker_compose(
            service_name,
            original_replicas,
        )

        _verify_replica_count(
            service_name,
            original_replicas,
        )

        logger.info(
            "Rollback completed for %s.",
            service_name,
        )

    except ScalingError as exc:
        raise ScalingError(
            f"Rollback failed for {service_name}: {exc}"
        ) from exc


# ---------------------------------------------------------------------
# APPLY SINGLE DECISION
# ---------------------------------------------------------------------

def apply_decision(decision: DecisionOutput) -> None:
    """
    Validate and apply a single DPBPS scaling decision.

    Scaling is performed only after all safety checks pass.

    If replica-count or health verification fails after the scaling
    command succeeds, the actuator attempts to restore the original
    replica count.
    """

    scaling_attempted = False
    original_count = decision.previous_replicas

    try:

        # Step 1: Validate the decision
        _validate_decision(decision)

        # Step 2: Execute scaling
        _run_docker_compose(
            decision.service_name,
            decision.requested_replicas,
        )

        # The scaling command completed successfully.
        scaling_attempted = True

        # Step 3: Verify replica count
        _verify_replica_count(
            decision.service_name,
            decision.requested_replicas,
        )

        # Step 4: Verify replica health
        _verify_replica_health(
            decision.service_name,
        )

        logger.info(
            "Scaling operation completed successfully: "
            "%s -> %d replicas",
            decision.service_name,
            decision.requested_replicas,
        )

    except ScalingError as exc:

        logger.error(
            "Scaling operation failed for %s: %s",
            decision.service_name,
            exc,
        )

        # Rollback only if the scaling command succeeded.
        if scaling_attempted:

            try:
                _rollback_service(
                    decision.service_name,
                    original_count,
                )

            except ScalingError as rollback_error:
                logger.critical(
                    "Rollback failed for %s: %s",
                    decision.service_name,
                    rollback_error,
                )

                raise rollback_error from exc

        raise


# ---------------------------------------------------------------------
# APPLY MULTIPLE DECISIONS
# ---------------------------------------------------------------------

def apply_decisions(
    decisions: List[DecisionOutput],
) -> None:
    """
    Apply multiple scaling decisions sequentially.

    The first failure stops further processing.

    Before executing any scaling command, the actuator validates
    the global scaling configuration.
    """

    # Global safety check
    if not cfg.SCALING_ENABLED:
        raise ScalingError(
            "Live scaling is disabled (SCALING_ENABLED=false)."
        )

    # Validate the scaling configuration
    errors = validate_scaling_configuration()

    if errors:
        raise ScalingError(
            "Scaling configuration validation failed: "
            + "; ".join(errors)
        )

    # Apply decisions sequentially
    for decision in decisions:

        apply_decision(decision)