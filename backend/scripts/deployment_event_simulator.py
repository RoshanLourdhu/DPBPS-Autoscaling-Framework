# backend/scripts/deployment_event_simulator.py
"""
Deterministic deployment‑event simulator for DPBPS.
Generates synthetic telemetry for a set of predefined deployment phases
and feeds it to the DPBPSController. Results are stored as JSON under
results/deployment_events/<unique‑id>.json.
"""
import json
import time
import uuid
from pathlib import Path
from typing import List, Dict

from backend.scaling.dpbps_controller import DPBPSController
from backend.scaling.models import TelemetryInput, DeploymentPhase

# ----------------------------------------------------------------------
# Pre‑defined deterministic scenarios (selected for simplicity).
# ----------------------------------------------------------------------
SCENARIOS: Dict[str, List[TelemetryInput]] = {
    "normal_operation": [
        TelemetryInput(
            service_name="product",
            request_rate=120,
            p95_latency=180,
            error_rate=0.01,
            cpu_utilisation=0.55,
            memory_utilisation=0.40,
            current_replicas=2,
            timestamp="2026-10-22T00:00:00Z",
            dependencies=[],
        ),
        TelemetryInput(
            service_name="cart",
            request_rate=80,
            p95_latency=150,
            error_rate=0.00,
            cpu_utilisation=0.48,
            memory_utilisation=0.35,
            current_replicas=2,
            timestamp="2026-10-22T00:00:00Z",
            dependencies=["product"],
        ),
    ],
    "pre_deployment": [
        TelemetryInput(
            service_name="product",
            request_rate=200,
            p95_latency=250,
            error_rate=0.03,
            cpu_utilisation=0.85,
            memory_utilisation=0.70,
            current_replicas=2,
            timestamp="2026-10-22T00:00:00Z",
            dependencies=[],
        )
    ],
    "active_deployment": [
        TelemetryInput(
            service_name="product",
            request_rate=300,
            p95_latency=350,
            error_rate=0.05,
            cpu_utilisation=0.92,
            memory_utilisation=0.80,
            current_replicas=2,
            timestamp="2026-10-22T00:00:00Z",
            dependencies=[],
        )
    ],
    "post_deployment": [
        TelemetryInput(
            service_name="product",
            request_rate=80,
            p95_latency=120,
            error_rate=0.00,
            cpu_utilisation=0.30,
            memory_utilisation=0.20,
            current_replicas=2,
            timestamp="2026-10-22T00:00:00Z",
            dependencies=[],
        )
    ],
}


def _run_one(controller: DPBPSController, name: str, telemetry: List[TelemetryInput]) -> Dict:
    """Execute controller.evaluate for a single scenario and measure latency."""
    start = time.perf_counter()
    decisions = controller.evaluate(telemetry)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return {
        "scenario": name,
        "decisions": [d.dict() for d in decisions],
        "elapsed_ms": elapsed_ms,
    }


def main() -> None:
    controller = DPBPSController()
    results: List[Dict] = []

    for name, telemetry in SCENARIOS.items():
        # Set phase according to scenario name
        if name == "pre_deployment":
            controller.set_phase(DeploymentPhase.PRE_DEPLOYMENT)
        elif name == "active_deployment":
            controller.set_phase(DeploymentPhase.ACTIVE_DEPLOYMENT)
        elif name == "post_deployment":
            controller.set_phase(DeploymentPhase.POST_DEPLOYMENT)
        else:
            controller.set_phase(DeploymentPhase.NORMAL_OPERATION)

        results.append(_run_one(controller, name, telemetry))

    out_dir = Path("results/deployment_events")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{uuid.uuid4().hex}.json"
    out_file.write_text(json.dumps(results, indent=2))
    print(f"Wrote {len(results)} scenario results to {out_file}")


if __name__ == "__main__":
    main()
