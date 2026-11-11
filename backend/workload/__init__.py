"""
Workload generation package for DPBPS platform.
"""

from .models import (
    WorkloadProfileName,
    WorkloadProfileConfig,
    WorkloadStage,
)
from .profiles import (
    CANONICAL_PROFILES,
    get_profile,
    get_all_profiles,
    get_normal_traffic_profile,
    get_gradual_traffic_increase_profile,
    get_sudden_traffic_spike_profile,
    get_sustained_high_traffic_profile,
    get_traffic_decrease_profile,
    get_bursty_traffic_profile,
)
from .validation import (
    validate_workload_config,
    WorkloadValidationError,
    MAX_ALLOWED_USERS,
    MIN_ALLOWED_USERS,
)
from .shape_generator import (
    generate_locust_shape_stages,
    generate_locust_shape_code,
    evaluate_shape_tick,
    generate_combined_locustfile,
)

__all__ = [
    "WorkloadProfileName",
    "WorkloadProfileConfig",
    "WorkloadStage",
    "CANONICAL_PROFILES",
    "get_profile",
    "get_all_profiles",
    "get_normal_traffic_profile",
    "get_gradual_traffic_increase_profile",
    "get_sudden_traffic_spike_profile",
    "get_sustained_high_traffic_profile",
    "get_traffic_decrease_profile",
    "get_bursty_traffic_profile",
    "validate_workload_config",
    "WorkloadValidationError",
    "MAX_ALLOWED_USERS",
    "MIN_ALLOWED_USERS",
    "generate_locust_shape_stages",
    "generate_locust_shape_code",
    "evaluate_shape_tick",
    "generate_combined_locustfile",
]

