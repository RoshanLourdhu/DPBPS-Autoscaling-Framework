# backend/scaling/validation.py
"""Utility functions for validating scaling configuration against Docker Compose.
These are used by tests to ensure safe static configuration before any live scaling.
"""
import os
import yaml
from typing import List

COMPOSE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "docker-compose.yml"))

def load_compose() -> dict:
    """Load the docker-compose.yml file as a dict."""
    with open(COMPOSE_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def get_service_definitions(compose: dict) -> dict:
    """Return the mapping of service name to its definition dict."""
    return compose.get("services", {})

def get_scaling_allowlist() -> List[str]:
    """Return the allowlist parsed from the environment variable.
    Empty string yields empty list.
    """
    raw = os.getenv("SCALING_ALLOWLIST", "")
    return [s.strip() for s in raw.split(",") if s.strip()]

def validate_scaling_configuration() -> List[str]:
    """Validate that:
    * Every service in SCALING_ALLOWLIST exists in compose.
    * Allowlisted services do not publish host ports.
    * Stateful services like "postgres" are not in the allowlist.
    Returns a list of error messages (empty if ok)."""
    errors: List[str] = []
    compose = load_compose()
    services = get_service_definitions(compose)
    allowlist = get_scaling_allowlist()

    for svc in allowlist:
        if svc not in services:
            errors.append(f"Allowlisted service '{svc}' not found in docker-compose.yml.")
        else:
            # Check for host‑port mappings
            if "ports" in services[svc]:
                errors.append(f"Allowlisted service '{svc}' publishes host ports, which prevents safe scaling.")
        # Disallow scaling of known stateful services
        if svc == "postgres" or svc == "frontend":
            errors.append(f"Stateful service '{svc}' must not be in SCALING_ALLOWLIST.")
    return errors
