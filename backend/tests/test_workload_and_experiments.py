"""
Automated test suite for Stage 7: Workload Generation & Experiment Management.

Verifies:
1. Workload profile configuration loading, completeness, and parameter validation.
2. Safety boundary checks (rejecting excessive concurrency, negative rates, unsafe durations).
3. ExperimentManager lifecycle and state machine enforcement.
4. Strict safety lock: execution in Stage 7 is permanently blocked (RUNNING forbidden).
5. Metric recording and preservation of missing telemetry (no fabricated zeros).
6. API endpoint integration for profiles, validation, metadata, and status updates.
7. System safety posture assertions (SCALING_ENABLED=False, Actuator DRY-RUN, 0 loadgenerator replicas).
"""

import pytest
import time
from datetime import datetime, timezone
from pathlib import Path
from fastapi.testclient import TestClient

import backend.config as cfg
from backend.app.main import app
from backend.workload.models import (
    WorkloadProfileConfig,
    WorkloadProfileName,
    WorkloadStage,
)
from backend.workload.profiles import (
    CANONICAL_PROFILES,
    get_all_profiles,
    get_profile,
)
from backend.workload.validation import (
    MAX_ALLOWED_USERS,
    MIN_ALLOWED_USERS,
    validate_workload_config,
)
from backend.experiments.models import (
    ExperimentMetadata,
    ExperimentStatus,
)
from backend.experiments.manager import (
    ExperimentManager,
)
from backend.experiments.metrics import (
    ApplicationServiceMetrics,
    DPBPSDecisionMetrics,
    ExperimentMetricSnapshot,
    ExperimentMetricsCollection,
    InfrastructureServiceMetrics,
)

client = TestClient(app)


# ---------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------

@pytest.fixture
def temp_experiment_manager(tmp_path):
    """Provide an isolated ExperimentManager with a temporary directory."""
    return ExperimentManager(storage_dir=tmp_path / "experiments")


# ---------------------------------------------------------------------
# 1. WORKLOAD PROFILE CONFIGURATION TESTS
# ---------------------------------------------------------------------

def test_all_six_profiles_exist():
    """Verify all six canonical workload profiles exist and load with full details."""
    profiles = get_all_profiles()
    assert len(profiles) == 6

    expected_names = {
        WorkloadProfileName.NORMAL_TRAFFIC,
        WorkloadProfileName.GRADUAL_TRAFFIC_INCREASE,
        WorkloadProfileName.SUDDEN_TRAFFIC_SPIKE,
        WorkloadProfileName.SUSTAINED_HIGH_TRAFFIC,
        WorkloadProfileName.TRAFFIC_DECREASE,
        WorkloadProfileName.BURSTY_TRAFFIC,
    }
    loaded_names = {p.profile_name for p in profiles}
    assert loaded_names == expected_names


@pytest.mark.parametrize("name", list(WorkloadProfileName))
def test_profile_fields_and_stages_complete(name):
    """Verify each profile has descriptions, valid stages, and expected observations."""
    p = get_profile(name.value)
    assert p is not None
    assert p.display_name
    assert p.description
    assert p.target_host == "frontend:80"
    assert 1 <= p.users <= MAX_ALLOWED_USERS
    assert 0.1 <= p.spawn_rate <= 50.0
    assert p.total_duration_seconds >= 10
    assert len(p.stages) >= 1
    assert len(p.expected_observations) >= 3


def test_invalid_concurrency_rejected():
    """Verify concurrency > 200 or < 1 is rejected by safety validation."""
    base_cfg = get_profile("NORMAL_TRAFFIC")
    
    # Exceeding safety cap
    unsafe_cfg = base_cfg.model_copy(update={"users": 250})
    is_valid, errors = validate_workload_config(unsafe_cfg)
    assert not is_valid
    assert any("exceeds safety limit of 200" in err for err in errors)

    # Zero or negative users
    unsafe_zero = base_cfg.model_copy(update={"users": 0})
    is_valid, errors = validate_workload_config(unsafe_zero)
    assert not is_valid
    assert any("must be at least 1" in err for err in errors)


def test_invalid_spawn_rate_and_duration_rejected():
    """Verify zero/excessive spawn rates and durations are rejected."""
    base_cfg = get_profile("NORMAL_TRAFFIC")

    # Invalid spawn rate
    bad_rate = base_cfg.model_copy(update={"spawn_rate": 0.05})
    is_valid, errors = validate_workload_config(bad_rate)
    assert not is_valid
    assert any("spawn_rate" in err for err in errors)

    # Invalid duration (< 10s or > 1200s)
    bad_duration = base_cfg.model_copy(update={"total_duration_seconds": 5})
    is_valid, errors = validate_workload_config(bad_duration)
    assert not is_valid
    assert any("total_duration_seconds" in err for err in errors)


# ---------------------------------------------------------------------
# 2. EXPERIMENT MANAGEMENT TESTS
# ---------------------------------------------------------------------

def test_unique_experiment_ids_generated(temp_experiment_manager):
    """Verify distinct experiment IDs are generated across successive calls."""
    id1 = temp_experiment_manager.generate_experiment_id(WorkloadProfileName.NORMAL_TRAFFIC)
    id2 = temp_experiment_manager.generate_experiment_id(WorkloadProfileName.NORMAL_TRAFFIC)
    assert id1 != id2
    assert "normal_traffic" in id1
    assert id1.startswith("exp_")


def test_create_and_retrieve_experiment(temp_experiment_manager):
    """Verify experiment record creation, serialization, and disk persistence."""
    exp = temp_experiment_manager.create_experiment(
        profile_name=WorkloadProfileName.SUDDEN_TRAFFIC_SPIKE,
        notes="Surge detection test",
        tags=["spike-test"],
    )
    assert exp.status == ExperimentStatus.CREATED
    assert exp.profile_name == WorkloadProfileName.SUDDEN_TRAFFIC_SPIKE
    assert exp.execution_disabled is True
    assert exp.notes == "Surge detection test"

    # Verify retrieval
    retrieved = temp_experiment_manager.get_experiment(exp.experiment_id)
    assert retrieved is not None
    assert retrieved.experiment_id == exp.experiment_id

    # Verify disk persistence
    exp_dir = temp_experiment_manager.storage_dir / exp.experiment_id
    assert exp_dir.is_dir()
    assert (exp_dir / "config.json").exists()
    assert (exp_dir / "metadata.json").exists()


def test_valid_state_transitions(temp_experiment_manager):
    """Verify allowed state transitions in experiment lifecycle."""
    exp = temp_experiment_manager.create_experiment(WorkloadProfileName.NORMAL_TRAFFIC)
    assert exp.status == ExperimentStatus.CREATED

    # CREATED -> READY
    updated = temp_experiment_manager.update_status(exp.experiment_id, ExperimentStatus.READY)
    assert updated.status == ExperimentStatus.READY

    # READY -> CREATED
    updated = temp_experiment_manager.update_status(exp.experiment_id, ExperimentStatus.CREATED)
    assert updated.status == ExperimentStatus.CREATED

    # CREATED -> STOPPED
    updated = temp_experiment_manager.update_status(exp.experiment_id, ExperimentStatus.STOPPED)
    assert updated.status == ExperimentStatus.STOPPED
    assert updated.end_timestamp is not None


def test_invalid_state_transitions_rejected(temp_experiment_manager):
    """Verify illegal state transitions raise ValueError."""
    exp = temp_experiment_manager.create_experiment(WorkloadProfileName.NORMAL_TRAFFIC)
    # Stop experiment (terminal state)
    temp_experiment_manager.update_status(exp.experiment_id, ExperimentStatus.STOPPED)

    # Attempting to move from terminal STOPPED to READY must fail
    with pytest.raises(ValueError, match="cannot move from STOPPED to READY"):
        temp_experiment_manager.update_status(exp.experiment_id, ExperimentStatus.READY)


def test_running_transition_strictly_forbidden(temp_experiment_manager):
    """CRITICAL SAFETY TEST: Verify attempting to enter RUNNING status raises RuntimeError."""
    exp = temp_experiment_manager.create_experiment(WorkloadProfileName.BURSTY_TRAFFIC)
    
    with pytest.raises(RuntimeError, match="Workload execution is strictly DISABLED in Stage 7"):
        temp_experiment_manager.update_status(exp.experiment_id, ExperimentStatus.RUNNING)


# ---------------------------------------------------------------------
# 3. METRIC RECORDING & TELEMETRY FIDELITY TESTS
# ---------------------------------------------------------------------

def test_missing_metrics_preserved_without_fabrication(temp_experiment_manager):
    """Verify unavailable metrics are recorded as None, never fabricated as zero."""
    exp = temp_experiment_manager.create_experiment(WorkloadProfileName.NORMAL_TRAFFIC)

    # Snapshot with missing application metrics (e.g. uninstrumented redis-cart)
    snapshot = ExperimentMetricSnapshot(
        experiment_id=exp.experiment_id,
        snapshot_index=0,
        elapsed_seconds=15.0,
        application_metrics={
            "frontend": ApplicationServiceMetrics(
                service_name="frontend",
                request_rate=12.5,
                p95_latency_ms=25.0,
                error_rate=0.0,
                telemetry_present=True,
            ),
            "redis-cart": ApplicationServiceMetrics(
                service_name="redis-cart",
                request_rate=None,  # MISSING
                p95_latency_ms=None, # MISSING
                error_rate=None,     # MISSING
                telemetry_present=False,
            ),
        },
        infrastructure_metrics={
            "frontend": InfrastructureServiceMetrics(
                service_name="frontend",
                current_replicas=1,
                ready_replicas=1,
                cpu_utilization_fraction=0.15,
                memory_utilization_fraction=0.45,
            )
        },
        dpbps_metrics={
            "frontend": DPBPSDecisionMetrics(
                service_name="frontend",
                action="HOLD",
                previous_replicas=1,
                proposed_replicas=1,
                detected_bottleneck=None,
                decision_reason="Pressure within bounds – hold",
            )
        },
    )

    temp_experiment_manager.record_snapshot(exp.experiment_id, snapshot)
    collection = temp_experiment_manager.get_metrics(exp.experiment_id)
    assert collection is not None
    assert collection.total_snapshots == 1
    
    s0 = collection.snapshots[0]
    redis_metrics = s0.application_metrics["redis-cart"]
    assert redis_metrics.request_rate is None
    assert redis_metrics.p95_latency_ms is None
    assert redis_metrics.error_rate is None
    assert redis_metrics.telemetry_present is False


# ---------------------------------------------------------------------
# 4. API INTEGRATION TESTS
# ---------------------------------------------------------------------

def test_api_list_profiles():
    """Verify GET /api/v1/experiments/profiles returns all 6 profiles."""
    resp = client.get("/api/v1/experiments/profiles")
    assert resp.status_code == 200
    profiles = resp.json()
    assert len(profiles) == 6
    names = {p["profile_name"] for p in profiles}
    assert "NORMAL_TRAFFIC" in names
    assert "SUSTAINED_HIGH_TRAFFIC" in names


def test_api_get_profile_by_name():
    """Verify GET /api/v1/experiments/profiles/{name} returns profile or 404."""
    resp = client.get("/api/v1/experiments/profiles/GRADUAL_TRAFFIC_INCREASE")
    assert resp.status_code == 200
    data = resp.json()
    assert data["profile_name"] == "GRADUAL_TRAFFIC_INCREASE"
    assert len(data["stages"]) == 3

    resp404 = client.get("/api/v1/experiments/profiles/NON_EXISTENT_PROFILE")
    assert resp404.status_code == 404


def test_api_validate_config():
    """Verify POST /api/v1/experiments/validate validates config without side-effects."""
    valid_cfg = get_profile("NORMAL_TRAFFIC").model_dump()
    resp = client.post("/api/v1/experiments/validate", json=valid_cfg)
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["safety_checks_passed"] is True
    assert len(data["errors"]) == 0

    # Test invalid config
    invalid_cfg = valid_cfg.copy()
    invalid_cfg["users"] = 999  # Violates 200 user safety cap
    resp_bad = client.post("/api/v1/experiments/validate", json=invalid_cfg)
    assert resp_bad.status_code == 200
    data_bad = resp_bad.json()
    assert data_bad["valid"] is False
    assert len(data_bad["errors"]) > 0


def test_api_create_and_get_experiment():
    """Verify POST /api/v1/experiments creates record and GET retrieves it."""
    payload = {
        "profile_name": "SUDDEN_TRAFFIC_SPIKE",
        "notes": "API test experiment",
        "tags": ["automated-test"],
    }
    create_resp = client.post("/api/v1/experiments", json=payload)
    assert create_resp.status_code == 200
    exp = create_resp.json()
    exp_id = exp["experiment_id"]
    assert exp["status"] == "CREATED"
    assert exp["execution_disabled"] is True

    # Retrieve by ID
    get_resp = client.get(f"/api/v1/experiments/{exp_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["experiment_id"] == exp_id

    # List experiments
    list_resp = client.get("/api/v1/experiments?limit=10")
    assert list_resp.status_code == 200
    all_exps = list_resp.json()
    assert any(e["experiment_id"] == exp_id for e in all_exps)


def test_api_status_update_and_safety_lock():
    """Verify status update endpoint allows READY and blocks RUNNING with 403."""
    payload = {"profile_name": "NORMAL_TRAFFIC"}
    create_resp = client.post("/api/v1/experiments", json=payload)
    exp_id = create_resp.json()["experiment_id"]

    # Mark READY (allowed)
    ready_resp = client.post(
        f"/api/v1/experiments/{exp_id}/status",
        json={"status": "READY"},
    )
    assert ready_resp.status_code == 200
    assert ready_resp.json()["status"] == "READY"

    # Mark RUNNING (STRICTLY FORBIDDEN in Stage 7 -> HTTP 403)
    running_resp = client.post(
        f"/api/v1/experiments/{exp_id}/status",
        json={"status": "RUNNING"},
    )
    assert running_resp.status_code == 403
    assert "strictly DISABLED in Stage 7" in running_resp.json()["detail"]


# ---------------------------------------------------------------------
# 5. OVERALL SAFETY POSTURE ASSERTIONS
# ---------------------------------------------------------------------

def test_stage_7_safety_invariants():
    """Verify critical safety configurations remain active."""
    assert cfg.SCALING_ENABLED is False, "SCALING_ENABLED must be False in Stage 7 and 8"


# ---------------------------------------------------------------------
# 6. STAGE 8 WORKLOAD SHAPE GENERATOR & EXECUTOR SAFETY TESTS
# ---------------------------------------------------------------------

from backend.workload.shape_generator import (
    generate_locust_shape_stages,
    generate_locust_shape_code,
    evaluate_shape_tick,
    generate_combined_locustfile,
)
from backend.experiments.executor import (
    ExperimentExecutor,
    EXPERIMENT_EXECUTION_ENABLED,
)


def test_locust_shape_generator_stages():
    """Verify LoadTestShape stages match profile timing and concurrency."""
    gradual_cfg = get_profile("GRADUAL_TRAFFIC_INCREASE")
    stages = generate_locust_shape_stages(gradual_cfg)
    assert len(stages) == 3
    assert stages[0]["duration"] == 60
    assert stages[0]["users"] == 10
    assert stages[1]["duration"] == 120
    assert stages[1]["users"] == 25
    assert stages[2]["duration"] == 180
    assert stages[2]["users"] == 50

    bursty_cfg = get_profile("BURSTY_TRAFFIC")
    burst_stages = generate_locust_shape_stages(bursty_cfg)
    assert len(burst_stages) == 8
    assert burst_stages[-1]["duration"] == 160


def test_locust_shape_generator_code():
    """Verify generated Python code is syntactically valid and imports LoadTestShape."""
    normal_cfg = get_profile("NORMAL_TRAFFIC")
    code = generate_locust_shape_code(normal_cfg)
    assert "class DPBPSWorkloadShape(LoadTestShape):" in code
    assert "def tick(self):" in code
    # Verify code compiles
    compiled = compile(code, "<string>", "exec")
    assert compiled is not None


def test_e02_concurrency_stage_tick_boundaries():
    """Verify E02 GRADUAL_TRAFFIC_INCREASE produces exact user steps at stage boundaries."""
    gradual_cfg = get_profile("GRADUAL_TRAFFIC_INCREASE")
    stages = generate_locust_shape_stages(gradual_cfg)

    # Stage 1: 0 to 60s -> 10 users, 2.0 spawn rate
    assert evaluate_shape_tick(stages, 0.0) == (10, 2.0)
    assert evaluate_shape_tick(stages, 30.0) == (10, 2.0)
    assert evaluate_shape_tick(stages, 59.9) == (10, 2.0)

    # Stage 2: 60 to 120s -> 25 users, 2.0 spawn rate
    assert evaluate_shape_tick(stages, 60.0) == (25, 2.0)
    assert evaluate_shape_tick(stages, 90.0) == (25, 2.0)
    assert evaluate_shape_tick(stages, 119.9) == (25, 2.0)

    # Stage 3: 120 to 180s -> 50 users, 2.0 spawn rate
    assert evaluate_shape_tick(stages, 120.0) == (50, 2.0)
    assert evaluate_shape_tick(stages, 150.0) == (50, 2.0)
    assert evaluate_shape_tick(stages, 179.9) == (50, 2.0)

    # Post-180s: test completion
    assert evaluate_shape_tick(stages, 180.0) is None
    assert evaluate_shape_tick(stages, 185.0) is None


def test_e02_concurrency_spawn_rates_and_durations():
    """Verify E02 step durations, spawn rate invariance, and ramp-up math."""
    gradual_cfg = get_profile("GRADUAL_TRAFFIC_INCREASE")
    assert gradual_cfg.total_duration_seconds == 180
    assert len(gradual_cfg.stages) == 3

    # All stages must maintain 2.0 users/sec
    for stage in gradual_cfg.stages:
        assert stage.spawn_rate == 2.0
        assert stage.duration_seconds == 60

    # User progression: 10 -> 25 -> 50
    assert gradual_cfg.stages[0].target_users == 10
    assert gradual_cfg.stages[1].target_users == 25
    assert gradual_cfg.stages[2].target_users == 50

    # Ramp-up durations:
    # Stage 1: 10 users / 2.0 = 5s ramp, 55s steady
    # Stage 2: 15 delta users / 2.0 = 7.5s ramp, 52.5s steady
    # Stage 3: 25 delta users / 2.0 = 12.5s ramp, 47.5s steady
    ramp_stage_1 = gradual_cfg.stages[0].target_users / gradual_cfg.stages[0].spawn_rate
    assert ramp_stage_1 == 5.0

    delta_stage_2 = gradual_cfg.stages[1].target_users - gradual_cfg.stages[0].target_users
    ramp_stage_2 = delta_stage_2 / gradual_cfg.stages[1].spawn_rate
    assert ramp_stage_2 == 7.5

    delta_stage_3 = gradual_cfg.stages[2].target_users - gradual_cfg.stages[1].target_users
    ramp_stage_3 = delta_stage_3 / gradual_cfg.stages[2].spawn_rate
    assert ramp_stage_3 == 12.5


def test_combined_locustfile_generation(tmp_path):
    """Verify generate_combined_locustfile produces valid Python combining tasks and shape."""
    base_locustfile = tmp_path / "locustfile.py"
    base_locustfile.write_text(
        "from locust import FastHttpUser, task\n\n"
        "class WebsiteUser(FastHttpUser):\n"
        "    @task\n"
        "    def index(self):\n"
        "        self.client.get('/')\n",
        encoding="utf-8",
    )

    gradual_cfg = get_profile("GRADUAL_TRAFFIC_INCREASE")
    combined_code = generate_combined_locustfile(base_locustfile, gradual_cfg)

    assert "class WebsiteUser(FastHttpUser):" in combined_code
    assert "class DPBPSWorkloadShape(LoadTestShape):" in combined_code
    assert "'users': 50" in combined_code

    # Syntax compilation verification
    compiled = compile(combined_code, "<string>", "exec")
    assert compiled is not None


def test_e02_watchdog_and_emergency_scale_zero(temp_experiment_manager):
    """Verify E02 watchdog and emergency-stop unconditionally scale loadgenerator to zero."""
    executor = ExperimentExecutor(manager=temp_experiment_manager)
    exp = temp_experiment_manager.create_experiment(WorkloadProfileName.GRADUAL_TRAFFIC_INCREASE)
    exp.status = ExperimentStatus.RUNNING
    temp_experiment_manager._experiments[exp.experiment_id] = exp

    # Active experiment state setup
    executor.active_experiment_id = exp.experiment_id
    executor.active_duration_seconds = exp.configuration.total_duration_seconds  # 180s

    scaled_replicas_history = []
    executor._scale_loadgenerator = lambda r, **kwargs: scaled_replicas_history.append(r)

    # 1. Before expiry (e.g. 179s elapsed)
    executor.active_start_time = 1000.0
    import time
    time_mock = 1000.0 + 179.0  # 179s elapsed
    # Patch time
    orig_time = time.time
    try:
        time.time = lambda: time_mock
        res = executor.watchdog_check(exp.experiment_id)
        assert res["active"] is True
        assert len(scaled_replicas_history) == 0

        # 2. At watchdog threshold (180s + 5s = 185s elapsed)
        time_mock = 1000.0 + 185.1
        res = executor.watchdog_check(exp.experiment_id)
        assert res["active"] is False
        assert res["action"] == "completed"
        assert 0 in scaled_replicas_history

        # 3. Emergency stop check
        scaled_replicas_history.clear()
        executor.active_experiment_id = exp.experiment_id
        res_stop = executor.emergency_stop(exp.experiment_id, reason="Operator emergency termination test")
        assert res_stop["status"] == "STOPPED"
        assert res_stop["loadgenerator_target_replicas"] == 0
        assert 0 in scaled_replicas_history
    finally:
        time.time = orig_time


def test_experiment_executor_safety_lock(temp_experiment_manager):
    """Verify ExperimentExecutor blocks execution when EXPERIMENT_EXECUTION_ENABLED is False."""
    executor = ExperimentExecutor(manager=temp_experiment_manager)
    assert executor.is_execution_enabled() is False

    exp = temp_experiment_manager.create_experiment(WorkloadProfileName.NORMAL_TRAFFIC)
    can_exec, reasons = executor.can_execute(exp.experiment_id)
    assert can_exec is False
    assert any("Master execution lock active" in r for r in reasons)


def test_experiment_executor_directory_initialization(temp_experiment_manager, tmp_path):
    """Verify ExperimentExecutor initializes all 7 required experiment storage files."""
    executor = ExperimentExecutor(manager=temp_experiment_manager, storage_dir=tmp_path / "exp_storage")
    exp = temp_experiment_manager.create_experiment(WorkloadProfileName.SUDDEN_TRAFFIC_SPIKE)

    exp_dir = executor.prepare_experiment_directory(exp)
    assert exp_dir.is_dir()
    assert (exp_dir / "experiment_config.json").exists()
    assert (exp_dir / "workload_metrics.json").exists()
    assert (exp_dir / "telemetry_metrics.json").exists()
    assert (exp_dir / "dpbps_decisions.json").exists()
    assert (exp_dir / "actuator_audit.json").exists()
    assert (exp_dir / "experiment_summary.json").exists()
    assert (exp_dir / "experiment.log").exists()


def test_experiment_executor_emergency_stop(temp_experiment_manager):
    """Verify emergency stop transitions experiment to STOPPED and returns 0 replicas."""
    from unittest.mock import MagicMock
    mock_apps = MagicMock()
    executor = ExperimentExecutor(manager=temp_experiment_manager, apps_api=mock_apps)
    exp = temp_experiment_manager.create_experiment(WorkloadProfileName.NORMAL_TRAFFIC)
    executor.active_experiment_id = exp.experiment_id

    res = executor.emergency_stop(exp.experiment_id, reason="Test emergency stop")
    assert res["status"] == "STOPPED"
    assert res["loadgenerator_target_replicas"] == 0
    assert executor.active_experiment_id is None
    mock_apps.patch_namespaced_deployment_scale.assert_called_once_with(
        name="loadgenerator",
        namespace="online-boutique",
        body={"spec": {"replicas": 0}},
    )

    updated = temp_experiment_manager.get_experiment(exp.experiment_id)
    assert updated.status == ExperimentStatus.STOPPED


def test_api_safety_check_and_emergency_stop():
    """Verify /safety-check and /stop API endpoints operate safely."""
    payload = {"profile_name": "NORMAL_TRAFFIC"}
    create_resp = client.post("/api/v1/experiments", json=payload)
    exp_id = create_resp.json()["experiment_id"]

    # Safety check endpoint
    check_resp = client.get(f"/api/v1/experiments/{exp_id}/safety-check")
    assert check_resp.status_code == 200
    check_data = check_resp.json()
    assert check_data["can_execute"] is False
    assert check_data["actuator_mode"] == "DRY_RUN"
    assert len(check_data["blocking_reasons"]) > 0

    # Emergency stop endpoint
    stop_resp = client.post(f"/api/v1/experiments/{exp_id}/stop?reason=Test+stop")
    assert stop_resp.status_code == 200
    assert stop_resp.json()["status"] == "STOPPED"


def test_executor_start_experiment_blocked_by_safety_lock(temp_experiment_manager):
    """Verify start_experiment raises ExperimentSafetyError when safety lock is active."""
    from backend.experiments.executor import ExperimentSafetyError
    executor = ExperimentExecutor(manager=temp_experiment_manager)
    exp = temp_experiment_manager.create_experiment(WorkloadProfileName.NORMAL_TRAFFIC)

    with pytest.raises(ExperimentSafetyError, match="Experiment execution forbidden"):
        executor.start_experiment(exp.experiment_id)


def test_executor_scale_loadgenerator_safety_check(temp_experiment_manager):
    """Verify scaling loadgenerator > 0 raises ExperimentSafetyError when locked."""
    from backend.experiments.executor import ExperimentSafetyError
    from unittest.mock import MagicMock
    mock_apps = MagicMock()
    executor = ExperimentExecutor(manager=temp_experiment_manager, apps_api=mock_apps)

    with pytest.raises(ExperimentSafetyError, match="Cannot scale loadgenerator > 0"):
        executor._scale_loadgenerator(1)

    # Scaling to 0 is always allowed for safety cleanup
    res = executor._scale_loadgenerator(0)
    assert res["success"] is True
    assert res["replicas"] == 0
    mock_apps.patch_namespaced_deployment_scale.assert_called_once_with(
        name="loadgenerator",
        namespace="online-boutique",
        body={"spec": {"replicas": 0}},
    )


def test_executor_reconciliation_cleans_orphaned_replicas(temp_experiment_manager):
    """Verify startup reconciliation forces loadgenerator to 0 if replicas > 0."""
    from unittest.mock import MagicMock
    mock_apps = MagicMock()
    mock_scale = MagicMock()
    mock_scale.spec.replicas = 2
    mock_apps.read_namespaced_deployment_scale.return_value = mock_scale

    executor = ExperimentExecutor(manager=temp_experiment_manager, apps_api=mock_apps)
    res = executor.reconcile_cluster_state()

    assert res["reconciled"] is True
    assert res["action"] == "scaled_to_zero"
    mock_apps.patch_namespaced_deployment_scale.assert_called_once_with(
        name="loadgenerator",
        namespace="online-boutique",
        body={"spec": {"replicas": 0}},
    )


def test_executor_watchdog_duration_expiry(temp_experiment_manager):
    """Verify watchdog detects expired duration and stops experiment."""
    from unittest.mock import MagicMock
    mock_apps = MagicMock()
    executor = ExperimentExecutor(manager=temp_experiment_manager, apps_api=mock_apps)
    exp = temp_experiment_manager.create_experiment(WorkloadProfileName.NORMAL_TRAFFIC)
    # Directly set to RUNNING for watchdog testing (simulating an active test)
    exp.status = ExperimentStatus.RUNNING
    executor.active_experiment_id = exp.experiment_id
    executor.active_start_time = time.time() - 200  # 200 seconds ago (duration is 130s)
    executor.active_duration_seconds = 130

    res = executor.watchdog_check()
    assert res["active"] is False
    assert res["action"] == "completed"
    assert "Duration expired" in res["reason"]
    assert executor.active_experiment_id is None
    mock_apps.patch_namespaced_deployment_scale.assert_called_once_with(
        name="loadgenerator",
        namespace="online-boutique",
        body={"spec": {"replicas": 0}},
    )

    updated = temp_experiment_manager.get_experiment(exp.experiment_id)
    assert updated.status == ExperimentStatus.COMPLETED


def test_api_start_endpoint_returns_403_forbidden():
    """Verify POST /experiments/{id}/start is rejected with 403 when locked."""
    payload = {"profile_name": "NORMAL_TRAFFIC"}
    create_resp = client.post("/api/v1/experiments", json=payload)
    exp_id = create_resp.json()["experiment_id"]

    start_resp = client.post(f"/api/v1/experiments/{exp_id}/start")
    assert start_resp.status_code == 403
    assert "Experiment execution blocked by safety interlock" in start_resp.json()["detail"]


def test_api_reconcile_endpoint():
    """Verify POST /experiments/reconcile endpoint operates cleanly."""
    resp = client.post("/api/v1/experiments/reconcile")
    assert resp.status_code == 200
    assert "reconciled" in resp.json()



