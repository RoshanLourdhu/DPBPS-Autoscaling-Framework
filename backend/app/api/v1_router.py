from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from backend.config import SCALING_ENABLED

router = APIRouter()

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str

@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    return {"status": "ok", "service": "dpbps-backend", "version": "0.1.0"}

class EnvironmentInfo(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    status: str

@router.get("/environments", response_model=List[EnvironmentInfo], tags=["environment"])
async def list_environments():
    # Demo placeholder data
    return [
        {
            "id": "simulated",
            "name": "DPBPS Simulation Lab",
            "description": "Controlled microservices experiments.",
            "status": "DISCONNECTED",
        },
        {
            "id": "real",
            "name": "Google Online Boutique",
            "description": "Open‑source e‑commerce microservices demo.",
            "status": "DISCONNECTED",
        },
    ]

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
    # Return empty demo list
    return {"metrics": []}

class ServiceInfo(BaseModel):
    id: str
    name: str
    environment_id: str
    health: str
    ready_replicas: int
    cpu_utilisation: float
    memory_utilisation: float
    request_rate: float
    p95_latency: float
    error_rate: float

@router.get("/services", response_model=List[ServiceInfo], tags=["service"])
async def list_services():
    return []

class ExperimentCreate(BaseModel):
    name: str
    environment_id: str
    scaling_strategy: str
    workload_scenario: str
    duration_seconds: int
    configuration: dict

class ExperimentInfo(ExperimentCreate):
    id: str
    status: str
    start_timestamp: Optional[str] = None
    end_timestamp: Optional[str] = None

@router.get("/experiments", response_model=List[ExperimentInfo], tags=["experiment"])
async def list_experiments():
    return []

@router.post("/experiments", response_model=ExperimentInfo, tags=["experiment"])
async def create_experiment(exp: ExperimentCreate):
    # Simple echo with generated ID
    return ExperimentInfo(**exp.dict(), id="exp-001", status="REGISTERED")

@router.get("/experiments/{experiment_id}", response_model=ExperimentInfo, tags=["experiment"])
async def get_experiment(experiment_id: str):
    # Placeholder response
    return ExperimentInfo(
        id=experiment_id,
        name="Demo Experiment",
        environment_id="simulated",
        scaling_strategy="fixed",
        workload_scenario="constant",
        duration_seconds=60,
        configuration={},
        status="COMPLETED",
        start_timestamp="2026-01-01T00:00:00Z",
        end_timestamp="2026-01-01T00:01:00Z",
    )

class ScalingConfig(BaseModel):
    strategy: str
    min_replicas: int
    max_replicas: int
    cpu_threshold: float
    memory_threshold: float
    latency_target_ms: float
    scale_up_window_sec: int
    scale_down_window_sec: int
    cooldown_sec: int

@router.get("/scaling/config", response_model=ScalingConfig, tags=["scaling"])
async def get_scaling_config():
    return ScalingConfig(
        strategy="fixed",
        min_replicas=1,
        max_replicas=10,
        cpu_threshold=0.8,
        memory_threshold=0.8,
        latency_target_ms=200,
        scale_up_window_sec=30,
        scale_down_window_sec=120,
        cooldown_sec=15,
    )

@router.put("/scaling/config", response_model=ScalingConfig, tags=["scaling"])
async def update_scaling_config(cfg: ScalingConfig):
    return cfg

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
    return []

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
    return []

# -------------------------------------------------
# Simulation sub‑router (Phase 2B)
# -------------------------------------------------
from .simulation import router as simulation_router
router.include_router(simulation_router, prefix="/simulation", tags=["simulation"])
# DPBPS Simulation Controller
from backend.scaling.dpbps_controller import DPBPSController
from backend.scaling.models import DeploymentPhase, DecisionAction, TelemetryInput

# Global controller instance
dpbps_controller = DPBPSController()

# Scaling status endpoint
@router.get("/scaling/status", tags=["scaling"]) 
async def get_scaling_status():
    return {
        "simulation_mode": True,
        "phase": dpbps_controller.get_phase().value,
        "config": dpbps_controller.config.dict(),
        "latest_decision": dpbps_controller.decision_history[-1].dict() if dpbps_controller.decision_history else None,
    }

# Scaling decisions history
@router.get("/scaling/decisions", tags=["scaling"]) 
async def get_scaling_decisions(limit: int = 20):
    return [d.dict() for d in dpbps_controller.get_history(limit)]

# Evaluate telemetry (real scaling simulation)
@router.post("/scaling/evaluate", tags=["scaling"]) 
async def evaluate_scaling(telemetry: List[TelemetryInput]):
    # Determine scaling mode dynamically from environment to avoid stale module state.
    import os
    scaling_enabled = os.getenv("SCALING_ENABLED", "false").lower() == "true"
    # Always evaluate to update history.
    decisions = dpbps_controller.evaluate(telemetry)
    # If scaling is disabled, do not invoke actuator. Convert INSUFFICIENT_TELEMETRY to HOLD for safety.
    if not scaling_enabled:
        from backend.scaling.models import DecisionAction
        for d in decisions:
            if d.action == DecisionAction.INSUFFICIENT_TELEMETRY:
                d.action = DecisionAction.HOLD
                d.reason = "Telemetry insufficient; treated as HOLD in simulation mode."
        return [d.dict() for d in decisions]
    # Scaling enabled: apply decisions via actuator.
    from backend.scaling.actuator import apply_decisions
    try:
        apply_decisions(decisions)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Live scaling error: {e}")
    return [d.dict() for d in decisions]
# Dry‑run endpoint
@router.post("/scaling/dry-run", tags=["scaling"]) 
async def dry_run_scaling(telemetry: List[TelemetryInput]):
    decisions = dpbps_controller.dry_run(telemetry)
    return [d.dict() for d in decisions]

# Set deployment phase
class DeploymentPhasePayload(BaseModel):
    phase: DeploymentPhase

@router.post("/scaling/deployment-phase", tags=["scaling"]) 
async def set_deployment_phase(payload: DeploymentPhasePayload):
    dpbps_controller.set_phase(payload.phase)
    return {"phase": dpbps_controller.get_phase().value}
