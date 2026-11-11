"""
Canonical workload profile specifications for DPBPS evaluation.

Provides the reference configurations for all six evaluation profiles:
1. NORMAL_TRAFFIC
2. GRADUAL_TRAFFIC_INCREASE
3. SUDDEN_TRAFFIC_SPIKE
4. SUSTAINED_HIGH_TRAFFIC
5. TRAFFIC_DECREASE
6. BURSTY_TRAFFIC
"""

from typing import Dict, List, Optional
from .models import WorkloadProfileConfig, WorkloadProfileName, WorkloadStage


def get_normal_traffic_profile() -> WorkloadProfileConfig:
    """Profile 1: NORMAL_TRAFFIC – Establish baseline application behavior."""
    return WorkloadProfileConfig(
        profile_name=WorkloadProfileName.NORMAL_TRAFFIC,
        display_name="Profile 1: Normal Traffic (Baseline)",
        description=(
            "Establishes baseline application behavior under steady, low-volume traffic. "
            "Evaluates whether the controller remains stable without unnecessary scaling."
        ),
        target_host="frontend:80",
        users=10,
        spawn_rate=2.0,
        ramp_up_seconds=5,
        steady_state_seconds=120,
        ramp_down_seconds=5,
        total_duration_seconds=130,
        stages=[
            WorkloadStage(
                stage_index=0,
                name="Ramp-Up",
                target_users=10,
                duration_seconds=5,
                spawn_rate=2.0,
                description="Gradual ramp to baseline 10 users",
            ),
            WorkloadStage(
                stage_index=1,
                name="Steady Baseline",
                target_users=10,
                duration_seconds=120,
                spawn_rate=2.0,
                description="Steady state baseline observation window",
            ),
            WorkloadStage(
                stage_index=2,
                name="Ramp-Down",
                target_users=0,
                duration_seconds=5,
                spawn_rate=2.0,
                description="Controlled termination",
            ),
        ],
        expected_observations=[
            "Stable request rate (approx. 10-15 RPS aggregate)",
            "Baseline P95 latency well within 200ms target (< 40ms)",
            "Error rate remains at 0.0%",
            "Low CPU (< 20%) and memory utilization across all 10 services",
            "DPBPS decision: HOLD across all services; zero bottleneck identified",
        ],
        custom_parameters={"target_rps_approx": 12, "traffic_pattern": "constant"},
    )


def get_gradual_traffic_increase_profile() -> WorkloadProfileConfig:
    """Profile 2: GRADUAL_TRAFFIC_INCREASE – Evaluate progressive scaling response."""
    return WorkloadProfileConfig(
        profile_name=WorkloadProfileName.GRADUAL_TRAFFIC_INCREASE,
        display_name="Profile 2: Gradual Traffic Increase (Stepped)",
        description=(
            "Progressively increases traffic in 3 discrete steps (10 -> 25 -> 50 users). "
            "Each step is held long enough (60s) for multiple Prometheus scrape cycles (15s)."
        ),
        target_host="frontend:80",
        users=50,
        spawn_rate=2.0,
        ramp_up_seconds=10,
        steady_state_seconds=160,
        ramp_down_seconds=10,
        total_duration_seconds=180,
        stages=[
            WorkloadStage(
                stage_index=0,
                name="Step 1: Low Concurrency",
                target_users=10,
                duration_seconds=60,
                spawn_rate=2.0,
                description="Initial light load tier (10 users)",
            ),
            WorkloadStage(
                stage_index=1,
                name="Step 2: Moderate Concurrency",
                target_users=25,
                duration_seconds=60,
                spawn_rate=2.0,
                description="Intermediate load tier (25 users)",
            ),
            WorkloadStage(
                stage_index=2,
                name="Step 3: High Concurrency",
                target_users=50,
                duration_seconds=60,
                spawn_rate=2.0,
                description="Peak load tier (50 users) driving resource pressure",
            ),
        ],
        expected_observations=[
            "Monotonically increasing request rate stepping from 15 to 65 RPS",
            "Progressive rise in P95 latency, especially in cartservice and productcatalogservice",
            "CPU pressure exceeds 50% threshold on critical leaf nodes",
            "Bottleneck detector flags the primary latency-inducing downstream dependency",
            "DPBPS proposes prioritized scale-up decisions (+1 to +2 replicas)",
        ],
        custom_parameters={"steps": [10, 25, 50], "step_duration_sec": 60},
    )


def get_sudden_traffic_spike_profile() -> WorkloadProfileConfig:
    """Profile 3: SUDDEN_TRAFFIC_SPIKE – Evaluate rapid pressure detection."""
    return WorkloadProfileConfig(
        profile_name=WorkloadProfileName.SUDDEN_TRAFFIC_SPIKE,
        display_name="Profile 3: Sudden Traffic Spike (Surge)",
        description=(
            "Establishes a 5-user baseline for 30s, then injects a sharp surge to 80 users "
            "at 20 users/sec, maintains peak for 60s, then recovers back to 5 users."
        ),
        target_host="frontend:80",
        users=80,
        spawn_rate=20.0,
        ramp_up_seconds=5,
        steady_state_seconds=60,
        ramp_down_seconds=5,
        total_duration_seconds=120,
        stages=[
            WorkloadStage(
                stage_index=0,
                name="Pre-Spike Baseline",
                target_users=5,
                duration_seconds=30,
                spawn_rate=20.0,
                description="Quiet baseline before spike arrival",
            ),
            WorkloadStage(
                stage_index=1,
                name="Sharp Spike Peak",
                target_users=80,
                duration_seconds=60,
                spawn_rate=20.0,
                description="Aggressive traffic surge challenging queue depths",
            ),
            WorkloadStage(
                stage_index=2,
                name="Post-Spike Recovery",
                target_users=5,
                duration_seconds=30,
                spawn_rate=20.0,
                description="Rapid reduction back to baseline",
            ),
        ],
        expected_observations=[
            "Sharp inflection in request rate (~5 RPS to ~100+ RPS within seconds)",
            "P95 latency spike and temporary queue buildup",
            "Rapid bottleneck detection identifying root-cause service",
            "Proposed scale-up bounded by max delta rule (<= 2 replicas per evaluation)",
            "Absence of cluster over-allocation shock",
        ],
        custom_parameters={"spike_users": 80, "spike_spawn_rate": 20.0},
    )


def get_sustained_high_traffic_profile() -> WorkloadProfileConfig:
    """Profile 4: SUSTAINED_HIGH_TRAFFIC – Evaluate continuous elevated demand."""
    return WorkloadProfileConfig(
        profile_name=WorkloadProfileName.SUSTAINED_HIGH_TRAFFIC,
        display_name="Profile 4: Sustained High Traffic (Saturation)",
        description=(
            "Ramps up to 60 users over 20s and maintains continuous high load for 180s. "
            "Evaluates controller stability and whether replica counts remain steady without flapping."
        ),
        target_host="frontend:80",
        users=60,
        spawn_rate=5.0,
        ramp_up_seconds=20,
        steady_state_seconds=180,
        ramp_down_seconds=20,
        total_duration_seconds=220,
        stages=[
            WorkloadStage(
                stage_index=0,
                name="Controlled Ramp-Up",
                target_users=60,
                duration_seconds=20,
                spawn_rate=5.0,
                description="Controlled user ramp to saturation point",
            ),
            WorkloadStage(
                stage_index=1,
                name="Sustained High Load",
                target_users=60,
                duration_seconds=180,
                spawn_rate=5.0,
                description="Extended saturation plateau spanning 12 scrape intervals",
            ),
            WorkloadStage(
                stage_index=2,
                name="Controlled Ramp-Down",
                target_users=0,
                duration_seconds=20,
                spawn_rate=5.0,
                description="Orderly traffic cessation",
            ),
        ],
        expected_observations=[
            "Sustained elevated request rate (~70-85 RPS)",
            "Persistent resource pressure across tiers",
            "Bottleneck service remains consistent throughout saturation window",
            "Target replicas stabilize at optimum tier without repeated flapping",
            "Zero unhandled exceptions or crash-loops",
        ],
        custom_parameters={"sustained_users": 60, "plateau_duration_sec": 180},
    )


def get_traffic_decrease_profile() -> WorkloadProfileConfig:
    """Profile 5: TRAFFIC_DECREASE – Evaluate scale-down behavior."""
    return WorkloadProfileConfig(
        profile_name=WorkloadProfileName.TRAFFIC_DECREASE,
        display_name="Profile 5: Traffic Decrease (Scale-Down)",
        description=(
            "Starts at high load (50 users for 60s) then steps down through 25 users (60s) "
            "to 5 users (60s). Evaluates scale-down cooldown enforcement (120s) and rollout protection."
        ),
        target_host="frontend:80",
        users=50,
        spawn_rate=5.0,
        ramp_up_seconds=10,
        steady_state_seconds=160,
        ramp_down_seconds=10,
        total_duration_seconds=180,
        stages=[
            WorkloadStage(
                stage_index=0,
                name="High Load Tier",
                target_users=50,
                duration_seconds=60,
                spawn_rate=5.0,
                description="High load to establish scaling state",
            ),
            WorkloadStage(
                stage_index=1,
                name="Intermediate Tier",
                target_users=25,
                duration_seconds=60,
                spawn_rate=5.0,
                description="Reduced load tier triggering cooldown tracking",
            ),
            WorkloadStage(
                stage_index=2,
                name="Low Baseline Tier",
                target_users=5,
                duration_seconds=60,
                spawn_rate=5.0,
                description="Return to minimum baseline load",
            ),
        ],
        expected_observations=[
            "Orderly pressure reduction across all services",
            "Scale-down decisions strictly held until scale_down_window_sec (120s) expires",
            "Deployment-phase guardrails prevent scale-down if phase is ACTIVE_DEPLOYMENT",
            "Replica recommendations decrement safely by at most max_replica_change (2)",
            "Replica floor at 1 is strictly observed",
        ],
        custom_parameters={"step_down_sequence": [50, 25, 5], "step_sec": 60},
    )


def get_bursty_traffic_profile() -> WorkloadProfileConfig:
    """Profile 6: BURSTY_TRAFFIC – Evaluate anti-flapping and damping."""
    return WorkloadProfileConfig(
        profile_name=WorkloadProfileName.BURSTY_TRAFFIC,
        display_name="Profile 6: Bursty Traffic (Oscillation Test)",
        description=(
            "Alternates between sharp bursts (60 users for 20s) and quiet lulls (5 users for 20s) "
            "across 4 cycles (160s total). Evaluates controller damping against scaling thrashing."
        ),
        target_host="frontend:80",
        users=60,
        spawn_rate=20.0,
        ramp_up_seconds=5,
        steady_state_seconds=150,
        ramp_down_seconds=5,
        total_duration_seconds=160,
        stages=[
            WorkloadStage(stage_index=0, name="Burst 1", target_users=60, duration_seconds=20, spawn_rate=20.0),
            WorkloadStage(stage_index=1, name="Lull 1", target_users=5, duration_seconds=20, spawn_rate=20.0),
            WorkloadStage(stage_index=2, name="Burst 2", target_users=60, duration_seconds=20, spawn_rate=20.0),
            WorkloadStage(stage_index=3, name="Lull 2", target_users=5, duration_seconds=20, spawn_rate=20.0),
            WorkloadStage(stage_index=4, name="Burst 3", target_users=60, duration_seconds=20, spawn_rate=20.0),
            WorkloadStage(stage_index=5, name="Lull 3", target_users=5, duration_seconds=20, spawn_rate=20.0),
            WorkloadStage(stage_index=6, name="Burst 4", target_users=60, duration_seconds=20, spawn_rate=20.0),
            WorkloadStage(stage_index=7, name="Lull 4 (Recovery)", target_users=5, duration_seconds=20, spawn_rate=20.0),
        ],
        expected_observations=[
            "Intermittent traffic pulses alternating between ~10 RPS and ~80 RPS",
            "Cooldown timers dampen transient surges, preventing premature scale-down during lulls",
            "Zero high-frequency scaling oscillation (thrashing)",
            "Stable average replica posture under turbulent workload conditions",
        ],
        custom_parameters={"burst_users": 60, "lull_users": 5, "cycle_count": 4, "period_sec": 40},
    )


CANONICAL_PROFILES: Dict[WorkloadProfileName, WorkloadProfileConfig] = {
    WorkloadProfileName.NORMAL_TRAFFIC: get_normal_traffic_profile(),
    WorkloadProfileName.GRADUAL_TRAFFIC_INCREASE: get_gradual_traffic_increase_profile(),
    WorkloadProfileName.SUDDEN_TRAFFIC_SPIKE: get_sudden_traffic_spike_profile(),
    WorkloadProfileName.SUSTAINED_HIGH_TRAFFIC: get_sustained_high_traffic_profile(),
    WorkloadProfileName.TRAFFIC_DECREASE: get_traffic_decrease_profile(),
    WorkloadProfileName.BURSTY_TRAFFIC: get_bursty_traffic_profile(),
}


def get_profile(name: str) -> Optional[WorkloadProfileConfig]:
    """Retrieve a workload profile by string or enum name."""
    try:
        enum_val = WorkloadProfileName(name) if isinstance(name, str) else name
        return CANONICAL_PROFILES.get(enum_val)
    except ValueError:
        return None


def get_all_profiles() -> List[WorkloadProfileConfig]:
    """Retrieve all six canonical workload profiles."""
    return list(CANONICAL_PROFILES.values())

