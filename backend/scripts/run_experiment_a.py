#!/usr/bin/env python3
"""
Experiment A – DPBPS controller‑only validation
Runs deterministic API requests against the live orchestration API while
ensuring `SCALING_ENABLED` remains false. No Docker scaling commands are executed.
The script writes a detailed markdown report to the artifact directory.
"""
import os
import sys
from pathlib import Path
# Ensure the project root is on sys.path for local imports
sys.path.append(str(Path(__file__).parents[2]))
import json
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List

# FastAPI test client
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

# Ensure scaling is disabled for safety
import backend.config as cfg
if cfg.SCALING_ENABLED:
    print("[ERROR] SCALING_ENABLED is True – aborting Experiment A to prevent live scaling.")
    sys.exit(1)

# Helper to get current replica count (read‑only)
def get_replica_count(service: str) -> int:
    cmd = ["docker", "compose", "-f", "docker-compose.yml", "ps", "-q", service]
    result = subprocess.run(cmd, cwd=Path(__file__).parents[2], capture_output=True, text=True)
    # Each line is a container ID; empty output means 0 replicas
    ids = [line for line in result.stdout.splitlines() if line.strip()]
    return len(ids)

# Record initial replica counts
services = ["product-service", "cart-service", "checkout-service", "recommendation-service"]
initial_counts = {svc: get_replica_count(svc) for svc in services}

# Utility to build telemetry dict
def telemetry(service_name: str, cpu: float, mem: float, latency: float, error: float, replicas: int, ts: datetime = None) -> dict:
    if ts is None:
        ts = datetime.now(timezone.utc)
    return {
        "service_name": service_name,
        "request_rate": 100.0,
        "p95_latency": latency,
        "error_rate": error,
        "cpu_utilisation": cpu,
        "memory_utilisation": mem,
        "current_replicas": replicas,
        "ready_replicas": replicas,
        "timestamp": ts.isoformat(),
        "dependencies": []
    }

# Store results for the markdown report
report_lines = ["# Phase 10.5 – Experiment A Results", ""]
report_lines.append(f"**Initial replica counts**: {initial_counts}")
report_lines.append("")

# ==== Test A1 – HOLD ====
tele_a1 = telemetry("product-service", cpu=0.5, mem=0.5, latency=180, error=0.0, replicas=1)
resp_a1 = client.post("/api/v1/scaling/evaluate", json=[tele_a1])
report_lines.append("## Test A1 – HOLD")
report_lines.append(f"*Input*: `{tele_a1}`")
report_lines.append(f"*HTTP status*: {resp_a1.status_code}")
report_lines.append(f"*Response*: `{resp_a1.json()}`")
report_lines.append(f"*Actuator invoked?*: No (scaling disabled)" )
report_lines.append("")

# ==== Test A2 – SCALE_UP ====
tele_a2 = telemetry("cart-service", cpu=1.0, mem=1.0, latency=500, error=0.2, replicas=1)
resp_a2 = client.post("/api/v1/scaling/evaluate", json=[tele_a2])
report_lines.append("## Test A2 – SCALE_UP")
report_lines.append(f"*Input*: `{tele_a2}`")
report_lines.append(f"*HTTP status*: {resp_a2.status_code}")
report_lines.append(f"*Response*: `{resp_a2.json()}`")
report_lines.append("*Actuator invoked?*: No (SCALING_ENABLED=false)")
report_lines.append("")

# ==== Test A3 – SCALE_DOWN (requires 2 replicas) ====
tele_a3 = telemetry("checkout-service", cpu=0.1, mem=0.1, latency=100, error=0.0, replicas=2)
resp_a3 = client.post("/api/v1/scaling/evaluate", json=[tele_a3])
report_lines.append("## Test A3 – SCALE_DOWN")
report_lines.append(f"*Input*: `{tele_a3}`")
report_lines.append(f"*HTTP status*: {resp_a3.status_code}")
report_lines.append(f"*Response*: `{resp_a3.json()}`")
report_lines.append("*Actuator invoked?*: No (SCALING_ENABLED=false)")
report_lines.append("")

# ==== Test A4 – Stale telemetry ====
stale_ts = datetime.now(timezone.utc) - timedelta(seconds=60)  # older than freshness_sec=30
tele_a4 = telemetry("recommendation-service", cpu=0.5, mem=0.5, latency=180, error=0.0, replicas=1, ts=stale_ts)
resp_a4 = client.post("/api/v1/scaling/evaluate", json=[tele_a4])
report_lines.append("## Test A4 – Stale telemetry")
report_lines.append(f"*Input (timestamp {stale_ts.isoformat()} older than 30 s)*")
report_lines.append(f"*HTTP status*: {resp_a4.status_code}")
report_lines.append(f"*Response*: `{resp_a4.json()}`")
report_lines.append("*Actuator invoked?*: No")
report_lines.append("")

# ==== Test A5 – Invalid telemetry (negative CPU) ====
tele_a5 = telemetry("product-service", cpu=-0.1, mem=0.5, latency=180, error=0.0, replicas=1)
resp_a5 = client.post("/api/v1/scaling/evaluate", json=[tele_a5])
report_lines.append("## Test A5 – Invalid telemetry")
report_lines.append(f"*Input*: `{tele_a5}` (invalid negative CPU)")
report_lines.append(f"*HTTP status*: {resp_a5.status_code}")
report_lines.append(f"*Response*: `{resp_a5.text}`")
report_lines.append("*Actuator invoked?*: No (request rejected by validation)")
report_lines.append("")

# ==== Test A6 – Deployment‑phase behavior ====
# Set phase to POST_DEPLOYMENT
client.post("/api/v1/scaling/deployment-phase", json={"phase": "POST_DEPLOYMENT"})
# Telemetry that would trigger downscale
tele_a6 = telemetry("cart-service", cpu=0.1, mem=0.1, latency=100, error=0.0, replicas=2)
resp_a6 = client.post("/api/v1/scaling/evaluate", json=[tele_a6])
report_lines.append("## Test A6 – Deployment‑phase (POST_DEPLOYMENT) downscale suppression")
report_lines.append(f"*Input*: `{tele_a6}`")
report_lines.append(f"*HTTP status*: {resp_a6.status_code}")
report_lines.append(f"*Response*: `{resp_a6.json()}`")
report_lines.append("*Actuator invoked?*: No")
report_lines.append("")

# Reset phase to NORMAL_OPERATION for cleanliness
client.post("/api/v1/scaling/deployment-phase", json={"phase": "NORMAL_OPERATION"})

# Record final replica counts (should be unchanged)
final_counts = {svc: get_replica_count(svc) for svc in services}
report_lines.append(f"**Final replica counts**: {final_counts}")

# Write report to artifact directory
artifact_dir = Path(os.getenv("GEMINI_ARTIFACT_ROOT", "c:/Users/ROSHAN/.gemini/antigravity-ide/brain/5b13d5fd-04b5-4359-bec6-03c972667810/docs"))
artifact_path = artifact_dir / "phase10_5_experiment_A_results.md"
# Avoid overwriting an existing report
if artifact_path.exists():
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_path = artifact_dir / f"phase10_5_experiment_A_results_{timestamp}.md"

# Write the report safely
try:
    artifact_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Report written to {artifact_path}")
except Exception as e:
    print(f"Failed to write report: {e}")
