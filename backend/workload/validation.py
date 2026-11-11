"""
Validation logic and safety guardrails for workload profile configurations.

Enforces constraints to prevent unintentional denial-of-service, cluster overload,
or system thrashing during experiment preparation.
"""

from typing import List, Tuple
from .models import WorkloadProfileConfig, WorkloadProfileName


MAX_ALLOWED_USERS = 200
MIN_ALLOWED_USERS = 1
MAX_ALLOWED_SPAWN_RATE = 50.0
MIN_ALLOWED_SPAWN_RATE = 0.1
MAX_DURATION_SECONDS = 1200  # 20 minutes
MIN_DURATION_SECONDS = 10


class WorkloadValidationError(ValueError):
    """Raised when a workload configuration violates safety invariants."""
    pass


def validate_workload_config(config: WorkloadProfileConfig) -> Tuple[bool, List[str]]:
    """
    Validate a workload configuration against strict safety envelopes.
    
    Returns:
        (is_valid, list_of_errors_or_warnings)
    """
    errors: List[str] = []

    # 1. Concurrency limits
    if config.users < MIN_ALLOWED_USERS:
        errors.append(f"users ({config.users}) must be at least {MIN_ALLOWED_USERS}")
    elif config.users > MAX_ALLOWED_USERS:
        errors.append(f"users ({config.users}) exceeds safety limit of {MAX_ALLOWED_USERS}")

    # 2. Spawn rate limits
    if config.spawn_rate < MIN_ALLOWED_SPAWN_RATE:
        errors.append(f"spawn_rate ({config.spawn_rate}) must be at least {MIN_ALLOWED_SPAWN_RATE}")
    elif config.spawn_rate > MAX_ALLOWED_SPAWN_RATE:
        errors.append(f"spawn_rate ({config.spawn_rate}) exceeds safety limit of {MAX_ALLOWED_SPAWN_RATE}")

    # 3. Duration limits
    if config.total_duration_seconds < MIN_DURATION_SECONDS:
        errors.append(f"total_duration_seconds ({config.total_duration_seconds}) must be at least {MIN_DURATION_SECONDS}s")
    elif config.total_duration_seconds > MAX_DURATION_SECONDS:
        errors.append(f"total_duration_seconds ({config.total_duration_seconds}) exceeds safety limit of {MAX_DURATION_SECONDS}s")

    # 4. Target host validation
    if not config.target_host or not config.target_host.strip():
        errors.append("target_host must not be empty")

    # 5. Stage validation
    if config.stages:
        stage_total_duration = sum(s.duration_seconds for s in config.stages)
        if abs(stage_total_duration - config.total_duration_seconds) > 5:
            errors.append(
                f"Sum of stage durations ({stage_total_duration}s) does not match total_duration_seconds ({config.total_duration_seconds}s)"
            )
        for s in config.stages:
            if s.target_users > MAX_ALLOWED_USERS:
                errors.append(f"Stage '{s.name}' target_users ({s.target_users}) exceeds {MAX_ALLOWED_USERS}")

    return len(errors) == 0, errors

