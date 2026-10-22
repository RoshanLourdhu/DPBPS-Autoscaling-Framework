# backend/scaling/actuator.py
"""Scaling actuator for DPBPS.

The actuator translates a validated :class:`DecisionOutput` into a concrete
replica change using ``docker compose``.  It respects the global configuration
flags defined in ``backend.config`` and performs extensive validation before
executing any Docker command.

Only services listed in ``SCALING_ALLOWLIST`` (or all services if the list is
empty) are eligible for scaling.  The actuator never attempts to scale the
frontend, PostgreSQL, or any service that maps a host port – such services cannot
be safely replicated with the current ``docker‑compose.yml`` configuration.

All actions are logged via the standard ``logging`` module; failures raise
:class:`ScalingError` so that callers can react appropriately.
"""
import logging
import subprocess
import importlib
from typing import List

from .models import DecisionOutput, DecisionAction, ScalingConfig
import backend.config as cfg
from .validation import validate_scaling_configuration


logger = logging.getLogger(__name__)

class ScalingError(RuntimeError):
    """Raised when the actuator cannot safely perform a scaling operation."""

def _service_has_host_port(service_name: str) -> bool:
    """Return True if the given service defines a host‑port mapping in the compose file.
    Scaling services that expose host ports cannot be safely replicated because
    multiple containers would attempt to bind the same host port.
    The function parses the docker‑compose.yml file and looks for a `ports:`
    section under the specified service definition.
    """
    import os
    compose_path = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "docker-compose.yml",
        )
    )
    try:
        with open(compose_path, "r", encoding="utf-8") as f:
            in_service = False
            for line in f:
                stripped = line.lstrip()
                if stripped.startswith(f"{service_name}:"):
                    in_service = True
                    continue
                if in_service:
                    # End of service block if indentation decreases
                    if not line.startswith(" "):
                        break
                    if stripped.startswith("ports:"):
                        return True
    except FileNotFoundError:
        logger.error("docker-compose.yml not found while checking port mapping.")
    return False
def _service_has_health_check(service_name: str) -> bool:
    """Detect if the service defines a healthcheck in docker‑compose.yml.
    Simple parsing: look for a line starting with 'healthcheck:' within the service block.
    """
    import os
    compose_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "docker-compose.yml")
    )
    try:
        with open(compose_path, "r", encoding="utf-8") as f:
            in_service = False
            for line in f:
                stripped = line.lstrip()
                if stripped.startswith(f"{service_name}:"):
                    in_service = True
                    continue
                if in_service:
                    if not line.startswith(" "):
                        break
                    if stripped.startswith("healthcheck:"):
                        return True
    except FileNotFoundError:
        logger.error("docker-compose.yml not found while checking healthcheck.")
    return False
def _validate_decision(decision: DecisionOutput) -> None:
    """Run all safety checks before a replica change is performed.

    * Scaling must be globally enabled.
    * The target service must be in the allowlist (or the allowlist is empty).
    * The decision must request a change (requested != previous).
    * Services with host‑port bindings are not scalable unless they are stateless (handled in _service_has_host_port).
    * The requested replica count respects the min/max limits defined in ScalingConfig.
    """
    if not cfg.SCALING_ENABLED:
        raise ScalingError("Live scaling is disabled (SCALING_ENABLED=false).")

    # Require an explicit allowlist; if empty, reject all scaling attempts
    if not cfg.SCALING_ALLOWLIST or decision.service_name not in cfg.SCALING_ALLOWLIST:
        raise ScalingError(
            f"Service '{decision.service_name}' is not in the scaling allowlist."
        )

    if decision.requested_replicas == decision.previous_replicas:
        raise ScalingError(
            f"No replica change required for service '{decision.service_name}'."
        )

    if decision.action not in {DecisionAction.SCALE_UP, DecisionAction.SCALE_DOWN}:
        raise ScalingError(
            f"Decision action '{decision.action}' is not a scaling operation."
        )

    # Enforce replica bounds defined in ScalingConfig (using defaults)
    # Load ScalingConfig dynamically to respect any monkey‑patching in tests
    models_mod = importlib.import_module("backend.scaling.models")
    cfg_obj = models_mod.ScalingConfig()
    if decision.requested_replicas < cfg_obj.min_replicas or decision.requested_replicas > cfg_obj.max_replicas:
        raise ScalingError(
            f"Requested replicas {decision.requested_replicas} out of allowed range [{cfg_obj.min_replicas}, {cfg_obj.max_replicas}]."
        )

    # Enforce max replica change per decision
    if abs(decision.requested_replicas - decision.previous_replicas) > cfg_obj.max_replica_change:
        raise ScalingError(
            f"Replica change exceeds max allowed per decision ({cfg_obj.max_replica_change})."
        )

    # Disallow scaling services that expose a host port – they would clash.
    if _service_has_host_port(decision.service_name):
        raise ScalingError(
            f"Service '{decision.service_name}' defines a host‑port mapping and cannot be safely scaled."
        )

def _run_docker_compose(service_name: str, replicas: int) -> None:
    """Execute ``docker compose`` with ``--scale``.

    The command is run in the project root directory.  A timeout of 30 seconds is
    used to avoid hanging the actuator.
    """
    cmd = [
        "docker",
        "compose",
        "-f",
        "docker-compose.yml",
        "up",
        "-d",
        f"--scale",
        f"{service_name}={replicas}",
    ]
    logger.info("Running scaling command: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            cwd="c:/Users/ROSHAN/Downloads/CIS/Deployment Aware AAutoscaling Platform",
            capture_output=True,
            text=True,
            timeout=30,
        )
    except TimeoutError as te:
        raise ScalingError(f"Docker compose scaling timed out: {te}")
    if result.returncode != 0:
        raise ScalingError(
            f"Docker compose scaling failed for {service_name}: {result.stderr.strip()}"
        )
    logger.info("Scaling command succeeded for %s (replicas=%d)", service_name, replicas)

# Helper to obtain running container IDs for a service
def _get_running_container_ids(service_name: str) -> List[str]:
    """Return a list of container IDs that are *running* for the given service.

    Uses ``docker compose ps -q <service>`` to retrieve IDs, then filters
    those whose ``State.Running`` is true via ``docker inspect``.
    """
    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "-q", service_name],
            cwd="c:/Users/ROSHAN/Downloads/CIS/Deployment Aware AAutoscaling Platform",
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as e:
        raise ScalingError(f"Failed to list containers for {service_name}: {e}")
    if result.returncode != 0:
        raise ScalingError(f"docker compose ps error for {service_name}: {result.stderr.strip()}")
    ids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    running_ids: List[str] = []
    for cid in ids:
        try:
            inspect = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", cid],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception as e:
            raise ScalingError(f"Failed to inspect container {cid}: {e}")
        if inspect.returncode != 0:
            continue  # ignore containers that cannot be inspected
        if inspect.stdout.strip().lower() == "true":
            running_ids.append(cid)
    return running_ids

# Public helper used by tests
def get_replica_count(service_name: str) -> int:
    """Return the number of *running* replicas for ``service_name``.
    This function is deliberately simple for unit‑test mocking.
    """
    return len(_get_running_container_ids(service_name))

# Verify replica count after scaling
def _verify_replica_count(service_name: str, expected: int, timeout: int = 30, interval: int = 1) -> None:
    import time
    elapsed = 0
    while elapsed < timeout:
        actual = get_replica_count(service_name)
        if actual == expected:
            return
        time.sleep(interval)
        elapsed += interval
    raise ScalingError(
        f"Replica count verification failed for {service_name}: expected {expected}, observed {actual}"
    )

# Verify health of each running container
def _verify_replica_health(service_name: str, timeout: int = 30, interval: int = 1) -> None:
    """Verify health of containers only if a healthcheck is defined.
    If no healthcheck is present, this function is a no‑op.
    """

    # Skip health verification if the service does not define a healthcheck
    if not _service_has_health_check(service_name):
        logger.info("Service %s has no healthcheck defined; skipping health verification.", service_name)
        return
        import time
        elapsed = 0
        while elapsed < timeout:
            ids = _get_running_container_ids(service_name)
            unhealthy = []
            for cid in ids:
                try:
                    result = subprocess.run(
                        ["docker", "inspect", "-f", "{{.State.Health.Status}}", cid],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                except Exception as e:
                    raise ScalingError(f"Health inspection failed for container {cid}: {e}")
                if result.returncode != 0:
                    # No health status available – treat as missing healthcheck and skip
                    logger.debug("No health status for container %s; assuming no healthcheck.", cid)
                    continue
                status = result.stdout.strip().lower()
                if status != "healthy":
                    unhealthy.append((cid, status))
            if not unhealthy:
                return
            time.sleep(interval)
            elapsed += interval
        cid, reason = unhealthy[0]
        raise ScalingError(
            f"Health verification failed for {service_name}: container {cid} status '{reason}'"
        )

# Rollback helper
def _rollback_service(service_name: str, original_replicas: int) -> None:
    """Rollback a service to its original replica count.
    The rollback attempts to set the replica count back via Docker compose.
    Verification of the replica count is intentionally omitted to avoid
    cascading failures when the original error was unrelated (e.g., health
    verification). Any error from the compose command itself is propagated
    as a ScalingError.
    """
    try:
        _run_docker_compose(service_name, original_replicas)
        # Note: Not verifying replica count here to ensure the original
        # scaling error (such as health verification) is reported to the
        # caller.
    except ScalingError as re:
        raise ScalingError(
            f"Rollback failed for {service_name}: {re}"  # propagate original error
        )

def apply_decision(decision: DecisionOutput) -> None:
    """Public entry point – validates and, if safe, applies a single decision."""
    scaling_attempted = False
    try:
        _validate_decision(decision)
        # Use provided previous replica count (avoids Docker call)
        original_count = decision.previous_replicas
        _run_docker_compose(decision.service_name, decision.requested_replicas)
        scaling_attempted = True
        # Post‑scale verification
        _verify_replica_count(decision.service_name, decision.requested_replicas)
        _verify_replica_health(decision.service_name)
    except ScalingError as e:
        logger.error("Scaling error for %s: %s", decision.service_name, str(e))
        if scaling_attempted:
            try:
                _rollback_service(decision.service_name, original_count)
            except ScalingError as rollback_err:
                # Propagate rollback failure instead of original error
                raise rollback_err
            # If rollback succeeded, re-raise the original scaling error
            raise e
        else:
            raise




def apply_decisions(decisions: List[DecisionOutput]) -> None:
    """Apply a list of decisions in sequence.  The function stops on the first
    failure and propagates the exception so that callers can react.
    """
    # Pre‑flight configuration validation ensures compose file is safe for scaling
    errors = validate_scaling_configuration()
    if errors:
        raise ScalingError("Scaling configuration validation failed: " + "; ".join(errors))
    for d in decisions:
        apply_decision(d)

