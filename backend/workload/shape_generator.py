"""
Dynamic Locust LoadTestShape generator for multi-stage DPBPS workload profiles.

Translates WorkloadProfileConfig stage specifications into standard Python Locust
LoadTestShape classes for seamless, in-process concurrency transitions without pod restarts.
"""

from typing import Any, Dict, List, Optional
from .models import WorkloadProfileConfig, WorkloadStage


def generate_locust_shape_stages(config: WorkloadProfileConfig) -> List[Dict[str, Any]]:
    """
    Generate Locust LoadTestShape stage dictionaries from a WorkloadProfileConfig.
    
    Each stage dictionary has:
    - duration: Cumulative runtime seconds up to which this stage applies.
    - users: Target concurrent user count.
    - spawn_rate: Spawn rate during transition to target users.
    """
    locust_stages: List[Dict[str, Any]] = []
    cumulative_time = 0

    if config.stages:
        for stage in config.stages:
            cumulative_time += stage.duration_seconds
            locust_stages.append({
                "duration": cumulative_time,
                "users": stage.target_users,
                "spawn_rate": stage.spawn_rate,
                "name": stage.name,
            })
    else:
        # Default simple ramp-up -> steady -> ramp-down
        ramp_up = config.ramp_up_seconds or 5
        steady = config.steady_state_seconds or 120
        ramp_down = config.ramp_down_seconds or 5

        locust_stages = [
            {"duration": ramp_up, "users": config.users, "spawn_rate": config.spawn_rate, "name": "Ramp-Up"},
            {"duration": ramp_up + steady, "users": config.users, "spawn_rate": config.spawn_rate, "name": "Steady-State"},
            {"duration": ramp_up + steady + ramp_down, "users": 0, "spawn_rate": config.spawn_rate, "name": "Ramp-Down"},
        ]

    return locust_stages


def generate_locust_shape_code(config: WorkloadProfileConfig) -> str:
    """
    Generate standalone Python code defining the LoadTestShape class for Locust.
    This can be mounted or injected into the load generator for dynamic multi-stage execution.
    """
    stages = generate_locust_shape_stages(config)
    code = f'''# Generated Locust LoadTestShape for DPBPS Profile: {config.profile_name.value}
from locust import LoadTestShape

class DPBPSWorkloadShape(LoadTestShape):
    """Dynamically steps through {len(stages)} stages according to DPBPS profile {config.profile_name.value}."""
    
    stages = {stages}

    def tick(self):
        run_time = self.get_run_time()
        for stage in self.stages:
            if run_time < stage["duration"]:
                return (stage["users"], stage["spawn_rate"])
        return None  # Stop test when all stages complete
'''
    return code


def evaluate_shape_tick(stages: List[Dict[str, Any]], run_time: float) -> Optional[tuple]:
    """
    Simulate Locust LoadTestShape tick evaluation at a specific run_time in seconds.
    Returns (target_users, spawn_rate) or None when all stages are complete.
    """
    for stage in stages:
        if run_time < stage["duration"]:
            return (stage["users"], stage["spawn_rate"])
    return None


def generate_combined_locustfile(base_locustfile_path: Any, config: WorkloadProfileConfig) -> str:
    """
    Combine base locustfile tasks with the generated DPBPSWorkloadShape class.
    Produces the complete locustfile ready for ConfigMap injection.
    """
    from pathlib import Path
    path_obj = Path(base_locustfile_path)
    base_code = path_obj.read_text(encoding="utf-8")
    shape_code = generate_locust_shape_code(config)
    return f"{base_code}\n\n# ====================================================================\n# DPBPS DYNAMIC LOAD TEST SHAPE (INJECTED)\n# ====================================================================\n{shape_code}"


