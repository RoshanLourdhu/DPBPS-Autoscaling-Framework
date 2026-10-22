# backend/load_testing/locustfile.py
"""
Locust load‑testing script for the DPBPS platform.
It performs a lightweight smoke‑test consisting of:
1️⃣  Health‑check of the orchestration API.
2️⃣  Retrieval of the service list (read‑only).
3️⃣  Retrieval of the scaling status.
4️⃣  A single evaluation request to the DPBPS controller using a tiny
   deterministic telemetry payload.
All tasks are inexpensive and do not modify persistent state.
"""

import json
from locust import HttpUser, task, between


class DpbpsSmokeUser(HttpUser):
    """A conservative set of read‑only tasks for a quick sanity check."""

    # Wait between 1 and 2 seconds between tasks to keep load low.
    wait_time = between(1, 2)

    @task(2)
    def health(self):
        self.client.get("/api/v1/health", name="HealthCheck")

    @task(1)
    def list_services(self):
        self.client.get("/api/v1/services", name="ListServices")

    @task(1)
    def scaling_status(self):
        self.client.get("/api/v1/scaling/status", name="ScalingStatus")

    @task(1)
    def evaluate_scaling(self):
        # Minimal telemetry payload – a single service sample.
        payload = [
            {
                "service_name": "product",
                "request_rate": 120,
                "p95_latency": 180,
                "error_rate": 0.01,
                "cpu_utilisation": 0.55,
                "memory_utilisation": 0.40,
                "current_replicas": 2,
                "timestamp": "2026-10-22T00:00:00Z",
                "dependencies": []
            }
        ]
        self.client.post(
            "/api/v1/scaling/evaluate",
            json=payload,
            name="EvaluateScaling"
        )
