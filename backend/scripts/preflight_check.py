#!/usr/bin/env python3
"""Pre‑flight checklist – safe, read‑only validation before any live scaling.

This script performs a series of non‑destructive checks to ensure that the
Docker environment, compose configuration, required containers, health status,
scaling flag, and disk space are all in a known good state before a controlled
experiment is run.

All failures are reported as clear messages; no credentials or secrets are
printed. The script never starts, stops, restarts or recreates containers.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def docker_available() -> bool:
    """Check that the Docker daemon responds to ``docker version``.
    Returns ``True`` if the command exits with code 0, otherwise prints an
    error and returns ``False``.
    """
    try:
        subprocess.run(["docker", "version"], capture_output=True, timeout=5, check=True)
        return True
    except Exception as e:
        print(f"[ERROR] Docker daemon not reachable: {e}", file=sys.stderr)
        return False

def compose_valid() -> bool:
    """Validate the compose file using ``docker compose config`` in the project root.
    The command prints the merged configuration; ``--quiet`` suppresses output.
    """
    try:
        subprocess.run(
            ["docker", "compose", "config", "--quiet"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            timeout=10,
            check=True,
        )
        return True
    except Exception as e:
        print(f"[ERROR] docker‑compose configuration invalid: {e}", file=sys.stderr)
        return False

def required_containers_running() -> bool:
    """Ensure that the four stateless services, postgres, and frontend are up.
    Uses ``docker compose ps --services`` to list *running* services and then
    verifies each expected service appears in the list.
    """
    expected = {
        "product-service",
        "cart-service",
        "checkout-service",
        "recommendation-service",
        "postgres",
        "frontend",
    }
    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "--services"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        running = {s.strip() for s in result.stdout.splitlines() if s.strip()}
        missing = expected - running
        if missing:
            print(f"[WARN] Services not running: {', '.join(sorted(missing))}", file=sys.stderr)
            return False
        return True
    except Exception as e:
        print(f"[ERROR] Unable to query running services: {e}", file=sys.stderr)
        return False

def health_checks() -> bool:
    """Perform a Docker‑level health‑check for services that define one.
    ``docker compose ps -q <service>`` returns container IDs; for each ID we ask
    Docker for its health status via ``docker inspect``. If any container reports
    a non‑healthy state, the function returns ``False``.
    """
    services = [
        "product-service",
        "cart-service",
        "checkout-service",
        "recommendation-service",
        "orchestration-api",
        "frontend",
    ]
    all_ok = True
    for svc in services:
        try:
            # List container IDs for the service
            result = subprocess.run(
                ["docker", "compose", "ps", "-q", svc],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            ids = [cid for cid in result.stdout.splitlines() if cid.strip()]
            for cid in ids:
                inspect = subprocess.run(
                    ["docker", "inspect", "-f", "{{.State.Health.Status}}", cid],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                status = inspect.stdout.strip()
                if status and status != "healthy":
                    print(f"[WARN] Service {svc} container {cid[:12]} health: {status}", file=sys.stderr)
                    all_ok = False
        except Exception as e:
            # If a service has no health check Docker returns an empty string – ignore.
            continue
    return all_ok

def scaling_flag_disabled() -> bool:
    """Confirm that the environment variable controlling live scaling is *false*.
    The script checks the process environment; the actual API reads the variable
    at request time, so the check here simply documents the current setting.
    """
    enabled = os.getenv("SCALING_ENABLED", "false").lower() == "true"
    if enabled:
        print("[WARN] SCALING_ENABLED is TRUE – live scaling must remain disabled for the audit.", file=sys.stderr)
    return not enabled

def disk_space() -> bool:
    """Require at least 2 GiB free space in the project directory.
    This mirrors the check used by the experiment runner.
    """
    total, used, free = shutil.disk_usage(PROJECT_ROOT)
    if free < 2 * 1024 ** 3:
        print("[WARN] Low free disk space (<2 GiB) in project directory.", file=sys.stderr)
        return False
    return True

def main():
    checks = {
        "Docker daemon reachable": docker_available(),
        "Compose file valid": compose_valid(),
        "Required containers running": required_containers_running(),
        "Docker‑level health checks": health_checks(),
        "Scaling flag disabled": scaling_flag_disabled(),
        "Sufficient disk space": disk_space(),
    }

    print("\n--- Pre‑flight check results ---")
    for name, ok in checks.items():
        print(f"{name:35}: {'OK' if ok else 'FAIL'}")

    if all(checks.values()):
        print("\nAll pre‑flight checks passed. Ready for a controlled scaling experiment.")
    else:
        print("\nOne or more checks failed – resolve the issues before proceeding.")

if __name__ == "__main__":
    main()
