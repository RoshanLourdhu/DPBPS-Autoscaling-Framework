# backend/app/api/v1_router.py
"""
API Router for DPBPS Platform Backend.

Provides endpoints for:
1. System health and environment status.
2. Microservices inventory and live metric telemetry.
3. Kubernetes pod and deployment telemetry.
4. DPBPS scaling controller decisions and history.
5. Deployment phase inspection and phase transitions.
6. Kubernetes Scaling Actuator dry-run execution.
7. Consolidated end-to-end DPBPS evaluation pipeline.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import backend.config as cfg
from backend.scaling.deployment_state import DeploymentStateManager
from backend.scaling.dpbps_controller import DPBPSController
from backend.scaling.kubernetes.actuator import (
    KubernetesScalingActuator,
    KubernetesScalingResult,
    ScalingExecutionStatus,
)
from backend.scaling.kubernetes.telemetry_adapter import (
    KubernetesTelemetryAdapter,
)
from backend.scaling.models import (
    DecisionAction,
    DecisionOutput,
    DeploymentPhase,
    ScalingConfig as ScalingConfigModel,
    TelemetryInput,
)
from backend.workload.models import (
    WorkloadProfileConfig,
    WorkloadProfileName,
)
from backend.workload.profiles import (
    CANONICAL_PROFILES,
    get_all_profiles,
    get_profile,
)
from backend.workload.validation import (
    validate_workload_config,
    WorkloadValidationError,
)
from backend.experiments.manager import ExperimentManager
from backend.experiments.executor import ExperimentExecutor
from backend.experiments.models import (
    ExperimentCreateRequest,
    ExperimentMetadata,
    ExperimentStatus,
    ExperimentValidationResponse,
)
from backend.experiments.metrics import (
    ExperimentMetricsCollection,
)
from .simulation import router as simulation_router

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------
# SHARED COMPONENT INSTANCES
# ---------------------------------------------------------------------
# Use a unified DeploymentStateManager so the DPBPS controller,
# the telemetry adapter, and the actuator share identical phase & cooldown state.

shared_state_manager = DeploymentStateManager()
dpbps_controller = DPBPSController()
dpbps_controller.state_manager = shared_state_manager
experiment_manager = ExperimentManager()
experiment_executor = ExperimentExecutor(manager=experiment_manager)

_shared_adapter: Optional[KubernetesTelemetryAdapter] = None
_shared_actuator: Optional[KubernetesScalingActuator] = None
_actuator_history: List[KubernetesScalingResult] = []


def get_telemetry_adapter() -> KubernetesTelemetryAdapter:
    """Retrieve or initialize the shared KubernetesTelemetryAdapter."""
    global _shared_adapter
    if _shared_adapter is None:
        _shared_adapter = KubernetesTelemetryAdapter(
            namespace=cfg.KUBERNETES_NAMESPACE,
            state_manager=shared_state_manager,
            prometheus_base_url=cfg.PROMETHEUS_URL,
        )
    return _shared_adapter


def get_kubernetes_actuator() -> KubernetesScalingActuator:
    """Retrieve or initialize the shared KubernetesScalingActuator in dry-run mode."""
    global _shared_actuator
    if _shared_actuator is None:
        _shared_actuator = KubernetesScalingActuator(
            namespace=cfg.KUBERNETES_NAMESPACE,
            state_manager=shared_state_manager,
            config=dpbps_controller.config,
            dry_run=True,  # STRICT DRY-RUN DEFAULT
        )
    return _shared_actuator


def set_telemetry_adapter(adapter: KubernetesTelemetryAdapter) -> None:
    """Override telemetry adapter (primarily for testing)."""
    global _shared_adapter
    _shared_adapter = adapter


def set_kubernetes_actuator(actuator: KubernetesScalingActuator) -> None:
    """Override actuator (primarily for testing)."""
    global _shared_actuator
    _shared_actuator = actuator


# ---------------------------------------------------------------------
# HEALTH & ENVIRONMENT ENDPOINTS
# ---------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    kubernetes_connected: bool = True
    prometheus_connected: bool = True
    dry_run: bool = True
    scaling_enabled: bool = False
    deployment_phase: str = "NORMAL_OPERATION"


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    """Return comprehensive health information for backend and cluster services."""
    k8s_ok = True
    prom_ok = True

    try:
        adapter = get_telemetry_adapter()
        # Verify Prometheus reachability
        if adapter.prometheus_client:
            res = adapter.prometheus_client.execute_query("up")
            prom_ok = res.is_present
    except Exception:
        prom_ok = False

    try:
        actuator = get_kubernetes_actuator()
        if actuator.apps_api:
            # Simple check
            k8s_ok = True
    except Exception:
        k8s_ok = False

    return HealthResponse(
        status="ok",
        service="dpbps-backend",
        version="0.1.0",
        kubernetes_connected=k8s_ok,
        prometheus_connected=prom_ok,
        dry_run=True,
        scaling_enabled=cfg.SCALING_ENABLED,
        deployment_phase=shared_state_manager.get_phase().value,
    )


class EnvironmentInfo(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    status: str


@router.get("/environments", response_model=List[EnvironmentInfo], tags=["environment"])
async def list_environments():
    """List operational and simulated environments."""
    return [
        {
            "id": "online-boutique",
            "name": "Google Online Boutique (Kubernetes)",
            "description": "10-microservice e-commerce application instrumented with OpenTelemetry.",
            "status": "CONNECTED",
        },
        {
            "id": "simulated",
            "name": "DPBPS Simulation Lab",
            "description": "Synthetic load generation and algorithm simulation harness.",
            "status": "READY",
        },
    ]


# ---------------------------------------------------------------------
# OVERVIEW METRICS & SERVICES
# ---------------------------------------------------------------------

class Metric(BaseModel):
    name: str
    value: float
    unit: str
    timestamp: str
    environment_id: str
    service_id: Optional[str] = None
    source: str
    simulated: bool


class OverviewMetricsResponse(BaseModel):
    metrics: List[Metric]


@router.get("/metrics/overview", response_model=OverviewMetricsResponse, tags=["metrics"])
async def get_overview_metrics():
    """Aggregate overview metrics across live Kubernetes microservices."""
    now_str = datetime.now(timezone.utc).isoformat()
    metrics: List[Metric] = []

    try:
        adapter = get_telemetry_adapter()
        raw_telemetry = adapter.collect_deployment_telemetry()
        active_items = [
            item for item in raw_telemetry
            if item.get("desired_replicas", 0) > 0 and item.get("service_name") != "loadgenerator"
        ]

        if active_items:
            # 1. Total Request Rate
            total_req = sum(item.get("request_rate") or 0.0 for item in active_items)
            metrics.append(Metric(
                name="request_rate", value=round(total_req, 2), unit="req/s",
                timestamp=now_str, environment_id="online-boutique", source="prometheus", simulated=False
            ))

            # 2. Average P95 Latency
            latencies = [item["p95_latency_ms"] for item in active_items if item.get("p95_latency_ms") is not None]
            avg_p95 = sum(latencies) / len(latencies) if latencies else 0.0
            metrics.append(Metric(
                name="p95_latency", value=round(avg_p95, 2), unit="ms",
                timestamp=now_str, environment_id="online-boutique", source="prometheus", simulated=False
            ))

            # 3. Average Error Rate
            errs = [item["error_rate"] for item in active_items if item.get("error_rate") is not None]
            avg_err = sum(errs) / len(errs) if errs else 0.0
            metrics.append(Metric(
                name="error_rate", value=round(avg_err, 4), unit="fraction",
                timestamp=now_str, environment_id="online-boutique", source="prometheus", simulated=False
            ))

            # 4. Average CPU Utilisation
            cpus = [item["cpu_utilization_percent"] for item in active_items if item.get("cpu_utilization_percent") is not None]
            avg_cpu = sum(cpus) / len(cpus) if cpus else 0.0
            metrics.append(Metric(
                name="cpu_utilisation", value=round(avg_cpu, 2), unit="%",
                timestamp=now_str, environment_id="online-boutique", source="kubernetes", simulated=False
            ))

            # 5. Average Memory Utilisation
            mems = [item["memory_utilization_percent"] for item in active_items if item.get("memory_utilization_percent") is not None]
            avg_mem = sum(mems) / len(mems) if mems else 0.0
            metrics.append(Metric(
                name="memory_utilisation", value=round(avg_mem, 2), unit="%",
                timestamp=now_str, environment_id="online-boutique", source="kubernetes", simulated=False
            ))

            # 6. Total Ready Replicas
            total_ready = sum(item.get("ready_replicas") or 0 for item in active_items)
            metrics.append(Metric(
                name="ready_replicas", value=float(total_ready), unit="replicas",
                timestamp=now_str, environment_id="online-boutique", source="kubernetes", simulated=False
            ))
    except Exception as exc:
        logger.warning("Failed to collect live overview metrics: %s", exc)

    return OverviewMetricsResponse(metrics=metrics)


class ServiceInfo(BaseModel):
    id: str
    name: str
    environment_id: str
    health: str
    ready_replicas: int
    desired_replicas: int = 1
    cpu_utilisation: float
    memory_utilisation: float
    request_rate: float
    p95_latency: float
    error_rate: float
    dependencies: List[str] = Field(default_factory=list)
    telemetry_available: bool = True
    missing_metrics: List[str] = Field(default_factory=list)
    deployment_phase: str = "NORMAL_OPERATION"


@router.get("/services", response_model=List[ServiceInfo], tags=["service"])
async def list_services():
    """List all microservices with live health and telemetry measurements."""
    try:
        adapter = get_telemetry_adapter()
        raw_telemetry = adapter.collect_deployment_telemetry()
        services: List[ServiceInfo] = []

        for item in raw_telemetry:
            # Exclude loadgenerator from microservices list
            if item["service_name"] == "loadgenerator":
                continue

            health_status = "HEALTHY" if item.get("telemetry_available") else "DEGRADED"

            services.append(ServiceInfo(
                id=item["service_name"],
                name=item["service_name"],
                environment_id="online-boutique",
                health=health_status,
                ready_replicas=item.get("ready_replicas", 0),
                desired_replicas=item.get("desired_replicas", 0),
                cpu_utilisation=item.get("cpu_utilisation") or 0.0,
                memory_utilisation=item.get("memory_utilisation") or 0.0,
                request_rate=item.get("request_rate") or 0.0,
                p95_latency=item.get("p95_latency_ms") or 0.0,
                error_rate=item.get("error_rate") or 0.0,
                dependencies=item.get("dependencies", []),
                telemetry_available=bool(item.get("telemetry_available")),
                missing_metrics=item.get("missing_metrics", []),
                deployment_phase=item.get("deployment_phase") or shared_state_manager.get_phase().value,
            ))
        return services
    except Exception as exc:
        logger.warning("Failed to retrieve live services list: %s", exc)
        return []


# ---------------------------------------------------------------------
# KUBERNETES TELEMETRY DIRECT ENDPOINTS
# ---------------------------------------------------------------------

@router.get("/kubernetes/telemetry", tags=["kubernetes"])
async def get_kubernetes_telemetry():
    """Retrieve raw live telemetry for all deployments in the target namespace."""
    try:
        adapter = get_telemetry_adapter()
        return adapter.collect_deployment_telemetry()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to collect Kubernetes telemetry: {exc}")


@router.get("/kubernetes/telemetry/summary", tags=["kubernetes"])
async def get_kubernetes_telemetry_summary():
    """Retrieve telemetry completeness and deployment summary."""
    try:
        adapter = get_telemetry_adapter()
        return adapter.get_telemetry_summary()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate telemetry summary: {exc}")


# ---------------------------------------------------------------------
# EXPERIMENTS & WORKLOAD PROFILES
# ---------------------------------------------------------------------

class ExperimentStatusUpdateRequest(BaseModel):
    status: ExperimentStatus
    failure_information: Optional[str] = None


@router.get("/experiments/profiles", response_model=List[WorkloadProfileConfig], tags=["experiments"])
async def list_workload_profiles():
    """Retrieve all six canonical DPBPS evaluation workload profiles."""
    return get_all_profiles()


@router.get("/experiments/profiles/{profile_name}", response_model=WorkloadProfileConfig, tags=["experiments"])
async def get_workload_profile(profile_name: str):
    """Retrieve a specific workload profile configuration by name."""
    prof = get_profile(profile_name)
    if not prof:
        raise HTTPException(status_code=404, detail=f"Workload profile '{profile_name}' not found")
    return prof


@router.post("/experiments/validate", response_model=ExperimentValidationResponse, tags=["experiments"])
async def validate_experiment_config(payload: Dict[str, Any]):
    """Validate a workload configuration against safety limits without creating an experiment."""
    try:
        config = WorkloadProfileConfig(**payload)
        is_valid, errors = validate_workload_config(config)
        return ExperimentValidationResponse(
            valid=is_valid,
            errors=errors,
            profile_name=config.profile_name,
            safety_checks_passed=is_valid,
            configuration=config if is_valid else None,
        )
    except Exception as e:
        prof_name = payload.get("profile_name", WorkloadProfileName.NORMAL_TRAFFIC)
        try:
            prof_enum = WorkloadProfileName(prof_name)
        except Exception:
            prof_enum = WorkloadProfileName.NORMAL_TRAFFIC

        return ExperimentValidationResponse(
            valid=False,
            errors=[str(e)],
            profile_name=prof_enum,
            safety_checks_passed=False,
            configuration=None,
        )


@router.post("/experiments", response_model=ExperimentMetadata, tags=["experiments"])
async def create_experiment_record(request: ExperimentCreateRequest):
    """
    Create a new experiment record in CREATED state.
    
    Workload execution is strictly disabled in Stage 7.
    """
    try:
        exp = experiment_manager.create_experiment(
            profile_name=request.profile_name,
            custom_configuration=request.custom_configuration,
            notes=request.notes,
            tags=request.tags,
        )
        return exp
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to create experiment: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to create experiment: {e}")


@router.get("/experiments", response_model=List[ExperimentMetadata], tags=["experiments"])
async def list_experiments(limit: int = Query(50, ge=1, le=100)):
    """List experiment records ordered by most recent first."""
    return experiment_manager.list_experiments(limit=limit)


@router.get("/experiments/{experiment_id}", response_model=ExperimentMetadata, tags=["experiments"])
async def get_experiment_details(experiment_id: str):
    """Retrieve metadata for a specific experiment ID."""
    exp = experiment_manager.get_experiment(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found")
    return exp


@router.get("/experiments/{experiment_id}/metrics", response_model=Optional[ExperimentMetricsCollection], tags=["experiments"])
async def get_experiment_metrics(experiment_id: str):
    """Retrieve collected metric snapshots for an experiment."""
    metrics = experiment_manager.get_metrics(experiment_id)
    if not metrics:
        # Check if experiment exists
        exp = experiment_manager.get_experiment(experiment_id)
        if not exp:
            raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found")
        # Return empty collection
        return ExperimentMetricsCollection(
            experiment_id=experiment_id,
            profile_name=exp.profile_name.value,
            total_snapshots=0,
            snapshots=[],
        )
    return metrics


@router.post("/experiments/{experiment_id}/status", response_model=ExperimentMetadata, tags=["experiments"])
async def update_experiment_status(experiment_id: str, payload: ExperimentStatusUpdateRequest):
    """
    Update the status of an experiment record.
    
    CRITICAL SAFETY ENFORCEMENT:
    Transitions to RUNNING are strictly forbidden in Stage 7 and return HTTP 403 Forbidden.
    """
    if payload.status == ExperimentStatus.RUNNING and not experiment_executor.is_execution_enabled():
        raise HTTPException(
            status_code=403,
            detail="Workload execution is strictly DISABLED in Stage 7. Experiments cannot enter RUNNING state.",
        )
    try:
        updated = experiment_manager.update_status(
            experiment_id=experiment_id,
            new_status=payload.status,
            failure_information=payload.failure_information,
        )
        return updated
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/experiments/{experiment_id}/safety-check", tags=["experiments"])
async def check_experiment_safety(experiment_id: str):
    """
    Evaluate safety gates for an experiment.
    
    Verifies master lock, lifecycle state, parameter limits, cluster health,
    and DRY-RUN actuator mode.
    """
    can_exec, reasons = experiment_executor.can_execute(experiment_id)
    return {
        "experiment_id": experiment_id,
        "can_execute": can_exec,
        "blocking_reasons": reasons,
        "master_execution_enabled": experiment_executor.is_execution_enabled(),
        "scaling_enabled": cfg.SCALING_ENABLED,
        "actuator_mode": "DRY_RUN",
    }


@router.post("/experiments/{experiment_id}/start", tags=["experiments"])
async def start_experiment(experiment_id: str):
    """
    Supervised start endpoint.
    Strictly verifies master safety lock, preflight checks, and cluster readiness.
    Rejects with 403 Forbidden if EXPERIMENT_EXECUTION_ENABLED is False.
    """
    can_exec, reasons = experiment_executor.can_execute(experiment_id)
    if not can_exec:
        raise HTTPException(
            status_code=403,
            detail=f"Experiment execution blocked by safety interlock: {'; '.join(reasons)}",
        )
    try:
        result = experiment_executor.start_experiment(experiment_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/experiments/reconcile", tags=["experiments"])
async def reconcile_experiments_state():
    """
    Reconciles cluster state against active experiments.
    Ensures that loadgenerator has 0 replicas if no experiment is currently RUNNING.
    """
    return experiment_executor.reconcile_cluster_state()


@router.post("/experiments/{experiment_id}/stop", tags=["experiments"])
async def stop_experiment_emergency(experiment_id: str, reason: str = Query("Operator stop requested", description="Termination reason")):
    """
    Emergency stop endpoint. Immediately forces loadgenerator to 0 replicas and marks experiment STOPPED.
    """
    exp = experiment_manager.get_experiment(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found")

    result = experiment_executor.emergency_stop(experiment_id, reason=reason)
    return result


# ---------------------------------------------------------------------
# SCALING CONFIGURATION & EVENTS
# ---------------------------------------------------------------------

class ScalingConfig(BaseModel):
    strategy: str = "dpbps"
    min_replicas: int = 1
    max_replicas: int = 10
    cpu_threshold: float = 0.8
    memory_threshold: float = 0.8
    latency_target_ms: float = 200.0
    scale_up_window_sec: int = 30
    scale_down_window_sec: int = 120
    cooldown_sec: int = 15


@router.get("/scaling/config", response_model=ScalingConfig, tags=["scaling"])
async def get_scaling_config():
    c = dpbps_controller.config
    return ScalingConfig(
        strategy="dpbps",
        min_replicas=c.min_replicas,
        max_replicas=c.max_replicas,
        cpu_threshold=c.cpu_threshold,
        memory_threshold=c.memory_threshold,
        latency_target_ms=c.latency_target_ms,
        scale_up_window_sec=c.scale_up_window_sec,
        scale_down_window_sec=c.scale_down_window_sec,
        cooldown_sec=c.cooldown_sec,
    )


@router.put("/scaling/config", response_model=ScalingConfig, tags=["scaling"])
async def update_scaling_config(config_in: ScalingConfig):
    dpbps_controller.config.min_replicas = config_in.min_replicas
    dpbps_controller.config.max_replicas = config_in.max_replicas
    dpbps_controller.config.cpu_threshold = config_in.cpu_threshold
    dpbps_controller.config.memory_threshold = config_in.memory_threshold
    dpbps_controller.config.latency_target_ms = config_in.latency_target_ms
    dpbps_controller.config.scale_up_window_sec = config_in.scale_up_window_sec
    dpbps_controller.config.scale_down_window_sec = config_in.scale_down_window_sec
    dpbps_controller.config.cooldown_sec = config_in.cooldown_sec
    return config_in


class ScalingEvent(BaseModel):
    timestamp: str
    environment_id: str
    service_id: str
    previous_replicas: int
    requested_replicas: int
    actual_replicas: int
    decision: str
    reason: str


@router.get("/scaling/events", response_model=List[ScalingEvent], tags=["scaling"])
async def list_scaling_events():
    """Return scaling events derived from recent actuator and controller history."""
    events = []
    for d in dpbps_controller.get_history(20):
        events.append(ScalingEvent(
            timestamp=d.timestamp.isoformat(),
            environment_id="online-boutique",
            service_id=d.service_name,
            previous_replicas=d.previous_replicas,
            requested_replicas=d.requested_replicas,
            actual_replicas=d.previous_replicas,  # Dry-run: actual remains previous
            decision=d.action.value,
            reason=d.reason,
        ))
    return events


class DeploymentInfo(BaseModel):
    id: str
    version: str
    status: str
    start_time: str
    end_time: Optional[str] = None
    ready_replicas: int
    unavailable_replicas: int
    phase: str


@router.get("/deployments", response_model=List[DeploymentInfo], tags=["deployment"])
async def list_deployments():
    """List deployment rollouts across the cluster."""
    try:
        adapter = get_telemetry_adapter()
        raw_telemetry = adapter.collect_deployment_telemetry()
        deployments = []
        for item in raw_telemetry:
            desired = item.get("desired_replicas", 0)
            ready = item.get("ready_replicas", 0)
            deployments.append(DeploymentInfo(
                id=item["service_name"],
                version="v1",
                status="READY" if (ready == desired and desired > 0) else ("IDLE" if desired == 0 else "UPDATING"),
                start_time=item.get("timestamp") or datetime.now(timezone.utc).isoformat(),
                ready_replicas=ready,
                unavailable_replicas=max(0, desired - ready),
                phase=item.get("deployment_phase") or shared_state_manager.get_phase().value,
            ))
        return deployments
    except Exception as exc:
        logger.warning("Failed to list deployments: %s", exc)
        return []


# ---------------------------------------------------------------------
# SIMULATION SUB-ROUTER
# ---------------------------------------------------------------------

router.include_router(simulation_router, prefix="/simulation", tags=["simulation"])


# ---------------------------------------------------------------------
# DPBPS CONTROLLER & SCALING DECISION ENDPOINTS
# ---------------------------------------------------------------------

@router.get("/scaling/status", tags=["scaling"])
async def get_scaling_status():
    """Return controller configuration, phase, dry-run mode, and latest decision."""
    latest = dpbps_controller.decision_history[-1].dict() if dpbps_controller.decision_history else None
    return {
        "simulation_mode": True,
        "dry_run": True,
        "scaling_enabled": cfg.SCALING_ENABLED,
        "phase": dpbps_controller.get_phase().value,
        "config": dpbps_controller.config.dict(),
        "latest_decision": latest,
    }


@router.get("/scaling/decisions", tags=["scaling"])
async def get_scaling_decisions(limit: int = Query(20, ge=1, le=100)):
    """Retrieve decision history from the DPBPS controller."""
    return [d.dict() for d in dpbps_controller.get_history(limit)]


@router.post("/scaling/evaluate", tags=["scaling"])
async def evaluate_scaling(telemetry: List[TelemetryInput]):
    """
    Evaluate submitted telemetry inputs using DPBPSController and process through
    KubernetesScalingActuator in dry-run mode.
    """
    decisions = dpbps_controller.evaluate(telemetry)

    # In dry-run mode, simulate and record results
    actuator = get_kubernetes_actuator()
    actuator_results = actuator.execute_decisions(decisions)

    # Store in actuator history
    _actuator_history.extend(actuator_results)
    while len(_actuator_history) > 100:
        _actuator_history.pop(0)

    # If scaling is disabled (standard safety posture), adjust reasons if needed
    if not cfg.SCALING_ENABLED:
        for d in decisions:
            if d.action == DecisionAction.INSUFFICIENT_TELEMETRY:
                d.action = DecisionAction.HOLD
                d.reason = "Telemetry insufficient; treated as HOLD in simulation mode."

    return [d.dict() for d in decisions]


@router.post("/scaling/dry-run", tags=["scaling"])
async def dry_run_scaling(telemetry: List[TelemetryInput]):
    """Evaluate telemetry without recording into controller decision history."""
    decisions = dpbps_controller.dry_run(telemetry)
    return [d.dict() for d in decisions]


class DeploymentPhasePayload(BaseModel):
    phase: DeploymentPhase


@router.post("/scaling/deployment-phase", tags=["scaling"])
async def set_deployment_phase(payload: DeploymentPhasePayload):
    """Update active deployment phase across DPBPS components."""
    shared_state_manager.set_phase(payload.phase)
    return {"phase": shared_state_manager.get_phase().value}


@router.get("/scaling/actuator/history", tags=["scaling"])
async def get_actuator_history(limit: int = Query(20, ge=1, le=100)):
    """Retrieve recent actuator execution records."""
    return [r.dict() for r in _actuator_history[-limit:]]


# ---------------------------------------------------------------------
# CONSOLIDATED DPBPS PIPELINE ENDPOINT (STEP 3)
# ---------------------------------------------------------------------

class PipelineServiceResult(BaseModel):
    service_name: str
    request_rate: Optional[float] = None
    p95_latency: Optional[float] = None
    error_rate: Optional[float] = None
    cpu_utilization: Optional[float] = None
    memory_utilization: Optional[float] = None
    current_replicas: int
    ready_replicas: int
    deployment_phase: str
    bottleneck_information: Optional[str] = None
    dpbps_decision: str
    proposed_replica_count: int
    actuator_execution_status: str
    reason: str
    cluster_modified: bool = False
    telemetry_complete: bool
    missing_metrics: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    timestamp: str


class PipelineEvaluationResponse(BaseModel):
    timestamp: str
    deployment_phase: str
    execution_mode: str = "DRY_RUN"
    cluster_modified: bool = False
    total_services: int
    complete_telemetry_services: int
    incomplete_telemetry_services: int
    bottleneck_service: Optional[str] = None
    scale_up_count: int
    scale_down_count: int
    hold_count: int
    services: List[PipelineServiceResult]


@router.get("/dpbps/pipeline/evaluate", response_model=PipelineEvaluationResponse, tags=["pipeline"])
@router.post("/dpbps/pipeline/evaluate", response_model=PipelineEvaluationResponse, tags=["pipeline"])
async def run_pipeline_evaluation():
    """
    Execute the complete end-to-end DPBPS evaluation pipeline in DRY-RUN mode.

    Pipeline Steps:
    1. Collects live telemetry for all eligible microservices via KubernetesTelemetryAdapter.
    2. Excludes services with incomplete, missing, or stale telemetry.
    3. Passes validated TelemetryInput objects to DPBPSController.
    4. Generates scaling decisions and detects bottleneck services.
    5. Evaluates scaling decisions through KubernetesScalingActuator in DRY-RUN mode.
    6. Returns a consolidated, structured per-service response.
    """
    adapter = get_telemetry_adapter()
    actuator = get_kubernetes_actuator()
    now_str = datetime.now(timezone.utc).isoformat()
    current_phase = shared_state_manager.get_phase().value

    # 1. Ingest telemetry
    try:
        valid_inputs, excluded = adapter.get_telemetry_inputs()
    except Exception as exc:
        logger.error("Failed to collect telemetry inputs in pipeline: %s", exc)
        raise HTTPException(status_code=500, detail=f"Telemetry collection failed: {exc}")

    # 2. Evaluate decisions through DPBPS Controller
    decisions = dpbps_controller.evaluate(valid_inputs)

    # 3. Process through Actuator in Dry-Run mode
    actuator_results = actuator.execute_decisions(decisions)

    # Record in history buffer
    _actuator_history.extend(actuator_results)
    while len(_actuator_history) > 100:
        _actuator_history.pop(0)

    # Index decisions and actuator results
    dec_map: Dict[str, DecisionOutput] = {d.service_name: d for d in decisions}
    act_map: Dict[str, KubernetesScalingResult] = {r.service_name: r for r in actuator_results}

    # Retrieve full raw telemetry for complete inventory
    raw_telemetry = adapter.collect_deployment_telemetry()
    service_results: List[PipelineServiceResult] = []

    bottleneck_detected = None

    for item in raw_telemetry:
        svc_name = item["service_name"]

        # Skip loadgenerator from microservice list
        if svc_name == "loadgenerator":
            continue

        is_complete = item.get("telemetry_available", False)
        desired_rep = item.get("desired_replicas", 0)
        ready_rep = item.get("ready_replicas", 0)

        if svc_name in dec_map:
            decision = dec_map[svc_name]
            act_res = act_map.get(svc_name)
            if decision.bottleneck:
                bottleneck_detected = decision.bottleneck

            service_results.append(PipelineServiceResult(
                service_name=svc_name,
                request_rate=item.get("request_rate"),
                p95_latency=item.get("p95_latency_ms"),
                error_rate=item.get("error_rate"),
                cpu_utilization=item.get("cpu_utilisation"),
                memory_utilization=item.get("memory_utilisation"),
                current_replicas=desired_rep,
                ready_replicas=ready_rep,
                deployment_phase=current_phase,
                bottleneck_information=decision.bottleneck,
                dpbps_decision=decision.action.value,
                proposed_replica_count=decision.requested_replicas,
                actuator_execution_status=act_res.status.value if act_res else "VALIDATED",
                reason=decision.reason,
                cluster_modified=False,
                telemetry_complete=True,
                missing_metrics=item.get("missing_metrics", []),
                dependencies=item.get("dependencies", []),
                timestamp=item.get("timestamp") or now_str,
            ))
        else:
            # Excluded service
            missing = item.get("missing_metrics", [])
            reason_str = item.get("reason") or (f"Excluded: missing metrics {missing}" if missing else "Excluded: uninstrumented or inactive")

            service_results.append(PipelineServiceResult(
                service_name=svc_name,
                request_rate=item.get("request_rate"),
                p95_latency=item.get("p95_latency_ms"),
                error_rate=item.get("error_rate"),
                cpu_utilization=item.get("cpu_utilisation"),
                memory_utilization=item.get("memory_utilisation"),
                current_replicas=desired_rep,
                ready_replicas=ready_rep,
                deployment_phase=current_phase,
                bottleneck_information=None,
                dpbps_decision="EXCLUDED",
                proposed_replica_count=desired_rep,
                actuator_execution_status="SKIPPED",
                reason=reason_str,
                cluster_modified=False,
                telemetry_complete=False,
                missing_metrics=missing,
                dependencies=item.get("dependencies", []),
                timestamp=item.get("timestamp") or now_str,
            ))

    scale_up_count = sum(1 for d in decisions if d.action == DecisionAction.SCALE_UP)
    scale_down_count = sum(1 for d in decisions if d.action == DecisionAction.SCALE_DOWN)
    hold_count = sum(1 for d in decisions if d.action == DecisionAction.HOLD)

    return PipelineEvaluationResponse(
        timestamp=now_str,
        deployment_phase=current_phase,
        execution_mode="DRY_RUN",
        cluster_modified=False,
        total_services=len(service_results),
        complete_telemetry_services=len(valid_inputs),
        incomplete_telemetry_services=len(service_results) - len(valid_inputs),
        bottleneck_service=bottleneck_detected,
        scale_up_count=scale_up_count,
        scale_down_count=scale_down_count,
        hold_count=hold_count,
        services=service_results,
    )
