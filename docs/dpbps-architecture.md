# docs/dpbps-architecture.md

## DPBPS Architecture Overview

The project currently consists of:

1. **Microservice routers** – FastAPI applications for `product`, `cart`, `checkout`, and `recommendation`. Each service runs independently and uses the shared **SQLite** database by default (or PostgreSQL when the `DB_BACKEND` environment variable is set). The services expose simple CRUD endpoints and a health endpoint.
2. **Orchestration API** – `backend/app/main.py` combines the `v1_router` from `backend/app/api/v1_router.py`. This API provides generic endpoints for health, environments, metrics, services, experiments, and scaling configuration. It does **not** currently contain any scaling controller logic.
3. **Docker‑Compose** – Defines containers for the four services, a PostgreSQL instance, and the orchestration API. The compose file includes health‑checks but does **not** provide any Kubernetes‑style scaling resources or rolling‑update mechanisms.
4. **Baseline experiment runner** – `backend/scripts/run_baseline_experiments.py` can drive workload scenarios against the orchestration API and record metrics. It works with the fixed‑replica configuration.
5. **Metrics & workload generation** – The `simulation` sub‑router under `backend/app/api/simulation.py` can generate synthetic workloads and return placeholder metric data. Real telemetry (CPU, memory, latency, error‑rate) is not harvested from the services at the moment.

### Current Capabilities
- Start each microservice locally (SQLite backend works out‑of‑the‑box).
- Execute baseline experiments against the orchestration API.
- Retrieve placeholder metric objects via `/metrics/overview` (currently empty).
- Manage experiments via the `/experiments` endpoints (mocked).

### Missing Infrastructure for DPBPS
| Component | Availability | Comment |
|-----------|--------------|---------|
| **Kubernetes / HPA** | **Absent** | No cluster, no Deployment objects, no Horizontal Pod Autoscaler.
| **Prometheus / Grafana** | **Absent** | No metrics collection pipeline.
| **Real telemetry** | **Partial** | Only synthetic data from `simulation` exists; services don’t expose CPU/memory usage.
| **Deployment phase events** | **Absent** | No source of real deployment state changes.

### Integration Points for DPBPS
1. **Telemetry source** – The controller will consume the same JSON structure used by the baseline runner (`request_rate`, `p95_latency`, `error_rate`, `cpu_utilisation`, `memory_utilisation`). For now we will rely on the simulated data produced by the `simulation` router.
2. **Scaling configuration** – Existing scaling config endpoint (`/scaling/config`) returns a `ScalingConfig` model. DPBPS will read this configuration (or a dedicated DPBPS config) to obtain replica limits and threshold values.
3. **Deployment‑phase awareness** – The controller will expose a small state machine (PRE_DEPLOYMENT, ACTIVE_DEPLOYMENT, POST_DEPLOYMENT, NORMAL_OPERATION). The state can be driven manually via an API call or inferred from simulated deployment events.
4. **Decision output** – Decisions will be returned via new API endpoints (`/scaling/evaluate`, `/scaling/dry‑run`) and persisted through a lightweight logger that writes JSON lines to `results/dpbps/decisions.log`.
5. **Adapter layer** – Because the environment lacks a real orchestrator, a **simulation adapter** will be used. It pretends to apply a replica change and returns the requested replica count. The adapter can be swapped later for a real Kubernetes client.

### High‑level Component Diagram
```
+-------------------+      +-------------------+      +-------------------+
|   Telemetry API   | ---> |   DPBPS Controller| ---> | Scaling Adapter   |
| (simulation data) |      | (decision engine) |      | (simulated only) |
+-------------------+      +-------------------+      +-------------------+
        ^                         ^                        |
        |                         |                        |
        |                         |                        v
+-------------------+   +-------------------+   +-------------------+
|   Baseline Runner |   |   Orchestration   |   |   Microservices   |
+-------------------+   |   API (v1)       |   +-------------------+
                        +-------------------+
```

### Next Steps
- Implement the DPBPS decision model and related modules under `backend/scaling/`.
- Add API endpoints to the orchestration API.
- Provide a simulation‑only scaling adapter.
- Write unit tests covering the decision logic.
- Document the algorithm in `docs/dpbps-algorithm.md`.
- Ensure the baseline runner remains functional.
